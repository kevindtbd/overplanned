"""
Training data seeder — fixes BPR training blockers + second-pass enrichments.

Blockers (Phase 1):
  1. ModelRegistry seed entries + BehavioralSignal.modelVersion backfill
  2. PersonaDimension materialization from Trip.personaSeed JSON
  3. RankingEvent seeding (~15K events, top-20 candidates per day)

Enrichments (Phase 2):
  4. PivotEvent records for existing swap slots
  5. IntentionSignal seeding for 20-30% of slot_skip signals
  6. Discovery swipe signals for ~30% of users
  7. WeatherContext backfill on outdoor/active signals
  8. Trip completion realism (abandoned + recent trips)

All operations are idempotent:
  - ModelRegistry: ON CONFLICT DO NOTHING
  - BehavioralSignal backfill: WHERE modelVersion IS NULL / weatherContext IS NULL
  - PersonaDimension: DELETE shadow rows + re-INSERT (in transaction)
  - RankingEvent: DELETE shadow rows + re-INSERT (in transaction)
  - PivotEvent: DELETE shadow rows + re-INSERT (in transaction)
  - IntentionSignal: DELETE shadow rows + re-INSERT (in transaction)
  - Discovery signals: DELETE shadow discover_* signals + re-INSERT (in transaction)

Usage:
    pool = await asyncpg.create_pool(DATABASE_URL)
    result = await seed_training_data(pool)
"""

import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

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
    # Phase 1: Blockers
    model_registry_seeded: int = 0
    signals_backfilled: int = 0
    persona_dimensions_created: int = 0
    ranking_events_created: int = 0
    # Phase 2: Enrichments
    pivot_events_created: int = 0
    intention_signals_created: int = 0
    discovery_signals_created: int = 0
    weather_signals_updated: int = 0
    trips_made_abandoned: int = 0
    trips_made_recent: int = 0
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
# Enrichment 1: PivotEvent records from swap slots
# ---------------------------------------------------------------------------

OUTDOOR_ACTIVE_CATEGORIES = ("outdoors", "active")


async def _seed_pivot_events(conn: asyncpg.Connection) -> int:
    """Create PivotEvent rows for swapped slots missing them.

    For each swapped slot, find the (skipped, replacement) pair by joining on
    (tripId, dayNumber, sortOrder). Verified: all 1,044 swaps have matching
    pairs at the same position, zero orphans.

    DELETE shadow PivotEvents + re-INSERT in transaction.
    """
    # Delete existing shadow PivotEvents (scoped to shadow user ownership)
    delete_result = await conn.execute(
        """
        DELETE FROM "PivotEvent"
        WHERE "tripId" IN (
            SELECT t."id" FROM "Trip" t
            JOIN "User" u ON u."id" = t."userId"
            WHERE u."email" LIKE 'shadow-%'
        )
        """
    )
    deleted = int(delete_result.split()[-1])
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing shadow PivotEvent rows")

    # Find swap pairs: (skipped slot, replacement slot) at same position
    swap_pairs = await conn.fetch(
        """
        SELECT
            skipped."tripId" as trip_id,
            skipped."id" as skipped_slot_id,
            skipped."activityNodeId" as original_node_id,
            replacement."activityNodeId" as selected_node_id
        FROM "ItinerarySlot" skipped
        JOIN "ItinerarySlot" replacement ON
            replacement."tripId" = skipped."tripId"
            AND replacement."dayNumber" = skipped."dayNumber"
            AND replacement."sortOrder" = skipped."sortOrder"
            AND replacement."id" != skipped."id"
            AND replacement."wasSwapped" = false
            AND replacement."status" IN ('confirmed', 'completed')
        JOIN "Trip" t ON t."id" = skipped."tripId"
        JOIN "User" u ON u."id" = t."userId"
        WHERE skipped."wasSwapped" = true
        AND skipped."status" = 'skipped'
        AND u."email" LIKE 'shadow-%'
        AND skipped."activityNodeId" IS NOT NULL
        AND replacement."activityNodeId" IS NOT NULL
        """
    )

    if not swap_pairs:
        logger.warning("No swap pairs found for PivotEvent seeding")
        return 0

    now = datetime.utcnow()
    rng = random.Random(42)
    count = 0

    for pair in swap_pairs:
        await conn.execute(
            """
            INSERT INTO "PivotEvent" (
                "id", "tripId", "slotId", "triggerType",
                "originalNodeId", "selectedNodeId", "alternativeIds",
                "status", "responseTimeMs", "resolvedAt", "createdAt"
            ) VALUES ($1, $2, $3, $4::\"PivotTrigger\", $5, $6, $7,
                      $8::\"PivotStatus\", $9, $10, $10)
            """,
            str(uuid.uuid4()),
            pair["trip_id"],
            pair["skipped_slot_id"],
            "user_request",
            pair["original_node_id"],
            pair["selected_node_id"],
            [pair["selected_node_id"]],
            "accepted",
            rng.randint(500, 3000),
            now,
        )
        count += 1

    logger.info(f"Created {count} PivotEvent rows from swap pairs")
    return count


# ---------------------------------------------------------------------------
# Enrichment 2: IntentionSignal seeding for slot_skip signals
# ---------------------------------------------------------------------------

# Weighted intention types (design doc spec)
INTENTION_WEIGHTS = {
    "not_interested": 32,
    "bad_timing": 17,
    "too_far": 15,
    "already_visited": 10,
    "weather": 10,
    "price_mismatch": 8,
    "group_conflict": 5,
    "fallback_not_interested": 3,
}


async def _seed_intention_signals(conn: asyncpg.Connection) -> int:
    """Seed IntentionSignals for ~25% of slot_skip signals.

    Per-user cap: max(1, user_skip_count * 0.25) to ensure coverage
    across all archetypes.

    DELETE shadow IntentionSignals + re-INSERT in transaction.
    """
    # Delete existing shadow IntentionSignals
    delete_result = await conn.execute(
        """
        DELETE FROM "IntentionSignal"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        """
    )
    deleted = int(delete_result.split()[-1])
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing shadow IntentionSignal rows")

    # Get all skip signals with context needed for intention type selection
    skip_signals = await conn.fetch(
        """
        SELECT
            bs."id" as signal_id,
            bs."userId" as user_id,
            bs."activityNodeId" as node_id,
            bs."tripId" as trip_id,
            an."category",
            an."priceLevel" as price_level
        FROM "BehavioralSignal" bs
        LEFT JOIN "ActivityNode" an ON an."id" = bs."activityNodeId"
        JOIN "User" u ON u."id" = bs."userId"
        WHERE bs."signalType" = 'slot_skip'
        AND u."email" LIKE 'shadow-%'
        ORDER BY bs."userId", bs."createdAt"
        """
    )

    if not skip_signals:
        logger.warning("No slot_skip signals found for IntentionSignal seeding")
        return 0

    # Load per-user persona dimensions for conditional logic
    user_dims = {}
    dim_rows = await conn.fetch(
        """
        SELECT "userId", "dimension", "value"
        FROM "PersonaDimension"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        AND "dimension" IN ('social_mode', 'budget_sensitivity')
        """
    )
    for row in dim_rows:
        uid = row["userId"]
        if uid not in user_dims:
            user_dims[uid] = {}
        user_dims[uid][row["dimension"]] = row["value"]

    # Group signals by user for per-user capping
    from collections import defaultdict
    user_signals: dict[str, list] = defaultdict(list)
    for sig in skip_signals:
        user_signals[sig["user_id"]].append(sig)

    now = datetime.utcnow()
    rng = random.Random(42)
    count = 0

    for user_id, signals in user_signals.items():
        cap = max(1, int(len(signals) * 0.25))
        selected = rng.sample(signals, min(cap, len(signals)))
        dims = user_dims.get(user_id, {})
        social = dims.get("social_mode", "solo")
        budget = dims.get("budget_sensitivity", "mid")

        for sig in selected:
            category = sig["category"]
            price_level = sig["price_level"]
            is_outdoor = category in OUTDOOR_ACTIVE_CATEGORIES if category else False
            is_group_user = "group" in social
            is_expensive = (price_level or 0) >= 3 and budget == "low"

            # Build weighted pool with conditional adjustments
            weights = dict(INTENTION_WEIGHTS)

            # weather gets 2x for outdoor/active
            if is_outdoor:
                weights["weather"] = weights["weather"] * 2

            # group_conflict only for group users
            if not is_group_user:
                weights["not_interested"] += weights.pop("group_conflict")

            # price_mismatch only when priceLevel >= 3 AND budget = low
            if not is_expensive:
                weights["not_interested"] += weights.pop("price_mismatch")

            # Collapse fallback
            weights["not_interested"] += weights.pop("fallback_not_interested", 0)

            # Weighted random selection
            types = list(weights.keys())
            w = list(weights.values())
            intention_type = rng.choices(types, weights=w, k=1)[0]

            await conn.execute(
                """
                INSERT INTO "IntentionSignal" (
                    "id", "behavioralSignalId", "userId",
                    "intentionType", "confidence", "source",
                    "userProvided", "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                str(uuid.uuid4()),
                sig["signal_id"],
                user_id,
                intention_type,
                1.0,
                "user_explicit",
                True,
                now,
            )
            count += 1

    logger.info(f"Created {count} IntentionSignal rows from {len(skip_signals)} skip signals")
    return count


# ---------------------------------------------------------------------------
# Enrichment 3: Discovery swipe signals
# ---------------------------------------------------------------------------


async def _seed_discovery_signals(
    conn: asyncpg.Connection, result: TrainingDataResult
) -> int:
    """Seed discovery swipe signals + RankingEvents for ~30% of shadow users.

    Thresholds (with +-15% per-user jitter):
    - affinity > 0.6: 65% right, 35% left
    - affinity 0.3-0.6: 40% right, 60% left
    - affinity < 0.3: 8% right, 92% left
    - Swipe-rights with affinity > 0.7: 30% chance of discover_shortlist

    DELETE shadow discover_* signals + discovery RankingEvents, then re-INSERT.
    """
    # Delete existing shadow discovery signals
    delete_result = await conn.execute(
        """
        DELETE FROM "BehavioralSignal"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        AND "signalType" IN ('discover_swipe_right', 'discover_swipe_left', 'discover_shortlist')
        """
    )
    deleted = int(delete_result.split()[-1])
    if deleted > 0:
        logger.info(f"Deleted {deleted} existing shadow discovery signals")

    # Delete existing shadow discovery RankingEvents
    delete_re = await conn.execute(
        """
        DELETE FROM "RankingEvent"
        WHERE "userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
        AND "surface" = 'discovery'
        """
    )
    deleted_re = int(delete_re.split()[-1])
    if deleted_re > 0:
        logger.info(f"Deleted {deleted_re} existing shadow discovery RankingEvents")

    # Load user affinities from PersonaDimension
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

    # Load all shadow users with their trips
    user_trips = await conn.fetch(
        """
        SELECT u."id" as user_id, t."id" as trip_id, t."city"
        FROM "User" u
        JOIN "Trip" t ON t."userId" = u."id"
        WHERE u."email" LIKE 'shadow-%'
        ORDER BY u."id", t."createdAt"
        """
    )

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

    # Select ~30% of users (deterministic)
    all_user_ids = list(dict.fromkeys(ut["user_id"] for ut in user_trips))
    rng = random.Random(42)
    selected_user_count = max(1, int(len(all_user_ids) * 0.30))
    selected_users = set(rng.sample(all_user_ids, selected_user_count))

    now = datetime.utcnow()
    signal_count = 0
    ranking_count = 0
    skipped_no_affinities = 0

    # Group trips by user
    from collections import defaultdict
    user_trip_map: dict[str, list] = defaultdict(list)
    for ut in user_trips:
        user_trip_map[ut["user_id"]].append(ut)

    # Batch signals for executemany
    signal_batch = []
    ranking_batch = []

    for user_idx, user_id in enumerate(all_user_ids):
        if user_id not in selected_users:
            continue

        affinities = user_affinities.get(user_id)
        if not affinities:
            skipped_no_affinities += 1
            continue

        # Per-user noise floor: +-15% jitter on thresholds (seeded from user index)
        user_rng = random.Random(42 + user_idx)
        noise = user_rng.uniform(-0.15, 0.15)

        for trip in user_trip_map[user_id]:
            city = trip["city"]
            nodes = city_nodes.get(city, [])
            if len(nodes) < 15:
                # Not enough nodes for a discovery session
                continue

            # Pick 15 nodes (mix of high and low affinity)
            scored = []
            for node in nodes:
                aff = affinities.get(node["category"], 0.3)
                scored.append((node["id"], aff))
            scored.sort(key=lambda x: x[1], reverse=True)

            # Mix: 8 high + 7 low for realistic discovery surface
            high = scored[:8]
            low = scored[-7:] if len(scored) >= 15 else scored[8:15]
            session_nodes = high + low
            user_rng.shuffle(session_nodes)

            swipe_rights = []
            for node_id, aff in session_nodes:
                adjusted_aff = aff + noise
                roll = user_rng.random()

                if adjusted_aff > 0.6:
                    is_right = roll < 0.65
                elif adjusted_aff > 0.3:
                    is_right = roll < 0.40
                else:
                    is_right = roll < 0.08

                if is_right:
                    signal_batch.append((
                        str(uuid.uuid4()), user_id, trip["trip_id"],
                        None, node_id, "discover_swipe_right", 1.0,
                        "pre_trip", "discover_swipe_right", now,
                    ))
                    signal_count += 1
                    swipe_rights.append(node_id)

                    # Shortlist chance for high-affinity right-swipes
                    if aff > 0.7 and user_rng.random() < 0.30:
                        signal_batch.append((
                            str(uuid.uuid4()), user_id, trip["trip_id"],
                            None, node_id, "discover_shortlist", 1.0,
                            "pre_trip", "discover_shortlist", now,
                        ))
                        signal_count += 1
                else:
                    signal_batch.append((
                        str(uuid.uuid4()), user_id, trip["trip_id"],
                        None, node_id, "discover_swipe_left", -1.0,
                        "pre_trip", "discover_swipe_left", now,
                    ))
                    signal_count += 1

            # One RankingEvent per discovery session
            candidate_ids = [nid for nid, _ in session_nodes]
            ranked_ids = [nid for nid, _ in sorted(session_nodes, key=lambda x: x[1], reverse=True)]
            ranking_batch.append((
                str(uuid.uuid4()), user_id, trip["trip_id"],
                0,  # dayNumber=0 for discovery
                "llm_ranker", "0.1.0",
                candidate_ids, ranked_ids, swipe_rights,
                "discovery", [], user_rng.randint(200, 800), now,
            ))
            ranking_count += 1

    # Batch insert signals
    if signal_batch:
        await conn.executemany(
            """
            INSERT INTO "BehavioralSignal" (
                "id", "userId", "tripId", "slotId", "activityNodeId",
                "signalType", "signalValue", "tripPhase", "rawAction", "createdAt"
            ) VALUES ($1, $2, $3, $4, $5, $6::\"SignalType\", $7, $8::\"TripPhase\", $9, $10)
            """,
            signal_batch,
        )

    # Batch insert ranking events
    if ranking_batch:
        await conn.executemany(
            """
            INSERT INTO "RankingEvent" (
                "id", "userId", "tripId", "dayNumber",
                "modelName", "modelVersion",
                "candidateIds", "rankedIds", "selectedIds",
                "surface", "shadowRankedIds", "latencyMs", "createdAt"
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            ranking_batch,
        )

    if skipped_no_affinities > 10:
        result.errors.append(
            f"Discovery: {skipped_no_affinities} users skipped (no category_affinities)"
        )
    elif skipped_no_affinities > 0:
        logger.warning(
            f"Discovery: {skipped_no_affinities} users skipped (no category_affinities)"
        )

    logger.info(
        f"Created {signal_count} discovery signals + {ranking_count} discovery RankingEvents"
    )
    return signal_count


# ---------------------------------------------------------------------------
# Enrichment 4: WeatherContext backfill
# ---------------------------------------------------------------------------

# Weather data by city and month (design doc spec)
# Format: label|temp_c|precip_index
WEATHER_TABLE: dict[str, dict[int, str]] = {
    "Tokyo": {
        1: "cold_clear|6|0.1", 2: "cold_clear|6|0.1",
        3: "mild_sunny|15|0.2", 4: "mild_sunny|15|0.2",
        5: "warm_humid|22|0.3",
        6: "rainy_warm|24|0.7",
        7: "hot_humid|30|0.5", 8: "hot_humid|30|0.5",
        9: "warm_rainy|26|0.6",
        10: "mild_sunny|17|0.2", 11: "mild_sunny|17|0.2",
        12: "cold_clear|8|0.1",
    },
    "New York City": {
        1: "cold_clear|2|0.2", 2: "cold_clear|2|0.2",
        3: "cool_windy|10|0.3", 4: "cool_windy|10|0.3",
        5: "warm_sunny|22|0.2", 6: "warm_sunny|22|0.2",
        7: "hot_humid|29|0.3", 8: "hot_humid|29|0.3",
        9: "mild_sunny|18|0.2", 10: "mild_sunny|18|0.2",
        11: "cool_cloudy|8|0.4",
        12: "cold_clear|3|0.3",
    },
    "Mexico City": {
        1: "dry_warm|22|0.1", 2: "dry_warm|22|0.1",
        3: "dry_warm|22|0.1", 4: "dry_warm|22|0.1",
        5: "dry_warm|22|0.1",
        6: "rainy_warm|20|0.6", 7: "rainy_warm|20|0.6",
        8: "rainy_warm|20|0.6", 9: "rainy_warm|20|0.6",
        10: "rainy_warm|20|0.6",
        11: "dry_cool|17|0.1", 12: "dry_cool|17|0.1",
    },
}

# City name normalization (persona seeder may use different names)
CITY_NAME_MAP = {
    "NYC": "New York City",
    "New York": "New York City",
    "CDMX": "Mexico City",
    "Ciudad de Mexico": "Mexico City",
}


async def _backfill_weather_context(conn: asyncpg.Connection) -> int:
    """Backfill weatherContext on outdoor/active signals with slotId.

    Join: BehavioralSignal -> ItinerarySlot (dayNumber) -> Trip (startDate, city).
    Only signals with a slotId. Pipe-delimited format: label|temp_c|precip_index.

    WHERE weatherContext IS NULL — safe to re-run.
    """
    # Get outdoor/active signals needing weather, with trip context
    rows = await conn.fetch(
        """
        SELECT
            bs."id" as signal_id,
            t."city",
            t."startDate" as start_date,
            slot."dayNumber" as day_number
        FROM "BehavioralSignal" bs
        JOIN "ItinerarySlot" slot ON slot."id" = bs."slotId"
        JOIN "Trip" t ON t."id" = bs."tripId"
        JOIN "ActivityNode" an ON an."id" = bs."activityNodeId"
        JOIN "User" u ON u."id" = bs."userId"
        WHERE u."email" LIKE 'shadow-%'
        AND bs."weatherContext" IS NULL
        AND bs."slotId" IS NOT NULL
        AND an."category" IN ('outdoors', 'active')
        """
    )

    if not rows:
        logger.info("No outdoor/active signals need weather backfill")
        return 0

    # Build update batches by weather string
    updates_by_weather: dict[str, list[str]] = {}

    for row in rows:
        city_raw = row["city"]
        city = CITY_NAME_MAP.get(city_raw, city_raw)
        weather_data = WEATHER_TABLE.get(city)
        if not weather_data:
            continue

        start_date = row["start_date"]
        day_number = row["day_number"]
        signal_date = start_date + timedelta(days=day_number)
        month = signal_date.month

        weather_str = weather_data.get(month)
        if not weather_str:
            continue

        if weather_str not in updates_by_weather:
            updates_by_weather[weather_str] = []
        updates_by_weather[weather_str].append(row["signal_id"])

    # Batch UPDATE by weather string (fewer queries than one per signal)
    count = 0
    for weather_str, signal_ids in updates_by_weather.items():
        result = await conn.execute(
            """
            UPDATE "BehavioralSignal"
            SET "weatherContext" = $1
            WHERE "id" = ANY($2)
            """,
            weather_str,
            signal_ids,
        )
        count += int(result.split()[-1])

    logger.info(f"Updated weatherContext on {count} outdoor/active signals")
    return count


# ---------------------------------------------------------------------------
# Enrichment 6: Trip completion realism
# ---------------------------------------------------------------------------


async def _make_trips_realistic(conn: asyncpg.Connection) -> tuple[int, int]:
    """Rebalance trip statuses for realism.

    ~280 completed trips without post_trip signals -> status='planning'
    ~80 recent completed trips -> shortened duration (2-3 days)

    Check-before-write idempotency.
    """
    # Check if we've already run (any shadow trips with status='planning')
    existing_planning = await conn.fetchval(
        """
        SELECT COUNT(*) FROM "Trip" t
        JOIN "User" u ON u."id" = t."userId"
        WHERE u."email" LIKE 'shadow-%'
        AND t."status" = 'planning'
        """
    )

    abandoned_count = 0
    if existing_planning == 0:
        # Find completed trips with NO post_trip phase signals
        abandoned_candidates = await conn.fetch(
            """
            SELECT t."id" as trip_id
            FROM "Trip" t
            JOIN "User" u ON u."id" = t."userId"
            WHERE u."email" LIKE 'shadow-%'
            AND t."status" = 'completed'
            AND t."id" NOT IN (
                SELECT DISTINCT "tripId" FROM "BehavioralSignal"
                WHERE "tripPhase" = 'post_trip'
                AND "tripId" IS NOT NULL
            )
            ORDER BY t."createdAt" ASC
            LIMIT 280
            """
        )

        if abandoned_candidates:
            trip_ids = [r["trip_id"] for r in abandoned_candidates]
            result = await conn.execute(
                """
                UPDATE "Trip"
                SET "status" = 'planning'::"TripStatus",
                    "completedAt" = NULL
                WHERE "id" = ANY($1)
                """,
                trip_ids,
            )
            abandoned_count = int(result.split()[-1])
            logger.info(f"Flipped {abandoned_count} trips to 'planning' (abandoned)")

    # Check if we've already shortened (any shadow trips with duration <= 2 days)
    existing_short = await conn.fetchval(
        """
        SELECT COUNT(*) FROM "Trip" t
        JOIN "User" u ON u."id" = t."userId"
        WHERE u."email" LIKE 'shadow-%'
        AND (t."endDate" - t."startDate") <= INTERVAL '2 days'
        """
    )

    shortened_count = 0
    if existing_short == 0:
        # Find recent completed trips (30-90 days ago)
        now = datetime.utcnow()
        recent_candidates = await conn.fetch(
            """
            SELECT t."id" as trip_id, t."startDate" as start_date
            FROM "Trip" t
            JOIN "User" u ON u."id" = t."userId"
            WHERE u."email" LIKE 'shadow-%'
            AND t."status" = 'completed'
            AND t."startDate" >= $1
            AND t."startDate" <= $2
            ORDER BY t."startDate" DESC
            LIMIT 80
            """,
            now - timedelta(days=90),
            now - timedelta(days=30),
        )

        rng = random.Random(42)
        for trip in recent_candidates:
            short_days = rng.randint(2, 3)
            new_end = trip["start_date"] + timedelta(days=short_days)
            await conn.execute(
                """
                UPDATE "Trip"
                SET "endDate" = $1
                WHERE "id" = $2
                """,
                new_end,
                trip["trip_id"],
            )
            shortened_count += 1

        if shortened_count > 0:
            logger.info(f"Shortened {shortened_count} trips to 2-3 days")

    return abandoned_count, shortened_count


# ---------------------------------------------------------------------------
# Enrichment entry point
# ---------------------------------------------------------------------------


async def enrich_training_data(pool: asyncpg.Pool) -> TrainingDataResult:
    """Run all 5 training data enrichments in sequence.

    Order matters:
    1. PivotEvent records (reads ItinerarySlot swaps)
    2. IntentionSignal seeding (reads BehavioralSignal skips)
    3. Discovery swipe signals (reads PersonaDimension affinities + ActivityNodes)
    4. WeatherContext backfill (UPDATE only, no deletes)
    5. Trip completion realism (UPDATE only, no deletes)
    """
    result = TrainingDataResult()

    async with pool.acquire() as conn:
        # Enrichment 1: PivotEvents (DELETE + re-INSERT)
        try:
            async with conn.transaction():
                result.pivot_events_created = await _seed_pivot_events(conn)
        except Exception as e:
            msg = f"PivotEvent seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Enrichment 2: IntentionSignals (DELETE + re-INSERT)
        try:
            async with conn.transaction():
                result.intention_signals_created = await _seed_intention_signals(conn)
        except Exception as e:
            msg = f"IntentionSignal seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Enrichment 3: Discovery signals (DELETE + re-INSERT)
        try:
            async with conn.transaction():
                result.discovery_signals_created = await _seed_discovery_signals(conn, result)
        except Exception as e:
            msg = f"Discovery signal seeding failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Enrichment 4: WeatherContext backfill (UPDATE, no transaction needed)
        try:
            result.weather_signals_updated = await _backfill_weather_context(conn)
        except Exception as e:
            msg = f"WeatherContext backfill failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

        # Enrichment 5: Trip completion realism (UPDATE, no transaction needed)
        try:
            abandoned, shortened = await _make_trips_realistic(conn)
            result.trips_made_abandoned = abandoned
            result.trips_made_recent = shortened
        except Exception as e:
            msg = f"Trip completion realism failed: {e}"
            logger.error(msg)
            result.errors.append(msg)

    logger.info(
        f"Enrichment complete: "
        f"{result.pivot_events_created} pivots, "
        f"{result.intention_signals_created} intentions, "
        f"{result.discovery_signals_created} discovery signals, "
        f"{result.weather_signals_updated} weather updates, "
        f"{result.trips_made_abandoned} abandoned trips, "
        f"{result.trips_made_recent} shortened trips"
    )
    return result


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
