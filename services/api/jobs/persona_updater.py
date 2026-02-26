"""
Nightly persona dimension updater (Phase 4.3).

Updates PersonaDimension rows using Exponential Moving Average (EMA) from
recent BehavioralSignal data. Runs at 3:30am UTC after write_back.

PersonaDimension stores:
  - dimension:  key like "food_priority", "nature_preference"
  - value:      categorical label like "food_driven", "nature_curious"
  - confidence: float 0.0-1.0 (certainty)
  - source:     provenance string

EMA formula:
    new_confidence = alpha * signal_confidence + (1 - alpha) * current_confidence

Design:
  - alpha = 0.3 (responsive but stable)
  - Mid-trip signals (tripPhase = 'active') get 3x weight via boosted alpha:
      effective_alpha = min(1.0, alpha * 3) = 0.9 for active-phase signals
  - Activity categories on accepted/rejected slots drive dimension updates
  - Only source='user_behavioral' signals are used
  - PersonaUpdateRun audit table tracks each execution
  - Idempotency: skips if a successful run already exists for the target date

Category-to-dimension mapping:
  Accepted food/dining slots     -> food_priority confidence UP
  Rejected outdoor/nature slots  -> nature_preference confidence DOWN
  etc. Each acceptance or rejection nudges the relevant dimension's
  confidence toward 1.0 or 0.0 respectively.

Entry point:
    async def run_persona_update(pool, target_date=None)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# EMA smoothing factor (0 = ignore new data, 1 = only new data)
EMA_ALPHA = 0.3

# Mid-trip (tripPhase = 'active') signals are 3x more informative
MID_TRIP_ALPHA_MULTIPLIER = 3

# Minimum signals to start updating a dimension (cold-start guard)
MIN_SIGNALS_FOR_UPDATE = 2

# Default confidence for new PersonaDimension rows
DEFAULT_CONFIDENCE = 0.5

# ActivityCategory -> PersonaDimension mapping
# Maps Prisma ActivityCategory enum values to which persona dimension they affect.
# Each category can affect multiple dimensions with different weights.
CATEGORY_DIMENSION_MAP: dict[str, list[dict[str, Any]]] = {
    "restaurant": [
        {"dimension": "food_priority", "positive_value": "food_driven", "weight": 1.0},
    ],
    "cafe": [
        {"dimension": "food_priority", "positive_value": "food_driven", "weight": 0.6},
        {"dimension": "pace_preference", "positive_value": "slow_traveler", "weight": 0.3},
    ],
    "bar": [
        {"dimension": "nightlife_interest", "positive_value": "nightlife_seeker", "weight": 0.8},
    ],
    "club": [
        {"dimension": "nightlife_interest", "positive_value": "nightlife_seeker", "weight": 1.0},
        {"dimension": "energy_level", "positive_value": "high_energy", "weight": 0.5},
    ],
    "museum": [
        {"dimension": "culture_engagement", "positive_value": "culture_immersive", "weight": 1.0},
    ],
    "temple": [
        {"dimension": "culture_engagement", "positive_value": "culture_immersive", "weight": 0.8},
        {"dimension": "authenticity_preference", "positive_value": "authenticity_driven", "weight": 0.5},
    ],
    "gallery": [
        {"dimension": "culture_engagement", "positive_value": "culture_immersive", "weight": 0.7},
    ],
    "market": [
        {"dimension": "food_priority", "positive_value": "food_driven", "weight": 0.5},
        {"dimension": "authenticity_preference", "positive_value": "authenticity_driven", "weight": 0.6},
    ],
    "park": [
        {"dimension": "nature_preference", "positive_value": "nature_driven", "weight": 0.8},
        {"dimension": "energy_level", "positive_value": "medium_energy", "weight": 0.3},
    ],
    "hike": [
        {"dimension": "nature_preference", "positive_value": "nature_driven", "weight": 1.0},
        {"dimension": "energy_level", "positive_value": "high_energy", "weight": 0.7},
    ],
    "viewpoint": [
        {"dimension": "nature_preference", "positive_value": "nature_curious", "weight": 0.5},
    ],
    "onsen": [
        {"dimension": "pace_preference", "positive_value": "slow_traveler", "weight": 0.6},
        {"dimension": "authenticity_preference", "positive_value": "authenticity_driven", "weight": 0.4},
    ],
    "shopping": [
        {"dimension": "budget_orientation", "positive_value": "moderate_spender", "weight": 0.4},
    ],
    "neighborhood": [
        {"dimension": "authenticity_preference", "positive_value": "locally_curious", "weight": 0.7},
        {"dimension": "pace_preference", "positive_value": "slow_traveler", "weight": 0.4},
    ],
    "entertainment": [
        {"dimension": "energy_level", "positive_value": "high_energy", "weight": 0.5},
        {"dimension": "social_orientation", "positive_value": "social_explorer", "weight": 0.4},
    ],
}

# Signal types that indicate acceptance (positive engagement)
POSITIVE_SIGNAL_TYPES = frozenset({
    "slot_confirm",
    "slot_complete",
    "post_loved",
    "discover_shortlist",
    "discover_swipe_right",
})

# Signal types that indicate rejection (negative engagement)
NEGATIVE_SIGNAL_TYPES = frozenset({
    "slot_skip",
    "slot_reject",
    "post_disliked",
    "discover_swipe_left",
})


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_CHECK_EXISTING_SQL = """
SELECT id FROM persona_update_runs
WHERE "runDate" = $1 AND status = 'success'
LIMIT 1
"""

_INSERT_RUN_SQL = """
INSERT INTO persona_update_runs ("runDate", status, "usersUpdated", "dimensionsUpdated", "durationMs")
VALUES ($1, $2, $3, $4, $5)
"""

# Fetch signals with their activity category for the target date window.
# Joins BehavioralSignal -> ItinerarySlot -> ActivityNode to get the category.
_SIGNALS_WITH_CATEGORY_SQL = """
SELECT
    bs."userId",
    bs."signalType",
    bs."tripPhase",
    an.category
FROM behavioral_signals bs
JOIN itinerary_slots isl ON isl.id = bs."slotId"
JOIN activity_nodes an ON an.id = isl."activityNodeId"
WHERE bs.source = 'user_behavioral'
  AND bs."slotId" IS NOT NULL
  AND bs."createdAt" >= $1
  AND bs."createdAt" < $2
  AND bs."signalType" = ANY($3)
ORDER BY bs."userId", bs."createdAt"
"""

# Get current PersonaDimension rows for a user
_GET_PERSONA_SQL = """
SELECT dimension, value, confidence, source
FROM persona_dimensions
WHERE "userId" = $1
"""

# Upsert a PersonaDimension row
_UPSERT_PERSONA_SQL = """
INSERT INTO persona_dimensions (id, "userId", dimension, value, confidence, source, "updatedAt", "createdAt")
VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, NOW(), NOW())
ON CONFLICT ("userId", dimension) DO UPDATE
SET confidence = EXCLUDED.confidence,
    source = EXCLUDED.source,
    "updatedAt" = NOW()
"""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_ema(
    current_confidence: float,
    signal_direction: float,
    alpha: float,
    weight: float,
) -> float:
    """
    Apply weighted EMA to a confidence value.

    Args:
        current_confidence: Current confidence (0.0 - 1.0)
        signal_direction:   1.0 for positive, -1.0 for negative
        alpha:              EMA smoothing factor (0.0 - 1.0)
        weight:             Category mapping weight (0.0 - 1.0)

    Returns:
        Updated confidence clamped to [0.05, 0.98]
    """
    # Target: 1.0 for positive signals, 0.0 for negative
    target = 1.0 if signal_direction > 0 else 0.0
    effective_alpha = alpha * weight
    new_confidence = effective_alpha * target + (1.0 - effective_alpha) * current_confidence
    return max(0.05, min(0.98, new_confidence))


def _effective_alpha(trip_phase: str) -> float:
    """Compute effective EMA alpha, boosted for mid-trip signals."""
    if trip_phase == "active":
        return min(1.0, EMA_ALPHA * MID_TRIP_ALPHA_MULTIPLIER)
    return EMA_ALPHA


def _build_dimension_updates(
    signals: list[dict],
    current_persona: dict[str, dict],
) -> dict[str, float]:
    """
    Compute new confidence values for each dimension from a batch of signals.

    Args:
        signals:         List of signal dicts with keys: signalType, tripPhase, category
        current_persona: Dict of dimension -> {value, confidence, source}

    Returns:
        Dict of dimension -> new_confidence
    """
    # Start with current confidence values
    confidences: dict[str, float] = {
        dim: info["confidence"]
        for dim, info in current_persona.items()
    }

    # Count signals per dimension to enforce MIN_SIGNALS_FOR_UPDATE
    dimension_signal_counts: dict[str, int] = {}

    for sig in signals:
        category = sig["category"].lower() if sig["category"] else None
        if category not in CATEGORY_DIMENSION_MAP:
            continue

        is_positive = sig["signalType"] in POSITIVE_SIGNAL_TYPES
        is_negative = sig["signalType"] in NEGATIVE_SIGNAL_TYPES
        if not is_positive and not is_negative:
            continue

        direction = 1.0 if is_positive else -1.0
        alpha = _effective_alpha(sig["tripPhase"])

        for mapping in CATEGORY_DIMENSION_MAP[category]:
            dim = mapping["dimension"]
            weight = mapping["weight"]

            dimension_signal_counts[dim] = dimension_signal_counts.get(dim, 0) + 1

            current = confidences.get(dim, DEFAULT_CONFIDENCE)
            confidences[dim] = compute_ema(current, direction, alpha, weight)

    # Filter out dimensions with too few signals
    result = {}
    for dim, conf in confidences.items():
        if dim in dimension_signal_counts and dimension_signal_counts[dim] >= MIN_SIGNALS_FOR_UPDATE:
            result[dim] = conf

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_persona_update(
    pool: Any,
    target_date: date | None = None,
) -> dict[str, Any]:
    """
    Run the nightly persona dimension update for a given target date.

    Args:
        pool:        asyncpg connection pool.
        target_date: The calendar date whose signals to process.
                     Defaults to yesterday (UTC).

    Returns:
        A result dict::

            {
                "date": "2026-02-24",
                "status": "success" | "skipped" | "error",
                "users_updated": int,
                "dimensions_updated": int,
                "duration_ms": int,
            }
    """
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    date_label = target_date.isoformat()
    logger.info("persona_updater: starting for date=%s", date_label)

    start_ts = time.monotonic()

    async with pool.acquire() as conn:
        # Idempotency guard
        existing = await conn.fetchrow(_CHECK_EXISTING_SQL, target_date)
        if existing:
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            logger.info(
                "persona_updater: already succeeded for date=%s, skipping",
                date_label,
            )
            return {
                "date": date_label,
                "status": "skipped",
                "users_updated": 0,
                "dimensions_updated": 0,
                "duration_ms": duration_ms,
            }

        # Time window for the target date
        day_start = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=timezone.utc,
        )
        day_end = day_start + timedelta(days=1)

        all_signal_types = list(POSITIVE_SIGNAL_TYPES | NEGATIVE_SIGNAL_TYPES)

        try:
            # Fetch signals with category info
            rows = await conn.fetch(
                _SIGNALS_WITH_CATEGORY_SQL,
                day_start,
                day_end,
                all_signal_types,
            )

            if not rows:
                duration_ms = int((time.monotonic() - start_ts) * 1000)
                logger.info("persona_updater: no signals for date=%s", date_label)
                await conn.execute(
                    _INSERT_RUN_SQL, target_date, "success", 0, 0, duration_ms,
                )
                return {
                    "date": date_label,
                    "status": "success",
                    "users_updated": 0,
                    "dimensions_updated": 0,
                    "duration_ms": duration_ms,
                }

            # Group signals by user
            user_signals: dict[str, list[dict]] = {}
            for row in rows:
                uid = row["userId"]
                user_signals.setdefault(uid, []).append(dict(row))

            users_updated = 0
            dimensions_updated = 0

            for uid, signals in user_signals.items():
                # Get current persona dimensions
                persona_rows = await conn.fetch(_GET_PERSONA_SQL, uid)
                current_persona: dict[str, dict] = {}
                for pr in persona_rows:
                    current_persona[pr["dimension"]] = {
                        "value": pr["value"],
                        "confidence": pr["confidence"],
                        "source": pr["source"],
                    }

                # Compute updates
                updates = _build_dimension_updates(signals, current_persona)

                if not updates:
                    continue

                # Apply updates via upsert
                async with conn.transaction():
                    for dim, new_confidence in updates.items():
                        # Preserve existing value, or use a default if dimension is new
                        existing_value = (
                            current_persona[dim]["value"]
                            if dim in current_persona
                            else _default_value_for_dimension(dim)
                        )
                        await conn.execute(
                            _UPSERT_PERSONA_SQL,
                            uid,
                            dim,
                            existing_value,
                            new_confidence,
                            "behavioral_ema",
                        )
                        dimensions_updated += 1

                users_updated += 1

            duration_ms = int((time.monotonic() - start_ts) * 1000)

            # Log audit
            await conn.execute(
                _INSERT_RUN_SQL,
                target_date,
                "success",
                users_updated,
                dimensions_updated,
                duration_ms,
            )

            logger.info(
                "persona_updater: complete date=%s users=%d dimensions=%d duration_ms=%d",
                date_label,
                users_updated,
                dimensions_updated,
                duration_ms,
            )

            return {
                "date": date_label,
                "status": "success",
                "users_updated": users_updated,
                "dimensions_updated": dimensions_updated,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            logger.error(
                "persona_updater: failed for date=%s after %dms: %s",
                date_label,
                duration_ms,
                exc,
                exc_info=True,
            )
            try:
                await conn.execute(
                    _INSERT_RUN_SQL,
                    target_date,
                    "error",
                    0,
                    0,
                    duration_ms,
                )
            except Exception:
                logger.warning(
                    "persona_updater: could not write error audit row for date=%s",
                    date_label,
                )
            raise


def _default_value_for_dimension(dimension: str) -> str:
    """Return the neutral/middle value for a persona dimension."""
    defaults = {
        "energy_level": "medium_energy",
        "social_orientation": "small_group",
        "planning_style": "flexible",
        "budget_orientation": "moderate_spender",
        "food_priority": "food_balanced",
        "culture_engagement": "culture_moderate",
        "nature_preference": "nature_curious",
        "nightlife_interest": "balanced_schedule",
        "authenticity_preference": "locally_curious",
        "pace_preference": "moderate_pace",
    }
    return defaults.get(dimension, "unknown")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Standalone entry point for running from cron or Cloud Run Job."""
    import os

    import asyncpg

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    database_url = os.environ["DATABASE_URL"]

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        result = await run_persona_update(pool)
        print(f"persona_updater complete: {result}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
