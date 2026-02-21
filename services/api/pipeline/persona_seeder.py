"""
Cartesian persona seeder for shadow model training.

Generates realistic user profiles from a cartesian product of 5 behavioral
axes: primary_interest x pace x budget x social_mode x time_orientation.
Each combo produces a unique affinity vector across 11 activity categories,
driving confirm/skip/love/dislike signal distributions for BPR training.

Axes (6 x 3 x 3 x 3 x 2 = 324 raw, ~300 after pruning):
  - primary_interest: food, culture, nightlife, outdoors, wellness, adventure
  - pace: slow, moderate, packed
  - budget: low, mid, high
  - social_mode: solo, couple, group
  - time_orientation: early_bird, night_owl

Affinity computation:
  1. Base vector per primary_interest (11-dim, peaks at 0.70-0.80)
  2. Additive deltas per modifier axis (stronger: +/-0.15-0.25)
  3. Per-user jitter +/-0.05
  4. Clamp to [0.05, 0.98]

Fixes from review:
  - Wider deltas so BPR sees 300 distinct clusters, not 6
  - Item exposure separated from outcome (more uniform sampling)
  - Item-level variance via per-node affinity jitter
  - post_loved/post_disliked double-roll bug fixed
  - Swap signals for stronger preference pairs
  - Transaction per user for clean rollback on crash
  - Idempotent rerun: skip trips for existing users

Usage:
    pool = await asyncpg.create_pool(DATABASE_URL)
    result = await seed_personas(pool, cities=["Tokyo", "New York"])
"""

import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import product
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Activity categories (matches Prisma ActivityCategory enum)
# ---------------------------------------------------------------------------

ALL_CATEGORIES = [
    "dining", "drinks", "culture", "outdoors", "active",
    "entertainment", "shopping", "experience", "nightlife",
    "group_activity", "wellness",
]

# ---------------------------------------------------------------------------
# Axis definitions
# ---------------------------------------------------------------------------

PRIMARY_INTERESTS = ["food", "culture", "nightlife", "outdoors", "wellness", "adventure"]
PACES = ["slow", "moderate", "packed"]
BUDGETS = ["low", "mid", "high"]
SOCIAL_MODES = ["solo", "couple", "group"]
TIME_ORIENTATIONS = ["early_bird", "night_owl"]

# ---------------------------------------------------------------------------
# Base vectors per primary interest (peaks at 0.70-0.80, not 0.85-0.95)
# Lower peaks leave room for modifier axes to create real separation.
# ---------------------------------------------------------------------------

BASE_VECTORS: dict[str, dict[str, float]] = {
    "food": {
        "dining": 0.80, "drinks": 0.65, "culture": 0.30, "outdoors": 0.20,
        "active": 0.15, "entertainment": 0.35, "shopping": 0.25,
        "experience": 0.45, "nightlife": 0.50, "group_activity": 0.25,
        "wellness": 0.15,
    },
    "culture": {
        "dining": 0.45, "drinks": 0.25, "culture": 0.80, "outdoors": 0.40,
        "active": 0.20, "entertainment": 0.35, "shopping": 0.30,
        "experience": 0.65, "nightlife": 0.10, "group_activity": 0.20,
        "wellness": 0.35,
    },
    "nightlife": {
        "dining": 0.60, "drinks": 0.78, "culture": 0.10, "outdoors": 0.08,
        "active": 0.12, "entertainment": 0.60, "shopping": 0.20,
        "experience": 0.40, "nightlife": 0.80, "group_activity": 0.45,
        "wellness": 0.08,
    },
    "outdoors": {
        "dining": 0.40, "drinks": 0.25, "culture": 0.35, "outdoors": 0.80,
        "active": 0.65, "entertainment": 0.20, "shopping": 0.15,
        "experience": 0.55, "nightlife": 0.15, "group_activity": 0.35,
        "wellness": 0.45,
    },
    "wellness": {
        "dining": 0.45, "drinks": 0.20, "culture": 0.45, "outdoors": 0.70,
        "active": 0.50, "entertainment": 0.15, "shopping": 0.25,
        "experience": 0.40, "nightlife": 0.05, "group_activity": 0.12,
        "wellness": 0.80,
    },
    "adventure": {
        "dining": 0.35, "drinks": 0.30, "culture": 0.25, "outdoors": 0.70,
        "active": 0.80, "entertainment": 0.30, "shopping": 0.12,
        "experience": 0.70, "nightlife": 0.30, "group_activity": 0.40,
        "wellness": 0.25,
    },
}

# ---------------------------------------------------------------------------
# Modifier deltas (stronger than v1: +/-0.15-0.25 range)
# ---------------------------------------------------------------------------

PACE_MODIFIERS: dict[str, dict[str, float]] = {
    "slow": {
        "active": -0.20, "nightlife": -0.15, "wellness": +0.15,
        "culture": +0.15, "shopping": -0.10,
    },
    "moderate": {},
    "packed": {
        "active": +0.15, "nightlife": +0.10, "shopping": +0.15,
        "experience": +0.15, "wellness": -0.10, "culture": -0.05,
    },
}

BUDGET_MODIFIERS: dict[str, dict[str, float]] = {
    "low": {
        "dining": -0.15, "wellness": -0.20, "shopping": -0.20,
        "drinks": -0.10, "outdoors": +0.15, "active": +0.15,
        "entertainment": -0.10,
    },
    "mid": {},
    "high": {
        "dining": +0.15, "wellness": +0.20, "shopping": +0.15,
        "entertainment": +0.15, "experience": +0.10, "drinks": +0.10,
    },
}

SOCIAL_MODIFIERS: dict[str, dict[str, float]] = {
    "solo": {
        "group_activity": -0.25, "wellness": +0.10, "culture": +0.10,
        "nightlife": -0.10,
    },
    "couple": {
        "group_activity": -0.15, "dining": +0.10, "entertainment": +0.10,
        "experience": +0.05,
    },
    "group": {
        "group_activity": +0.30, "nightlife": +0.15, "entertainment": +0.15,
        "drinks": +0.15, "wellness": -0.15, "culture": -0.10,
    },
}

TIME_MODIFIERS: dict[str, dict[str, float]] = {
    "early_bird": {
        "outdoors": +0.15, "culture": +0.10, "wellness": +0.15,
        "nightlife": -0.20, "drinks": -0.15, "active": +0.10,
    },
    "night_owl": {
        "nightlife": +0.20, "drinks": +0.20, "dining": +0.10,
        "outdoors": -0.15, "wellness": -0.15, "culture": -0.10,
    },
}

# ---------------------------------------------------------------------------
# Pace-derived parameters
# ---------------------------------------------------------------------------

PACE_PARAMS: dict[str, dict[str, tuple[int, int]]] = {
    "slow": {"slots_per_day": (2, 4), "trips_range": (2, 4)},
    "moderate": {"slots_per_day": (4, 6), "trips_range": (2, 5)},
    "packed": {"slots_per_day": (6, 9), "trips_range": (3, 6)},
}

# ---------------------------------------------------------------------------
# Pruning rules
# ---------------------------------------------------------------------------

PRUNED_COMBOS: set[tuple[str, str, str, str, str]] = set()


def _is_pruned(interest: str, pace: str, budget: str, social: str, time: str) -> bool:
    """Light pruning: remove truly nonsensical combos."""
    # Wellness + packed: wellness travelers don't pack 8 slots/day
    if interest == "wellness" and pace == "packed":
        return True
    # Wellness + low budget: spa/onsen/yoga are inherently mid-to-high
    if interest == "wellness" and budget == "low":
        return True
    # Nightlife primary + early_bird: early birds don't center nightlife
    if interest == "nightlife" and time == "early_bird":
        return True
    # Adventure primary + slow: adventure seekers aren't doing 3 slots/day
    if interest == "adventure" and pace == "slow":
        return True
    return False


# ---------------------------------------------------------------------------
# Archetype generator
# ---------------------------------------------------------------------------

def _compute_affinities(
    interest: str, pace: str, budget: str, social: str, time: str,
) -> dict[str, float]:
    """Compute affinity vector from axis combination."""
    base = dict(BASE_VECTORS[interest])

    # Apply all modifier deltas
    for modifiers in [
        PACE_MODIFIERS[pace],
        BUDGET_MODIFIERS[budget],
        SOCIAL_MODIFIERS[social],
        TIME_MODIFIERS[time],
    ]:
        for cat, delta in modifiers.items():
            base[cat] = base.get(cat, 0.3) + delta

    # Clamp to [0.05, 0.98]
    return {cat: max(0.05, min(0.98, val)) for cat, val in base.items()}


def _apply_user_jitter(affinities: dict[str, float], jitter: float = 0.05) -> dict[str, float]:
    """Add per-user random jitter to prevent identical signal histories."""
    return {
        cat: max(0.05, min(0.98, val + random.uniform(-jitter, jitter)))
        for cat, val in affinities.items()
    }


def _combo_key(interest: str, pace: str, budget: str, social: str, time: str) -> str:
    """Generate a stable key for a cartesian combo."""
    return f"{interest}_{pace}_{budget}_{social}_{time}"


def _combo_description(interest: str, pace: str, budget: str, social: str, time: str) -> str:
    """Human-readable description for logs."""
    return (
        f"{interest.replace('_', ' ').title()} traveler | "
        f"{pace} pace | {budget} budget | {social} | {time.replace('_', ' ')}"
    )


def _build_persona_seed(
    interest: str, pace: str, budget: str, social: str, time: str,
) -> dict[str, Any]:
    """Build the persona_seed JSON that gets stored on Trip/TripMember."""
    food_chips_map = {
        "food": ["authentic", "hole-in-the-wall", "adventurous"],
        "culture": ["traditional", "local", "historic-setting"],
        "nightlife": ["late-night", "street-food", "izakaya"],
        "outdoors": ["farm-to-table", "picnic", "market"],
        "wellness": ["healthy", "organic", "tea-house"],
        "adventure": ["street-food", "exotic", "local-favorite"],
    }
    cuisine_openness_map = {
        "food": 0.90, "culture": 0.65, "nightlife": 0.75,
        "outdoors": 0.60, "wellness": 0.55, "adventure": 0.80,
    }
    pace_label_map = {"slow": "leisurely", "moderate": "moderate", "packed": "fast"}
    morning_map = {"early_bird": "early_bird", "night_owl": "late_riser"}
    radius_map = {
        "slow": "neighborhood", "moderate": "district", "packed": "city_wide",
    }

    return {
        "pace": pace_label_map[pace],
        "morningPreference": morning_map[time],
        "foodChips": food_chips_map.get(interest, ["local", "popular"]),
        "cuisine_openness": cuisine_openness_map.get(interest, 0.60),
        "budget_tier": budget,
        "social_mode": social,
        "exploration_radius": radius_map[pace],
        "primary_interest": interest,
        "time_orientation": time,
    }


def generate_archetypes() -> dict[str, dict[str, Any]]:
    """Generate all cartesian archetype combos, pruning nonsensical ones."""
    archetypes: dict[str, dict[str, Any]] = {}

    for interest, pace, budget, social, time in product(
        PRIMARY_INTERESTS, PACES, BUDGETS, SOCIAL_MODES, TIME_ORIENTATIONS
    ):
        if _is_pruned(interest, pace, budget, social, time):
            continue

        key = _combo_key(interest, pace, budget, social, time)
        params = PACE_PARAMS[pace]

        archetypes[key] = {
            "description": _combo_description(interest, pace, budget, social, time),
            "persona_seed": _build_persona_seed(interest, pace, budget, social, time),
            "category_affinities": _compute_affinities(interest, pace, budget, social, time),
            "trips_range": params["trips_range"],
            "slots_per_day": params["slots_per_day"],
        }

    return archetypes


# ---------------------------------------------------------------------------
# City configs for trip generation
# ---------------------------------------------------------------------------

CITY_CONFIGS: dict[str, dict[str, str]] = {
    "Tokyo": {"country": "Japan", "timezone": "Asia/Tokyo"},
    "New York": {"country": "United States", "timezone": "America/New_York"},
    "Mexico City": {"country": "Mexico", "timezone": "America/Mexico_City"},
    "San Francisco": {"country": "United States", "timezone": "America/Los_Angeles"},
    "Seoul": {"country": "South Korea", "timezone": "Asia/Seoul"},
    "London": {"country": "United Kingdom", "timezone": "Europe/London"},
    "Paris": {"country": "France", "timezone": "Europe/Paris"},
}

# Signal type constants
POSITIVE_SIGNALS = ["slot_confirm", "slot_complete", "post_loved"]
NEGATIVE_SIGNALS = ["slot_skip", "discover_swipe_left", "post_disliked"]
PASSIVE_SIGNALS = ["slot_view", "slot_dwell", "dwell_time", "scroll_depth"]


@dataclass
class SeedResult:
    users_created: int = 0
    users_skipped: int = 0
    trips_created: int = 0
    slots_created: int = 0
    signals_created: int = 0
    swaps_created: int = 0
    archetypes_total: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core seeding logic
# ---------------------------------------------------------------------------


async def seed_personas(
    pool: asyncpg.Pool,
    cities: list[str] | None = None,
    personas_per_archetype: int = 3,
    skip_llm: bool = True,
) -> SeedResult:
    """
    Seed fake personas with trips and behavioral signals.

    Generates a cartesian product of behavioral axes, computes affinity
    vectors, and creates users with realistic signal distributions.
    """
    if cities is None:
        cities = ["Tokyo"]

    result = SeedResult()
    archetypes = generate_archetypes()
    result.archetypes_total = len(archetypes)

    # Fetch existing activity nodes per city
    city_nodes: dict[str, list[dict]] = {}
    async with pool.acquire() as conn:
        for city in cities:
            rows = await conn.fetch(
                """
                SELECT "id", "name", "category", "neighborhood",
                       "convergenceScore", "priceLevel"
                FROM "ActivityNode"
                WHERE "city" = $1 AND "status" != 'archived'
                """,
                city,
            )
            city_nodes[city] = [dict(r) for r in rows]
            logger.info(f"Found {len(rows)} activity nodes for {city}")

    valid_cities = [c for c in cities if len(city_nodes.get(c, [])) >= 5]
    if not valid_cities:
        result.errors.append(
            f"No cities with enough activity nodes. Available: {list(city_nodes.keys())}"
        )
        return result

    logger.info(
        f"Seeding {len(archetypes)} archetypes x "
        f"{personas_per_archetype} users across {valid_cities}"
    )

    for archetype_name, archetype in archetypes.items():
        for i in range(personas_per_archetype):
            try:
                user_result = await _seed_single_persona(
                    pool, archetype_name, archetype, i, valid_cities, city_nodes
                )
                result.users_created += user_result.users_created
                result.users_skipped += user_result.users_skipped
                result.trips_created += user_result.trips_created
                result.slots_created += user_result.slots_created
                result.signals_created += user_result.signals_created
                result.swaps_created += user_result.swaps_created
            except Exception as e:
                msg = f"Failed seeding {archetype_name}#{i}: {e}"
                logger.error(msg)
                result.errors.append(msg)

    logger.info(
        f"Persona seeding complete: {result.users_created} users "
        f"({result.users_skipped} skipped existing), "
        f"{result.trips_created} trips, {result.slots_created} slots, "
        f"{result.signals_created} signals, {result.swaps_created} swaps"
    )
    return result


async def _seed_single_persona(
    pool: asyncpg.Pool,
    archetype_name: str,
    archetype: dict[str, Any],
    index: int,
    cities: list[str],
    city_nodes: dict[str, list[dict]],
) -> SeedResult:
    """Create one user with trips and signals for an archetype."""
    result = SeedResult()
    email = f"shadow-{archetype_name}-{index:03d}@overplanned.test"

    # Apply per-user jitter to base affinities
    jittered_affinities = _apply_user_jitter(archetype["category_affinities"])
    user_archetype = {**archetype, "category_affinities": jittered_affinities}

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Upsert user — get the actual ID (handles reruns)
            user_id = await conn.fetchval(
                """
                INSERT INTO "User" (
                    "id", "email", "name", "subscriptionTier", "systemRole",
                    "onboardingComplete", "createdAt", "updatedAt"
                ) VALUES ($1, $2, $3, 'beta', 'user', true, $4, $4)
                ON CONFLICT ("email") DO UPDATE SET "updatedAt" = "User"."updatedAt"
                RETURNING "id"
                """,
                str(uuid.uuid4()),
                email,
                f"Shadow {archetype_name.replace('_', ' ').title()} #{index}",
                datetime.utcnow(),
            )

            # Check if this user already has trips (rerun detection)
            existing_trips = await conn.fetchval(
                'SELECT COUNT(*) FROM "Trip" WHERE "userId" = $1',
                user_id,
            )
            if existing_trips > 0:
                result.users_skipped = 1
                return result

            result.users_created = 1

            # Generate trips
            min_trips, max_trips = user_archetype["trips_range"]
            num_trips = random.randint(min_trips, max_trips)

            for trip_idx in range(num_trips):
                city = random.choice(cities)
                city_cfg = CITY_CONFIGS.get(
                    city, {"country": "Unknown", "timezone": "UTC"}
                )
                nodes = city_nodes[city]

                trip_result = await _seed_trip_with_signals(
                    conn, user_id, city, city_cfg, nodes, user_archetype, trip_idx
                )
                result.trips_created += trip_result.trips_created
                result.slots_created += trip_result.slots_created
                result.signals_created += trip_result.signals_created
                result.swaps_created += trip_result.swaps_created

    return result


async def _seed_trip_with_signals(
    conn: asyncpg.Connection,
    user_id: str,
    city: str,
    city_cfg: dict[str, str],
    nodes: list[dict],
    archetype: dict[str, Any],
    trip_idx: int,
) -> SeedResult:
    """Create a single trip with itinerary slots and behavioral signals."""
    result = SeedResult()
    trip_id = str(uuid.uuid4())

    days_ago = random.randint(7, 180)
    trip_duration = random.randint(3, 8)
    start_date = datetime.utcnow() - timedelta(days=days_ago)
    end_date = start_date + timedelta(days=trip_duration)

    if days_ago > trip_duration:
        status = "completed"
    else:
        status = "active"

    social = archetype["persona_seed"].get("social_mode", "solo")
    mode = "group" if social == "group" else "solo"

    await conn.execute(
        """
        INSERT INTO "Trip" (
            "id", "userId", "mode", "status", "destination",
            "city", "country", "timezone",
            "startDate", "endDate", "personaSeed",
            "createdAt", "updatedAt"
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $12)
        """,
        trip_id,
        user_id,
        mode,
        status,
        f"{city}, {city_cfg['country']}",
        city,
        city_cfg["country"],
        city_cfg["timezone"],
        start_date,
        end_date,
        json.dumps(archetype["persona_seed"]),
        datetime.utcnow(),
    )

    await conn.execute(
        """
        INSERT INTO "TripMember" (
            "id", "tripId", "userId", "role", "status",
            "personaSeed", "joinedAt", "createdAt"
        ) VALUES ($1, $2, $3, 'organizer', 'joined', $4, $5, $5)
        """,
        str(uuid.uuid4()),
        trip_id,
        user_id,
        json.dumps(archetype["persona_seed"]),
        start_date,
    )
    result.trips_created = 1

    min_slots, max_slots = archetype["slots_per_day"]
    affinities = archetype["category_affinities"]

    for day in range(1, trip_duration + 1):
        num_slots = random.randint(min_slots, max_slots)

        # Item exposure: more uniform sampling (sqrt-dampened weights)
        # Then outcome is driven purely by affinity.
        # This ensures low-affinity items get exposure for BPR negatives.
        day_nodes = _pick_nodes_uniform_exposure(nodes, affinities, num_slots)

        for sort_order, node in enumerate(day_nodes):
            slot_id = str(uuid.uuid4())
            slot_type = _infer_slot_type(node["category"])

            category = node["category"]
            affinity = affinities.get(category, 0.3)

            # Item-level variance: each node gets its own jitter
            # so BPR can learn item embeddings, not just category embeddings
            item_jitter = random.gauss(0, 0.08)
            item_affinity = max(0.05, min(0.98, affinity + item_jitter))

            # Day fatigue factor (day 3 most reliable)
            fatigue_factor = 1.0 - (abs(day - 3) * 0.05)
            adjusted_affinity = max(0.05, min(0.98, item_affinity * fatigue_factor))

            # Roll outcome
            roll = random.random()
            if roll < adjusted_affinity:
                slot_status = "completed" if status == "completed" else "confirmed"
            elif roll < adjusted_affinity + 0.15:
                slot_status = "skipped"
            else:
                slot_status = "proposed"

            slot_time = start_date + timedelta(
                days=day - 1, hours=8 + sort_order * 2
            )

            # Swap logic: ~10% of skipped slots get swapped for a
            # different-category node (generates strong preference pairs)
            was_swapped = False
            if slot_status == "skipped" and random.random() < 0.10:
                swap_node = _pick_swap_node(nodes, affinities, category)
                if swap_node:
                    was_swapped = True

            await conn.execute(
                """
                INSERT INTO "ItinerarySlot" (
                    "id", "tripId", "activityNodeId", "dayNumber",
                    "sortOrder", "slotType", "status",
                    "startTime", "durationMinutes",
                    "isLocked", "isContested", "wasSwapped",
                    "createdAt", "updatedAt"
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    false, false, $10, $11, $11
                )
                """,
                slot_id,
                trip_id,
                node["id"],
                day,
                sort_order,
                slot_type,
                slot_status,
                slot_time,
                random.choice([60, 90, 120]),
                was_swapped,
                datetime.utcnow(),
            )
            result.slots_created += 1

            # Generate behavioral signals
            signals = _generate_signals(
                user_id, trip_id, slot_id, node["id"],
                slot_status, adjusted_affinity, slot_time, status
            )
            for sig in signals:
                await conn.execute(
                    """
                    INSERT INTO "BehavioralSignal" (
                        "id", "userId", "tripId", "slotId",
                        "activityNodeId", "signalType", "signalValue",
                        "tripPhase", "rawAction", "createdAt"
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    str(uuid.uuid4()),
                    sig["userId"],
                    sig["tripId"],
                    sig["slotId"],
                    sig["activityNodeId"],
                    sig["signalType"],
                    sig["signalValue"],
                    sig["tripPhase"],
                    sig["rawAction"],
                    sig["createdAt"],
                )
                result.signals_created += 1

            # If swapped: create the replacement slot + confirm signal
            if was_swapped and swap_node:
                swap_slot_id = str(uuid.uuid4())
                swap_affinity = affinities.get(swap_node["category"], 0.5)

                await conn.execute(
                    """
                    INSERT INTO "ItinerarySlot" (
                        "id", "tripId", "activityNodeId", "dayNumber",
                        "sortOrder", "slotType", "status",
                        "startTime", "durationMinutes",
                        "isLocked", "isContested", "wasSwapped",
                        "createdAt", "updatedAt"
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, 'confirmed', $7, $8,
                        false, false, false, $9, $9
                    )
                    """,
                    swap_slot_id,
                    trip_id,
                    swap_node["id"],
                    day,
                    sort_order,
                    _infer_slot_type(swap_node["category"]),
                    slot_time,
                    random.choice([60, 90, 120]),
                    datetime.utcnow(),
                )
                result.slots_created += 1
                result.swaps_created += 1

                # Swap generates a confirm on the replacement
                await conn.execute(
                    """
                    INSERT INTO "BehavioralSignal" (
                        "id", "userId", "tripId", "slotId",
                        "activityNodeId", "signalType", "signalValue",
                        "tripPhase", "rawAction", "createdAt"
                    ) VALUES ($1, $2, $3, $4, $5, 'slot_confirm', 1.0, 'active', 'swap_confirm', $6)
                    """,
                    str(uuid.uuid4()),
                    user_id,
                    trip_id,
                    swap_slot_id,
                    swap_node["id"],
                    slot_time,
                )
                result.signals_created += 1

    # Post-trip reflections
    if status == "completed":
        post_signals = await _generate_post_trip_signals(
            conn, user_id, trip_id, affinities, end_date
        )
        result.signals_created += post_signals

    return result


# ---------------------------------------------------------------------------
# Node selection (improved: uniform exposure, affinity-driven outcome)
# ---------------------------------------------------------------------------


def _pick_nodes_uniform_exposure(
    nodes: list[dict],
    affinities: dict[str, float],
    count: int,
) -> list[dict]:
    """
    Pick nodes with more uniform category exposure.

    Uses sqrt-dampened affinity weights so low-affinity categories still
    get sampled (BPR needs to see items get both positive and negative
    signals from different users). The outcome (confirm/skip) is still
    driven by the full affinity value.
    """
    if not nodes:
        return []

    # Sqrt-dampen: a 0.80 affinity becomes 0.89 weight, a 0.10 becomes 0.32.
    # This flattens the distribution without making it fully uniform.
    weights = [max(0.1, affinities.get(n["category"], 0.3) ** 0.5) for n in nodes]

    # Weighted sample without replacement
    selected: list[dict] = []
    available = list(range(len(nodes)))
    available_weights = [weights[i] for i in available]

    for _ in range(min(count, len(nodes))):
        if not available:
            break
        total_w = sum(available_weights)
        if total_w == 0:
            break
        r = random.random() * total_w
        cumulative = 0.0
        for idx_pos, idx in enumerate(available):
            cumulative += available_weights[idx_pos]
            if cumulative >= r:
                selected.append(nodes[idx])
                available.pop(idx_pos)
                available_weights.pop(idx_pos)
                break

    return selected


def _pick_swap_node(
    nodes: list[dict],
    affinities: dict[str, float],
    original_category: str,
) -> dict | None:
    """Pick a replacement node from a higher-affinity category for swaps."""
    candidates = [
        n for n in nodes
        if n["category"] != original_category
        and affinities.get(n["category"], 0.3) > affinities.get(original_category, 0.3)
    ]
    if not candidates:
        return None
    return random.choice(candidates)


def _infer_slot_type(category: str) -> str:
    """Map ActivityCategory to SlotType."""
    mapping = {
        "dining": "meal",
        "drinks": "meal",
        "culture": "anchor",
        "outdoors": "anchor",
        "active": "anchor",
        "entertainment": "anchor",
        "shopping": "flex",
        "experience": "anchor",
        "nightlife": "flex",
        "group_activity": "anchor",
        "wellness": "flex",
    }
    return mapping.get(category, "flex")


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------


def _generate_signals(
    user_id: str,
    trip_id: str,
    slot_id: str,
    activity_node_id: str,
    slot_status: str,
    affinity: float,
    slot_time: datetime,
    trip_status: str,
) -> list[dict]:
    """Generate behavioral signals for a single slot interaction."""
    signals = []
    base = {
        "userId": user_id,
        "tripId": trip_id,
        "slotId": slot_id,
        "activityNodeId": activity_node_id,
    }

    # Only emit view signals for slots that were actually interacted with.
    # Proposed (never touched) slots don't get view signals — avoids
    # diluting BPR training data with noise.
    if slot_status in ("confirmed", "completed", "skipped"):
        signals.append({
            **base,
            "signalType": "slot_view",
            "signalValue": 1.0,
            "tripPhase": "pre_trip",
            "rawAction": "view_slot_detail",
            "createdAt": slot_time - timedelta(days=random.randint(1, 14)),
        })

    if slot_status in ("confirmed", "completed"):
        signals.append({
            **base,
            "signalType": "slot_confirm",
            "signalValue": 1.0,
            "tripPhase": "pre_trip",
            "rawAction": "confirm_slot",
            "createdAt": slot_time - timedelta(days=random.randint(1, 7)),
        })

        if slot_status == "completed":
            signals.append({
                **base,
                "signalType": "slot_complete",
                "signalValue": 1.0,
                "tripPhase": "active",
                "rawAction": "mark_complete",
                "createdAt": slot_time + timedelta(hours=random.randint(1, 3)),
            })

            dwell_minutes = int(affinity * 120 + random.gauss(0, 15))
            dwell_minutes = max(10, min(240, dwell_minutes))
            signals.append({
                **base,
                "signalType": "dwell_time",
                "signalValue": float(dwell_minutes),
                "tripPhase": "active",
                "rawAction": f"dwell_{dwell_minutes}m",
                "createdAt": slot_time + timedelta(minutes=dwell_minutes),
            })

    elif slot_status == "skipped":
        signals.append({
            **base,
            "signalType": "slot_skip",
            "signalValue": -1.0,
            "tripPhase": "active",
            "rawAction": "skip_slot",
            "createdAt": slot_time - timedelta(hours=random.randint(0, 2)),
        })

    return signals


async def _generate_post_trip_signals(
    conn: asyncpg.Connection,
    user_id: str,
    trip_id: str,
    affinities: dict[str, float],
    end_date: datetime,
) -> int:
    """Generate post-trip reflection signals (loved/disliked) for completed slots."""
    count = 0

    rows = await conn.fetch(
        """
        SELECT s."id" as slot_id, s."activityNodeId", n."category"
        FROM "ItinerarySlot" s
        JOIN "ActivityNode" n ON n."id" = s."activityNodeId"
        WHERE s."tripId" = $1 AND s."status" = 'completed'
        """,
        trip_id,
    )

    reflection_time = end_date + timedelta(days=random.randint(1, 5))

    for row in rows:
        affinity = affinities.get(row["category"], 0.5)

        # Fixed: single roll, proper if/elif (no double-roll bug)
        roll = random.random()
        if roll < affinity * 0.7:
            signal_type = "post_loved"
            signal_value = 1.0
            raw_action = "mark_loved"
        elif roll > 0.85:
            signal_type = "post_disliked"
            signal_value = -1.0
            raw_action = "mark_disliked"
        else:
            # No reflection (most common for mid-affinity)
            continue

        await conn.execute(
            """
            INSERT INTO "BehavioralSignal" (
                "id", "userId", "tripId", "slotId",
                "activityNodeId", "signalType", "signalValue",
                "tripPhase", "rawAction", "createdAt"
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'post_trip', $8, $9)
            """,
            str(uuid.uuid4()),
            user_id,
            trip_id,
            row["slot_id"],
            row["activityNodeId"],
            signal_type,
            signal_value,
            raw_action,
            reflection_time + timedelta(minutes=random.randint(0, 60)),
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# CLI / Router entry point
# ---------------------------------------------------------------------------


async def run_persona_seed(
    pool: asyncpg.Pool,
    cities: list[str] | None = None,
    personas_per_archetype: int = 3,
) -> SeedResult:
    """Entry point for admin router or CLI invocation."""
    logger.info("Starting cartesian persona seed...")
    return await seed_personas(
        pool, cities=cities, personas_per_archetype=personas_per_archetype
    )
