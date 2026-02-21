"""
Training data seeder — fixes the 3 BPR training blockers.

Blocker 1: ModelRegistry seed entries + BehavioralSignal.modelVersion backfill
Blocker 2: PersonaDimension materialization from Trip.personaSeed JSON
Blocker 3: RankingEvent seeding (~15K events, top-20 candidates per day)

All operations are idempotent:
  - ModelRegistry: ON CONFLICT DO NOTHING
  - BehavioralSignal backfill: WHERE modelVersion IS NULL
  - PersonaDimension: DELETE shadow rows + re-INSERT (in transaction)
  - RankingEvent: DELETE shadow rows + re-INSERT (in transaction)

Usage:
    pool = await asyncpg.create_pool(DATABASE_URL)
    result = await seed_training_data(pool)
"""

import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)

# Import affinity computation from persona_seeder (single source of truth)
from services.api.pipeline.persona_seeder import (
    ALL_CATEGORIES,
    BASE_VECTORS,
    BUDGET_MODIFIERS,
    PACE_MODIFIERS,
    SOCIAL_MODIFIERS,
    TIME_MODIFIERS,
    _compute_affinities,
)

# Mapping from persona_seed labels back to axis values used in _compute_affinities
PACE_REVERSE = {
    "leisurely": "slow", "slow": "slow",
    "moderate": "moderate",
    "fast": "packed", "packed": "packed",
}

BUDGET_REVERSE = {
    "low": "low",
    "mid": "mid",
    "high": "high",
    "flexible": "mid",  # Older shadow users — treat as mid
}

# Some persona seeds have composite social modes — map to primary component
SOCIAL_REVERSE = {
    "solo": "solo",
    "couple": "couple",
    "group": "group",
    "solo_or_couple": "solo",
    "solo_or_group": "solo",
    "couple_or_group": "couple",
    "solo_or_small": "solo",
}


@dataclass
class TrainingDataResult:
    model_registry_seeded: int = 0
    signals_backfilled: int = 0
    persona_dimensions_created: int = 0
    ranking_events_created: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Blocker 1: ModelRegistry + backfill
# ---------------------------------------------------------------------------


async def _seed_model_registry(conn: asyncpg.Connection) -> int:
    """Seed 2 ModelRegistry entries. ON CONFLICT = idempotent."""
    now = datetime.utcnow()
    entries = [
        {
            "model_name": "llm_ranker",
            "model_version": "0.1.0",
            "stage": "production",
            "model_type": "llm_ranking",
            "description": "Claude Sonnet-based ranking, bootstrap phase",
        },
        {
            "model_name": "bpr",
            "model_version": "0.0.0",
            "stage": "staging",
            "model_type": "collaborative_filtering",
            "description": "BPR placeholder, awaiting first training run",
        },
    ]

    count = 0
    for entry in entries:
        result = await conn.execute(
            """
            INSERT INTO "ModelRegistry" (
                "id", "modelName", "modelVersion", "stage", "modelType",
                "description", "createdAt", "updatedAt"
            ) VALUES ($1, $2, $3, $4::\"ModelStage\", $5, $6, $7, $7)
            ON CONFLICT ("modelName", "modelVersion") DO NOTHING
            """,
            str(uuid.uuid4()),
            entry["model_name"],
            entry["model_version"],
            entry["stage"],
            entry["model_type"],
            entry["description"],
            now,
        )
        if result == "INSERT 0 1":
            count += 1
            logger.info(f"Seeded ModelRegistry: {entry['model_name']}:{entry['model_version']}")
        else:
            logger.info(f"ModelRegistry already exists: {entry['model_name']}:{entry['model_version']}")

    return count


async def _backfill_model_version(conn: asyncpg.Connection) -> int:
    """Backfill modelVersion on shadow user BehavioralSignals."""
    result = await conn.execute(
        """
        UPDATE "BehavioralSignal"
        SET "modelVersion" = 'llm_ranker:0.1.0'
        WHERE "userId" IN (
            SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%'
        )
        AND "modelVersion" IS NULL
        """
    )
    # Result format: "UPDATE N"
    count = int(result.split()[-1])
    logger.info(f"Backfilled modelVersion on {count} BehavioralSignals")
    return count


# ---------------------------------------------------------------------------
# Blocker 2: PersonaDimension materialization
# ---------------------------------------------------------------------------

# The 8 dimensions to materialize
DIMENSION_EXTRACTORS = {
    "pace_preference": lambda ps: ps.get("pace", "moderate"),
    "budget_sensitivity": lambda ps: ps.get("budget_tier", "mid"),
    "cuisine_openness": lambda ps: str(ps.get("cuisine_openness", 0.60)),
    "social_mode": lambda ps: ps.get("social_mode", "solo"),
    "time_orientation": lambda ps: ps.get("time_orientation", "early_bird"),
    "primary_interest": lambda ps: ps.get("primary_interest", "food"),
    "trip_count": None,  # Computed separately from trip count
    "category_affinities": None,  # Computed from dimension values
}


def _compute_trip_count_label(count: int) -> str:
    """Categorize trip count into cold-start buckets."""
    if count <= 1:
        return "first_trip"
    elif count <= 3:
        return "returning"
    else:
        return "frequent"


def _recompute_affinities_from_persona_seed(persona_seed: dict) -> dict[str, float]:
    """Reconstruct category affinities from persona_seed dimension values.

    This recomputes the base affinity vector (without per-user jitter) from
    the stored persona dimensions. The small jitter gap (+/-0.05) vs the
    original seeding is a documented known limitation for the bootstrap run.
    """
    interest = persona_seed.get("primary_interest", "food")
    pace_label = persona_seed.get("pace", "moderate")
    pace = PACE_REVERSE.get(pace_label, "moderate")
    budget_raw = persona_seed.get("budget_tier", "mid")
    budget = BUDGET_REVERSE.get(budget_raw, "mid")
    social_raw = persona_seed.get("social_mode", "solo")
    social = SOCIAL_REVERSE.get(social_raw, "solo")
    time = persona_seed.get("time_orientation", "early_bird")

    return _compute_affinities(interest, pace, budget, social, time)


async def _seed_persona_dimensions(conn: asyncpg.Connection) -> int:
    """Materialize PersonaDimension rows from Trip.personaSeed JSON.

    DELETE + re-INSERT in a single transaction for idempotency.
    """
    # Get all shadow users with their first trip's personaSeed
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (u."id")
            u."id" as user_id,
            t."personaSeed" as persona_seed
        FROM "User" u
        JOIN "Trip" t ON t."userId" = u."id"
        WHERE u."email" LIKE 'shadow-%'
        AND t."personaSeed" IS NOT NULL
        ORDER BY u."id", t."createdAt" ASC
        """
    )

    if not rows:
        logger.warning("No shadow users with persona seeds found")
        return 0

    # Get trip counts per user
    trip_counts = dict(await conn.fetch(
        """
        SELECT "userId", COUNT(*)::int as cnt
        FROM "Trip"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        GROUP BY "userId"
        """
    ))

    # Delete existing shadow PersonaDimensions
    delete_result = await conn.execute(
        """
        DELETE FROM "PersonaDimension"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        """
    )
    deleted = int(delete_result.split()[-1])
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing PersonaDimension rows")

    # Insert fresh rows
    now = datetime.utcnow()
    count = 0

    for row in rows:
        user_id = row["user_id"]
        persona_seed_raw = row["persona_seed"]

        # Handle both string and dict formats
        if isinstance(persona_seed_raw, str):
            persona_seed = json.loads(persona_seed_raw)
        else:
            persona_seed = persona_seed_raw

        # Extract standard dimensions
        for dimension, extractor in DIMENSION_EXTRACTORS.items():
            if dimension == "trip_count":
                value = _compute_trip_count_label(trip_counts.get(user_id, 1))
            elif dimension == "category_affinities":
                affinities = _recompute_affinities_from_persona_seed(persona_seed)
                value = json.dumps(affinities)
            else:
                value = str(extractor(persona_seed))

            await conn.execute(
                """
                INSERT INTO "PersonaDimension" (
                    "id", "userId", "dimension", "value",
                    "confidence", "source", "updatedAt", "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
                """,
                str(uuid.uuid4()),
                user_id,
                dimension,
                value,
                1.0,
                "onboarding",
                now,
            )
            count += 1

    logger.info(f"Created {count} PersonaDimension rows for {len(rows)} users")
    return count


# ---------------------------------------------------------------------------
# Blocker 3: RankingEvent seeding
# ---------------------------------------------------------------------------


async def _seed_ranking_events(conn: asyncpg.Connection) -> int:
    """Seed RankingEvents (top-20 candidates per day per trip).

    Reads PersonaDimension category_affinities to rank candidates.
    DELETE + re-INSERT in a single transaction for idempotency.
    """
    # Delete existing shadow RankingEvents
    delete_result = await conn.execute(
        """
        DELETE FROM "RankingEvent"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        """
    )
    deleted = int(delete_result.split()[-1])
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing RankingEvent rows")

    # Load all shadow user affinities from PersonaDimension
    affinity_rows = await conn.fetch(
        """
        SELECT "userId", "value"
        FROM "PersonaDimension"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        AND "dimension" = 'category_affinities'
        """
    )
    user_affinities: dict[str, dict[str, float]] = {}
    for row in affinity_rows:
        user_affinities[row["userId"]] = json.loads(row["value"])

    if not user_affinities:
        logger.warning("No category_affinities in PersonaDimension — run dimension seeding first")
        return 0

    # Load activity nodes per city
    node_rows = await conn.fetch(
        """
        SELECT "id", "city", "category"
        FROM "ActivityNode"
        WHERE "status" != 'archived'
        """
    )
    city_nodes: dict[str, list[dict]] = {}
    for row in node_rows:
        city = row["city"]
        if city not in city_nodes:
            city_nodes[city] = []
        city_nodes[city].append({"id": row["id"], "category": row["category"]})

    # Load all shadow trips with their days and selected nodes
    trip_rows = await conn.fetch(
        """
        SELECT
            t."id" as trip_id,
            t."userId" as user_id,
            t."city",
            t."createdAt" as trip_created
        FROM "Trip" t
        JOIN "User" u ON u."id" = t."userId"
        WHERE u."email" LIKE 'shadow-%'
        ORDER BY t."userId", t."createdAt"
        """
    )

    now = datetime.utcnow()
    count = 0

    for trip in trip_rows:
        trip_id = trip["trip_id"]
        user_id = trip["user_id"]
        city = trip["city"]

        affinities = user_affinities.get(user_id)
        if not affinities:
            continue

        nodes = city_nodes.get(city, [])
        if not nodes:
            continue

        # Get all days with confirmed/completed slots for this trip
        day_slots = await conn.fetch(
            """
            SELECT "dayNumber", array_agg("activityNodeId") as selected_node_ids
            FROM "ItinerarySlot"
            WHERE "tripId" = $1
            AND "status" IN ('confirmed', 'completed')
            AND "activityNodeId" IS NOT NULL
            GROUP BY "dayNumber"
            ORDER BY "dayNumber"
            """,
            trip_id,
        )

        for day_row in day_slots:
            day_number = day_row["dayNumber"]
            selected_ids = [nid for nid in day_row["selected_node_ids"] if nid is not None]

            if not selected_ids:
                continue

            # Score all nodes by affinity, take top 20
            scored = []
            for node in nodes:
                cat = node["category"]
                score = affinities.get(cat, 0.3)
                scored.append((node["id"], score))
            scored.sort(key=lambda x: x[1], reverse=True)

            # Top 20 candidates (or all if fewer than 20)
            top_candidates = scored[:20]
            candidate_ids = [nid for nid, _ in top_candidates]

            # Ensure selected nodes are in the candidate set
            # (they should be, but edge cases with low-affinity confirmed slots)
            candidate_set = set(candidate_ids)
            for sid in selected_ids:
                if sid not in candidate_set:
                    candidate_ids.append(sid)

            # rankedIds = candidates ordered by affinity (already sorted)
            ranked_ids = candidate_ids.copy()

            # Filter selectedIds to only those in candidate set
            selected_in_candidates = [sid for sid in selected_ids if sid in set(candidate_ids)]

            await conn.execute(
                """
                INSERT INTO "RankingEvent" (
                    "id", "userId", "tripId", "dayNumber",
                    "modelName", "modelVersion",
                    "candidateIds", "rankedIds", "selectedIds",
                    "surface", "shadowRankedIds",
                    "latencyMs", "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                str(uuid.uuid4()),
                user_id,
                trip_id,
                day_number,
                "llm_ranker",
                "0.1.0",
                candidate_ids,
                ranked_ids,
                selected_in_candidates,
                "itinerary",
                [],  # No shadow model yet
                random.randint(200, 800),
                now,
            )
            count += 1

    logger.info(f"Created {count} RankingEvent rows")
    return count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def seed_training_data(pool: asyncpg.Pool) -> TrainingDataResult:
    """Run all 3 training data blockers in sequence.

    Order matters:
    1. ModelRegistry + backfill (no dependencies)
    2. PersonaDimension (reads Trip.personaSeed)
    3. RankingEvent (reads PersonaDimension.category_affinities)
    """
    result = TrainingDataResult()

    async with pool.acquire() as conn:
        # Step 1: ModelRegistry (idempotent via ON CONFLICT)
        try:
            result.model_registry_seeded = await _seed_model_registry(conn)
        except Exception as e:
            msg = f"ModelRegistry seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Step 1b: Backfill modelVersion
        try:
            result.signals_backfilled = await _backfill_model_version(conn)
        except Exception as e:
            msg = f"modelVersion backfill failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Step 2: PersonaDimension (DELETE + re-INSERT in transaction)
        try:
            async with conn.transaction():
                result.persona_dimensions_created = await _seed_persona_dimensions(conn)
        except Exception as e:
            msg = f"PersonaDimension seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Step 3: RankingEvent (DELETE + re-INSERT in transaction)
        try:
            async with conn.transaction():
                result.ranking_events_created = await _seed_ranking_events(conn)
        except Exception as e:
            msg = f"RankingEvent seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

    logger.info(
        f"Training data seeding complete: "
        f"{result.model_registry_seeded} registry entries, "
        f"{result.signals_backfilled} signals backfilled, "
        f"{result.persona_dimensions_created} persona dimensions, "
        f"{result.ranking_events_created} ranking events"
    )
    return result
