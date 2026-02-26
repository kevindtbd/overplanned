"""
Phase 3.4 — Synthetic Training Data Simulation.

Generates synthetic behavioral signals by simulating 12 travel archetypes
making decisions. Uses a two-agent loop:

  Agent 1 (Sonnet): Generates a simulated traveler's reactions to
      an itinerary slot. Produces free-text reactions as that archetype.

  Agent 2 (Haiku): Classifies those reactions into BehavioralSignal-
      compatible format (dimension, direction, confidence).

All synthetic data is tagged with source="synthetic_agent_v1" and
user IDs use the "synth-" prefix.

Security / safety:
  - Admin-only: raises PermissionError if is_admin=False
  - Budget cap: $100/day. Tracks cumulative spend. Aborts if exceeded.
  - Circuit breaker: 5 consecutive Haiku classification failures -> abort
  - Strict output validation: Haiku must return valid enums + confidence 0-1
  - Hard-coded archetype data — no user data interpolated into prompts

DB writes use raw asyncpg INSERT into behavioral_signals table.
All synthetic rows use signal_weight within [-1.0, 3.0] CHECK constraint.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SONNET_PROMPT_VERSION = "synthetic_simulation_sonnet_v1"
HAIKU_PROMPT_VERSION = "synthetic_simulation_haiku_v1"

SYNTHETIC_SOURCE = "synthetic_agent_v1"
SYNTH_ID_PREFIX = "synth-"

BUDGET_CAP_USD = 100.0          # per-run spend cap
CIRCUIT_BREAKER_THRESHOLD = 5   # consecutive Haiku failures -> abort

# Cost rates (per million tokens)
SONNET_INPUT_COST_PER_M = 3.0
SONNET_OUTPUT_COST_PER_M = 15.0
HAIKU_INPUT_COST_PER_M = 0.25
HAIKU_OUTPUT_COST_PER_M = 1.25

# Valid enum values for Haiku output validation
VALID_DIMENSIONS: frozenset[str] = frozenset({
    "food_priority",
    "nightlife_interest",
    "pace_preference",
    "budget_sensitivity",
    "outdoor_affinity",
    "cultural_depth",
    "social_energy",
    "adventure_tolerance",
})

VALID_DIRECTIONS: frozenset[str] = frozenset({"high", "low", "neutral"})

# BehavioralSignal.signal_weight CHECK constraint: [-1.0, 3.0]
SIGNAL_WEIGHT_MIN = -1.0
SIGNAL_WEIGHT_MAX = 3.0

# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------
#
# 12 hard-coded travel archetypes. Each has:
#   id           — unique slug used for synthetic user IDs
#   name         — display name
#   description  — personality descriptor used in Sonnet prompts
#   preferences  — dimension -> direction mapping
#   sample_cities — cities this archetype would typically visit
#
# NOTE: These are hard-coded. User data is NEVER interpolated here.

ARCHETYPES: list[dict[str, Any]] = [
    {
        "id": "budget_backpacker",
        "name": "Budget Backpacker",
        "description": (
            "A 20-something solo traveler maximizing destinations on minimal funds. "
            "Prefers hostels, street food, and free or cheap attractions. "
            "Values authentic local experiences over comfort or convenience."
        ),
        "preferences": {
            "budget_sensitivity": "high",
            "social_energy": "high",
            "outdoor_affinity": "neutral",
            "food_priority": "neutral",
            "nightlife_interest": "high",
            "pace_preference": "high",
            "cultural_depth": "high",
            "adventure_tolerance": "high",
        },
        "sample_cities": ["portland", "mexico-city", "austin"],
    },
    {
        "id": "luxury_foodie",
        "name": "Luxury Foodie",
        "description": (
            "A high-income traveler whose primary motivation is exceptional dining. "
            "Books restaurants months in advance, reads Michelin and Eater obsessively. "
            "Stays at boutique hotels, drinks natural wine, and skips tourist attractions."
        ),
        "preferences": {
            "food_priority": "high",
            "budget_sensitivity": "low",
            "nightlife_interest": "neutral",
            "outdoor_affinity": "low",
            "cultural_depth": "high",
            "pace_preference": "low",
            "social_energy": "neutral",
            "adventure_tolerance": "low",
        },
        "sample_cities": ["new-orleans", "mexico-city", "austin"],
    },
    {
        "id": "adventure_seeker",
        "name": "Adventure Seeker",
        "description": (
            "An adrenaline-driven traveler who prioritizes physical challenges. "
            "Hikes, climbs, bikes, kayaks, and seeks discomfort as a badge. "
            "Eats whatever is convenient and sleeps wherever is closest to the trailhead."
        ),
        "preferences": {
            "outdoor_affinity": "high",
            "adventure_tolerance": "high",
            "pace_preference": "high",
            "food_priority": "low",
            "budget_sensitivity": "neutral",
            "nightlife_interest": "low",
            "cultural_depth": "low",
            "social_energy": "neutral",
        },
        "sample_cities": ["bend", "asheville", "seattle"],
    },
    {
        "id": "culture_vulture",
        "name": "Culture Vulture",
        "description": (
            "A lifelong learner driven by history, art, and architecture. "
            "Spends full days in museums, reads travel history before each trip, "
            "and seeks out neighborhoods, not landmarks."
        ),
        "preferences": {
            "cultural_depth": "high",
            "food_priority": "neutral",
            "pace_preference": "low",
            "outdoor_affinity": "neutral",
            "nightlife_interest": "low",
            "budget_sensitivity": "neutral",
            "social_energy": "low",
            "adventure_tolerance": "neutral",
        },
        "sample_cities": ["mexico-city", "new-orleans", "asheville"],
    },
    {
        "id": "slow_traveler",
        "name": "Slow Traveler",
        "description": (
            "Someone who spends weeks in one neighborhood, shops at local markets, "
            "befriends the cafe owner, and avoids guidebooks entirely. "
            "Measures success by how un-touristy the experience feels."
        ),
        "preferences": {
            "pace_preference": "low",
            "cultural_depth": "high",
            "food_priority": "high",
            "outdoor_affinity": "neutral",
            "nightlife_interest": "low",
            "budget_sensitivity": "high",
            "social_energy": "high",
            "adventure_tolerance": "low",
        },
        "sample_cities": ["portland", "asheville", "seattle"],
    },
    {
        "id": "nightlife_hunter",
        "name": "Nightlife Hunter",
        "description": (
            "Travels primarily to experience the bar and club scene. "
            "Sleeps until noon, starts evenings at 10pm, and judges cities by their last call. "
            "Food is secondary — typically late-night tacos or whatever the bar serves."
        ),
        "preferences": {
            "nightlife_interest": "high",
            "food_priority": "neutral",
            "pace_preference": "high",
            "outdoor_affinity": "low",
            "cultural_depth": "low",
            "budget_sensitivity": "neutral",
            "social_energy": "high",
            "adventure_tolerance": "high",
        },
        "sample_cities": ["new-orleans", "austin", "portland"],
    },
    {
        "id": "family_planner",
        "name": "Family Planner",
        "description": (
            "A parent traveling with children aged 5-12. "
            "Prioritizes safety, accessibility, and activities that work for mixed ages. "
            "Prefers clear itineraries, predictable meals, and avoids nightlife and risk."
        ),
        "preferences": {
            "pace_preference": "low",
            "adventure_tolerance": "low",
            "food_priority": "high",
            "outdoor_affinity": "high",
            "nightlife_interest": "low",
            "budget_sensitivity": "neutral",
            "social_energy": "neutral",
            "cultural_depth": "neutral",
        },
        "sample_cities": ["seattle", "asheville", "austin"],
    },
    {
        "id": "wellness_retreater",
        "name": "Wellness Retreater",
        "description": (
            "A traveler who uses trips for personal restoration. "
            "Seeks yoga studios, spas, healthy restaurants, nature walks, and quiet mornings. "
            "Avoids crowds, noise, and overscheduling."
        ),
        "preferences": {
            "pace_preference": "low",
            "outdoor_affinity": "high",
            "food_priority": "high",
            "nightlife_interest": "low",
            "cultural_depth": "neutral",
            "budget_sensitivity": "low",
            "social_energy": "low",
            "adventure_tolerance": "low",
        },
        "sample_cities": ["bend", "asheville", "portland"],
    },
    {
        "id": "digital_nomad",
        "name": "Digital Nomad",
        "description": (
            "A remote worker who travels while working full-time. "
            "Evaluates cities by coworking space quality, coffee shop WiFi, and cost of living. "
            "Social but selective — seeks expat community without tourist traps."
        ),
        "preferences": {
            "budget_sensitivity": "high",
            "food_priority": "neutral",
            "cultural_depth": "neutral",
            "outdoor_affinity": "neutral",
            "nightlife_interest": "neutral",
            "pace_preference": "low",
            "social_energy": "high",
            "adventure_tolerance": "neutral",
        },
        "sample_cities": ["mexico-city", "austin", "portland"],
    },
    {
        "id": "weekend_warrior",
        "name": "Weekend Warrior",
        "description": (
            "A busy professional who takes 3-day trips to decompress. "
            "Wants maximum variety packed into minimal time. "
            "Will pay for convenience, skips nothing, and sleeps on the flight home."
        ),
        "preferences": {
            "pace_preference": "high",
            "budget_sensitivity": "low",
            "food_priority": "high",
            "outdoor_affinity": "neutral",
            "nightlife_interest": "high",
            "cultural_depth": "neutral",
            "social_energy": "neutral",
            "adventure_tolerance": "neutral",
        },
        "sample_cities": ["new-orleans", "austin", "seattle"],
    },
    {
        "id": "road_tripper",
        "name": "Road Tripper",
        "description": (
            "Someone who drives between destinations and treats the journey as the point. "
            "Loves roadside diners, scenic overlooks, small towns, and camping. "
            "Hates airports, tourist hotspots, and structured itineraries."
        ),
        "preferences": {
            "outdoor_affinity": "high",
            "adventure_tolerance": "high",
            "food_priority": "low",
            "budget_sensitivity": "high",
            "nightlife_interest": "low",
            "cultural_depth": "neutral",
            "pace_preference": "neutral",
            "social_energy": "neutral",
        },
        "sample_cities": ["bend", "asheville", "portland"],
    },
    {
        "id": "group_organizer",
        "name": "Group Organizer",
        "description": (
            "The person in friend groups who plans every detail of group trips. "
            "Optimizes for group consensus, books reservations, mediates preferences. "
            "Personally flexible but diplomatically manages competing tastes."
        ),
        "preferences": {
            "social_energy": "high",
            "food_priority": "high",
            "pace_preference": "neutral",
            "outdoor_affinity": "neutral",
            "nightlife_interest": "neutral",
            "budget_sensitivity": "neutral",
            "cultural_depth": "neutral",
            "adventure_tolerance": "neutral",
        },
        "sample_cities": ["new-orleans", "austin", "mexico-city"],
    },
]

_ARCHETYPE_BY_ID: dict[str, dict[str, Any]] = {a["id"]: a for a in ARCHETYPES}

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_sonnet_prompt(archetype: dict, city: str, trip_number: int) -> str:
    """
    Build the Sonnet prompt for generating traveler reactions.

    Only archetype data goes into this prompt — no user data.
    """
    prefs = "\n".join(
        f"  - {dim}: {direction}"
        for dim, direction in archetype["preferences"].items()
    )
    return (
        f"You are simulating a traveler with the following profile:\n\n"
        f"Archetype: {archetype['name']}\n"
        f"Description: {archetype['description']}\n\n"
        f"Preferences:\n{prefs}\n\n"
        f"City: {city}\n"
        f"Trip number: {trip_number}\n\n"
        f"Generate a realistic first-person journal entry (3-5 sentences) describing "
        f"this traveler's reactions to the activities they did today. "
        f"Focus on what they liked, disliked, and what they'd want more or less of. "
        f"Write from this traveler's genuine perspective based on their archetype. "
        f"Be specific about the city and day activities."
    )


_HAIKU_CLASSIFICATION_SYSTEM = """You classify traveler journal entries into behavioral signals.

Return a JSON array. Each item must have exactly:
  - dimension: one of: food_priority, nightlife_interest, pace_preference,
      budget_sensitivity, outdoor_affinity, cultural_depth, social_energy, adventure_tolerance
  - direction: exactly "high" or "low" or "neutral"
  - confidence: float between 0.0 and 1.0 (inclusive)

Return only valid JSON. No explanation, no markdown fences. Return [] if nothing classifiable."""


def _build_haiku_prompt(journal_text: str) -> str:
    return f"Classify this traveler journal entry:\n\n{journal_text}"


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


def _estimate_sonnet_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * SONNET_INPUT_COST_PER_M
        + output_tokens * SONNET_OUTPUT_COST_PER_M
    ) / 1_000_000


def _estimate_haiku_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * HAIKU_INPUT_COST_PER_M
        + output_tokens * HAIKU_OUTPUT_COST_PER_M
    ) / 1_000_000


# ---------------------------------------------------------------------------
# Haiku output validation
# ---------------------------------------------------------------------------


def _validate_haiku_output(raw: str) -> list[dict]:
    """
    Parse and strictly validate Haiku classification output.

    Raises ValueError if the output is malformed or contains invalid values.
    Returns a list of validated signal dicts.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Haiku returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"Haiku output must be a JSON array, got: {type(parsed).__name__}")

    validated: list[dict] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"Haiku output item {i} is not a dict: {item!r}")

        dim = item.get("dimension", "")
        direction = item.get("direction", "")
        confidence = item.get("confidence")

        if dim not in VALID_DIMENSIONS:
            raise ValueError(
                f"Haiku output item {i}: invalid dimension {dim!r}. "
                f"Valid: {sorted(VALID_DIMENSIONS)}"
            )

        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Haiku output item {i}: invalid direction {direction!r}. "
                f"Valid: {sorted(VALID_DIRECTIONS)}"
            )

        try:
            conf_f = float(confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Haiku output item {i}: confidence must be float, got {confidence!r}"
            ) from exc

        if not (0.0 <= conf_f <= 1.0):
            raise ValueError(
                f"Haiku output item {i}: confidence {conf_f} out of range [0.0, 1.0]"
            )

        validated.append(
            {
                "dimension": dim,
                "direction": direction,
                "confidence": conf_f,
            }
        )

    return validated


# ---------------------------------------------------------------------------
# Database write
# ---------------------------------------------------------------------------

_INSERT_BEHAVIORAL_SIGNAL_SQL = """
INSERT INTO behavioral_signals
  (id, "userId", "tripId", "slotId", "activityNodeId", "signalType",
   "signalValue", "tripPhase", "rawAction", "modelVersion", "promptVersion",
   "source", signal_weight, "createdAt")
VALUES
  ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
"""


def _direction_to_signal_value(direction: str, confidence: float) -> float:
    """
    Convert direction + confidence into a signal_value in [-1.0, 3.0].

    high -> positive value scaled by confidence
    low  -> negative value scaled by confidence
    neutral -> near zero
    """
    if direction == "high":
        # Scale 0.0-1.0 confidence -> 0.0-1.5
        value = confidence * 1.5
    elif direction == "low":
        # Scale to [-1.0, 0.0]
        value = -(confidence * 1.0)
    else:
        value = 0.0

    # Clamp to CHECK constraint
    return max(SIGNAL_WEIGHT_MIN, min(SIGNAL_WEIGHT_MAX, round(value, 4)))


async def _write_signals(
    db_pool,
    user_id: str,
    signals: list[dict],
    city: str,
) -> int:
    """Write validated synthetic signals to behavioral_signals table."""
    if not signals:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for sig in signals:
        signal_value = _direction_to_signal_value(
            sig["direction"], sig["confidence"]
        )
        rows.append((
            str(uuid.uuid4()),          # id
            user_id,                    # userId
            None,                       # tripId
            None,                       # slotId
            None,                       # activityNodeId
            "category_preference",      # signalType (closest BehavioralSignal enum)
            signal_value,               # signalValue
            "pre_trip",                 # tripPhase
            f"synthetic:{sig['dimension']}:{sig['direction']}",  # rawAction
            SONNET_MODEL,               # modelVersion
            HAIKU_PROMPT_VERSION,       # promptVersion
            SYNTHETIC_SOURCE,           # source
            0.3,                        # signal_weight (synthetic = 0.3 per design doc)
            now,                        # createdAt
        ))

    async with db_pool.acquire() as conn:
        await conn.executemany(_INSERT_BEHAVIORAL_SIGNAL_SQL, rows)

    return len(rows)


# ---------------------------------------------------------------------------
# Two-agent loop
# ---------------------------------------------------------------------------


async def _run_archetype(
    archetype: dict,
    trips_per_archetype: int,
    db_pool,
    anthropic_client,
    budget_tracker: dict,
) -> dict:
    """
    Run trips_per_archetype simulated trips for a single archetype.

    Returns:
        {
          "archetype_id": str,
          "trips_completed": int,
          "signals_generated": int,
          "cost_estimate_usd": float,
          "aborted": bool,
          "abort_reason": str | None,
        }
    """
    archetype_id = archetype["id"]
    cities = archetype["sample_cities"]
    signals_generated = 0
    cost_estimate = 0.0
    consecutive_haiku_failures = 0

    for trip_num in range(1, trips_per_archetype + 1):
        # Check budget cap before each trip
        if budget_tracker["total_cost"] >= BUDGET_CAP_USD:
            logger.warning(
                "synthetic_sim: budget cap $%.2f reached at archetype=%s trip=%d",
                BUDGET_CAP_USD,
                archetype_id,
                trip_num,
            )
            return {
                "archetype_id": archetype_id,
                "trips_completed": trip_num - 1,
                "signals_generated": signals_generated,
                "cost_estimate_usd": cost_estimate,
                "aborted": True,
                "abort_reason": f"budget_cap_reached at ${BUDGET_CAP_USD:.2f}",
            }

        # Round-robin through sample cities
        city = cities[(trip_num - 1) % len(cities)]

        # Build synthetic user ID (synth- prefix, stable per archetype+trip)
        synth_user_id = f"{SYNTH_ID_PREFIX}{archetype_id}-{trip_num:04d}"

        # --- Agent 1: Sonnet generates reaction ---
        t0 = time.monotonic()
        try:
            sonnet_prompt = _build_sonnet_prompt(archetype, city, trip_num)
            sonnet_response = await anthropic_client.messages.create(
                model=SONNET_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": sonnet_prompt}],
            )
            sonnet_latency_ms = round((time.monotonic() - t0) * 1000)
            journal_text = sonnet_response.content[0].text.strip()

            sonnet_cost = _estimate_sonnet_cost(
                sonnet_response.usage.input_tokens,
                sonnet_response.usage.output_tokens,
            )
            cost_estimate += sonnet_cost
            budget_tracker["total_cost"] += sonnet_cost

            logger.info(
                "synthetic_sim sonnet model=%s prompt_version=%s archetype=%s "
                "trip=%d latency_ms=%d input_tokens=%d output_tokens=%d cost_usd=%.6f",
                SONNET_MODEL,
                SONNET_PROMPT_VERSION,
                archetype_id,
                trip_num,
                sonnet_latency_ms,
                sonnet_response.usage.input_tokens,
                sonnet_response.usage.output_tokens,
                sonnet_cost,
            )

        except Exception as exc:
            logger.error(
                "synthetic_sim: sonnet failed archetype=%s trip=%d: %s",
                archetype_id,
                trip_num,
                str(exc),
            )
            # Sonnet failure is non-fatal per trip — skip this trip
            continue

        # --- Agent 2: Haiku classifies the reaction ---
        t0 = time.monotonic()
        try:
            haiku_prompt = _build_haiku_prompt(journal_text)
            haiku_response = await anthropic_client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=512,
                system=_HAIKU_CLASSIFICATION_SYSTEM,
                messages=[{"role": "user", "content": haiku_prompt}],
            )
            haiku_latency_ms = round((time.monotonic() - t0) * 1000)
            raw_classification = haiku_response.content[0].text.strip()

            haiku_cost = _estimate_haiku_cost(
                haiku_response.usage.input_tokens,
                haiku_response.usage.output_tokens,
            )
            cost_estimate += haiku_cost
            budget_tracker["total_cost"] += haiku_cost

            logger.info(
                "synthetic_sim haiku model=%s prompt_version=%s archetype=%s "
                "trip=%d latency_ms=%d input_tokens=%d output_tokens=%d cost_usd=%.6f",
                HAIKU_MODEL,
                HAIKU_PROMPT_VERSION,
                archetype_id,
                trip_num,
                haiku_latency_ms,
                haiku_response.usage.input_tokens,
                haiku_response.usage.output_tokens,
                haiku_cost,
            )

            # Validate Haiku output
            validated_signals = _validate_haiku_output(raw_classification)

            # Reset circuit breaker on success
            consecutive_haiku_failures = 0

        except ValueError as exc:
            # Validation failure
            consecutive_haiku_failures += 1
            logger.warning(
                "synthetic_sim: haiku validation failed archetype=%s trip=%d "
                "consecutive=%d: %s",
                archetype_id,
                trip_num,
                consecutive_haiku_failures,
                str(exc),
            )
            if consecutive_haiku_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(
                    "synthetic_sim: circuit breaker tripped archetype=%s "
                    "after %d consecutive haiku failures",
                    archetype_id,
                    CIRCUIT_BREAKER_THRESHOLD,
                )
                return {
                    "archetype_id": archetype_id,
                    "trips_completed": trip_num - 1,
                    "signals_generated": signals_generated,
                    "cost_estimate_usd": cost_estimate,
                    "aborted": True,
                    "abort_reason": (
                        f"circuit_breaker: {CIRCUIT_BREAKER_THRESHOLD} consecutive "
                        f"haiku failures"
                    ),
                }
            continue

        except Exception as exc:
            consecutive_haiku_failures += 1
            logger.error(
                "synthetic_sim: haiku call failed archetype=%s trip=%d "
                "consecutive=%d: %s",
                archetype_id,
                trip_num,
                consecutive_haiku_failures,
                str(exc),
            )
            if consecutive_haiku_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(
                    "synthetic_sim: circuit breaker tripped archetype=%s "
                    "after %d consecutive haiku failures",
                    archetype_id,
                    CIRCUIT_BREAKER_THRESHOLD,
                )
                return {
                    "archetype_id": archetype_id,
                    "trips_completed": trip_num - 1,
                    "signals_generated": signals_generated,
                    "cost_estimate_usd": cost_estimate,
                    "aborted": True,
                    "abort_reason": (
                        f"circuit_breaker: {CIRCUIT_BREAKER_THRESHOLD} consecutive "
                        f"haiku failures"
                    ),
                }
            continue

        # --- Write signals to DB ---
        if validated_signals:
            try:
                count = await _write_signals(
                    db_pool, synth_user_id, validated_signals, city
                )
                signals_generated += count
            except Exception as exc:
                logger.error(
                    "synthetic_sim: db write failed archetype=%s trip=%d: %s",
                    archetype_id,
                    trip_num,
                    str(exc),
                )
                # DB write failure is non-fatal per trip

    return {
        "archetype_id": archetype_id,
        "trips_completed": trips_per_archetype,
        "signals_generated": signals_generated,
        "cost_estimate_usd": cost_estimate,
        "aborted": False,
        "abort_reason": None,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_synthetic_simulation(
    db_pool,
    anthropic_client,
    is_admin: bool,
    archetype_filter: list[str] | None = None,
    trips_per_archetype: int = 50,
) -> dict:
    """
    Generate synthetic training data by simulating travel archetypes.

    Admin-only. Raises PermissionError if is_admin is False.

    Two-agent loop:
      1. Sonnet generates simulated traveler reactions to itinerary slots
      2. Haiku classifies those reactions into BehavioralSignal-compatible format

    All synthetic data tagged with source="synthetic_agent_v1".
    Synthetic user IDs use "synth-" prefix.

    Safety controls:
      - Budget cap: $100 per run (cumulative across all archetypes)
      - Circuit breaker: 5 consecutive Haiku failures per archetype -> abort that archetype
      - Strict output validation on all Haiku responses

    Args:
        db_pool: asyncpg connection pool.
        anthropic_client: AsyncAnthropic client instance.
        is_admin: Must be True or PermissionError is raised.
        archetype_filter: If provided, run only archetypes with IDs in this list.
            If None, run all 12 archetypes.
        trips_per_archetype: Number of simulated trips per archetype. Default 50.

    Returns:
        {
          "status": "completed" | "aborted",
          "archetypes_run": int,
          "signals_generated": int,
          "cost_estimate_usd": float,
          "archetype_results": list[dict],
          "abort_reason": str | None,
        }
    """
    if not is_admin:
        raise PermissionError(
            "run_synthetic_simulation is admin-only. "
            "Set is_admin=True with proper authorization."
        )

    # Resolve archetype list
    if archetype_filter is not None:
        unknown = [a for a in archetype_filter if a not in _ARCHETYPE_BY_ID]
        if unknown:
            raise ValueError(
                f"Unknown archetype IDs: {unknown}. "
                f"Valid: {list(_ARCHETYPE_BY_ID.keys())}"
            )
        archetypes_to_run = [_ARCHETYPE_BY_ID[a] for a in archetype_filter]
    else:
        archetypes_to_run = list(ARCHETYPES)

    # Shared budget tracker (mutable dict passed by reference to each archetype run)
    budget_tracker = {"total_cost": 0.0}

    total_signals = 0
    archetypes_run = 0
    archetype_results: list[dict] = []
    overall_aborted = False
    abort_reason: str | None = None

    logger.info(
        "synthetic_sim: starting run archetypes=%d trips_per=%d",
        len(archetypes_to_run),
        trips_per_archetype,
    )

    for archetype in archetypes_to_run:
        # Budget check before each archetype
        if budget_tracker["total_cost"] >= BUDGET_CAP_USD:
            overall_aborted = True
            abort_reason = f"budget_cap_reached at ${BUDGET_CAP_USD:.2f}"
            logger.warning(
                "synthetic_sim: aborting run at archetype=%s due to budget cap",
                archetype["id"],
            )
            break

        result = await _run_archetype(
            archetype=archetype,
            trips_per_archetype=trips_per_archetype,
            db_pool=db_pool,
            anthropic_client=anthropic_client,
            budget_tracker=budget_tracker,
        )

        archetype_results.append(result)
        archetypes_run += 1
        total_signals += result["signals_generated"]

        if result["aborted"]:
            # Circuit breaker or budget cap during archetype run
            if "budget_cap" in (result["abort_reason"] or ""):
                overall_aborted = True
                abort_reason = result["abort_reason"]
                break
            # Circuit breaker only aborts this archetype — continue with next
            logger.warning(
                "synthetic_sim: archetype=%s aborted (%s), continuing with next",
                archetype["id"],
                result["abort_reason"],
            )

    final_status = "aborted" if overall_aborted else "completed"

    logger.info(
        "synthetic_sim: %s archetypes_run=%d signals_generated=%d "
        "cost_estimate_usd=%.4f",
        final_status,
        archetypes_run,
        total_signals,
        budget_tracker["total_cost"],
    )

    return {
        "status": final_status,
        "archetypes_run": archetypes_run,
        "signals_generated": total_signals,
        "cost_estimate_usd": round(budget_tracker["total_cost"], 4),
        "archetype_results": archetype_results,
        "abort_reason": abort_reason,
    }
