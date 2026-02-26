"""
L1 — SessionPersonaDelta

Ephemeral per-session persona accumulator stored in Redis as a hash.

Key format:  session_delta:{user_id}:{session_id}
TTL:         30 minutes, sliding on each write

Each behavioral signal is translated into a small adjustment to one or
more persona dimensions using the same CATEGORY_DIMENSION_MAP that drives
the nightly EMA persona updater. Adjustments are directional (positive
signals push the dimension up, negative signals push it down) and
phase-weighted so mid-trip signals carry more influence.

This class never writes to the PersonaDimension DB table. It only
accumulates deltas that are later merged into TripPersonaCache via
flush_to_trip_cache().

Graceful degradation: all operations are no-ops when redis is None.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Sliding TTL in seconds (30 minutes)
_SESSION_TTL_SECONDS = 30 * 60

# Step size per signal — keeps individual signals from dominating the delta
_STEP_SIZE = 0.1

# Persona dimension fields tracked in the session hash
_DIMENSION_FIELDS = [
    "food_priority_adj",
    "culture_engagement_adj",
    "nature_preference_adj",
    "nightlife_interest_adj",
    "pace_preference_adj",
    "energy_level_adj",
    "authenticity_preference_adj",
    "budget_orientation_adj",
    "social_orientation_adj",
]

# ActivityCategory -> dimension mapping (mirrors persona_updater.CATEGORY_DIMENSION_MAP)
# Only the dimension name and weight are needed here; we compute floating adjustments
# rather than EMA confidence updates.
_CATEGORY_DIMENSION_MAP: dict[str, list[dict[str, Any]]] = {
    "restaurant": [
        {"dimension": "food_priority", "weight": 1.0},
    ],
    "cafe": [
        {"dimension": "food_priority", "weight": 0.6},
        {"dimension": "pace_preference", "weight": 0.3},
    ],
    "bar": [
        {"dimension": "nightlife_interest", "weight": 0.8},
    ],
    "club": [
        {"dimension": "nightlife_interest", "weight": 1.0},
        {"dimension": "energy_level", "weight": 0.5},
    ],
    "museum": [
        {"dimension": "culture_engagement", "weight": 1.0},
    ],
    "temple": [
        {"dimension": "culture_engagement", "weight": 0.8},
        {"dimension": "authenticity_preference", "weight": 0.5},
    ],
    "gallery": [
        {"dimension": "culture_engagement", "weight": 0.7},
    ],
    "market": [
        {"dimension": "food_priority", "weight": 0.5},
        {"dimension": "authenticity_preference", "weight": 0.6},
    ],
    "park": [
        {"dimension": "nature_preference", "weight": 0.8},
        {"dimension": "energy_level", "weight": 0.3},
    ],
    "hike": [
        {"dimension": "nature_preference", "weight": 1.0},
        {"dimension": "energy_level", "weight": 0.7},
    ],
    "viewpoint": [
        {"dimension": "nature_preference", "weight": 0.5},
    ],
    "onsen": [
        {"dimension": "pace_preference", "weight": 0.6},
        {"dimension": "authenticity_preference", "weight": 0.4},
    ],
    "shopping": [
        {"dimension": "budget_orientation", "weight": 0.4},
    ],
    "neighborhood": [
        {"dimension": "authenticity_preference", "weight": 0.7},
        {"dimension": "pace_preference", "weight": 0.4},
    ],
    "entertainment": [
        {"dimension": "energy_level", "weight": 0.5},
        {"dimension": "social_orientation", "weight": 0.4},
    ],
}

# Signal types indicating positive engagement (direction = +1)
_POSITIVE_SIGNAL_TYPES = frozenset({
    "slot_confirm",
    "slot_complete",
    "post_loved",
    "discover_shortlist",
    "discover_swipe_right",
})

# Signal types indicating negative engagement (direction = -1)
_NEGATIVE_SIGNAL_TYPES = frozenset({
    "slot_skip",
    "slot_reject",
    "card_dismissed",
    "post_disliked",
    "discover_swipe_left",
})

# Phase weights — how much each trip phase amplifies a signal
# active day 1: 0.6, day 2-4: 1.0, day 5+: 0.65 are handled by the caller
# passing the correct phase string. Here we map phase label -> weight.
_PHASE_WEIGHTS: dict[str, float] = {
    "pre_trip": 0.4,
    "active": 1.0,      # default active weight (caller can refine by day number)
    "active_day1": 0.6,
    "active_day2_4": 1.0,
    "active_day5_plus": 0.65,
    "post_trip": 3.0,
}


def _phase_weight(trip_phase: str) -> float:
    """Return the phase amplifier for a given trip phase string."""
    return _PHASE_WEIGHTS.get(trip_phase, 1.0)


def _signal_direction(signal_type: str) -> float | None:
    """
    Return +1.0 for positive signals, -1.0 for negative, None to ignore.

    Signals that are neither positive nor negative (e.g. card_viewed) have
    no directional dimension adjustment — they only increment signal_count.
    """
    if signal_type in _POSITIVE_SIGNAL_TYPES:
        return 1.0
    if signal_type in _NEGATIVE_SIGNAL_TYPES:
        return -1.0
    return None


def _redis_key(user_id: str, session_id: str) -> str:
    return f"session_delta:{user_id}:{session_id}"


class SessionPersonaDelta:
    """
    L1 ephemeral per-session persona accumulator.

    Usage:
        delta = SessionPersonaDelta(app.state.redis)
        await delta.apply_signal(user_id, session_id, "slot_confirm", "restaurant", "active")
        adjustments = await delta.get_delta(user_id, session_id)
        await delta.flush_to_trip_cache(user_id, session_id, trip_id, trip_cache)
    """

    def __init__(self, redis: Any) -> None:
        """
        Args:
            redis: An async Redis client (redis.asyncio compatible).
                   May be None — all operations degrade gracefully.
        """
        self._redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def apply_signal(
        self,
        user_id: str,
        session_id: str,
        signal_type: str,
        activity_category: str | None,
        trip_phase: str,
    ) -> None:
        """
        Apply one behavioral signal to the session delta hash.

        Increments signal_count unconditionally. Dimension adjustments are
        only applied when:
          - signal_type is positive or negative (not view-only events)
          - activity_category maps to at least one persona dimension

        The TTL is reset to 30 minutes on every write (sliding window).

        Args:
            user_id:           User UUID string.
            session_id:        Opaque session identifier (UUID or client-generated).
            signal_type:       e.g. "slot_confirm", "card_dismissed".
            activity_category: e.g. "restaurant", "museum". May be None for
                               signals not tied to a specific activity.
            trip_phase:        e.g. "pre_trip", "active", "post_trip".
        """
        if self._redis is None:
            return

        key = _redis_key(user_id, session_id)
        direction = _signal_direction(signal_type)
        phase_w = _phase_weight(trip_phase)
        category = (activity_category or "").lower()

        try:
            # Build the field updates for this signal
            updates: dict[str, str] = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            if direction is not None and category in _CATEGORY_DIMENSION_MAP:
                for mapping in _CATEGORY_DIMENSION_MAP[category]:
                    dim = mapping["dimension"]
                    weight: float = mapping["weight"]
                    adj = direction * weight * phase_w * _STEP_SIZE
                    field = f"{dim}_adj"
                    # Fetch current value and accumulate
                    raw = await self._redis.hget(key, field)
                    current = float(raw) if raw is not None else 0.0
                    updates[field] = str(round(current + adj, 6))

            # Increment signal_count
            await self._redis.hincrby(key, "signal_count", 1)

            # Write accumulated dimension adjustments + timestamp
            if len(updates) > 1 or "last_updated" in updates:
                await self._redis.hset(key, mapping=updates)

            # Reset sliding TTL
            await self._redis.expire(key, _SESSION_TTL_SECONDS)

            logger.debug(
                "session_delta apply_signal: key=%s signal_type=%s category=%s phase=%s",
                key,
                signal_type,
                category,
                trip_phase,
            )

        except Exception:
            logger.warning(
                "session_delta apply_signal failed: key=%s signal_type=%s",
                key,
                signal_type,
                exc_info=True,
            )

    async def get_delta(self, user_id: str, session_id: str) -> dict[str, Any]:
        """
        Return the current session delta as a dict.

        Returns:
            Dict with keys like ``food_priority_adj``, ``signal_count``,
            ``last_updated``. All adjustment values are floats.
            Returns an empty dict on cache miss or Redis unavailability.
        """
        if self._redis is None:
            return {}

        key = _redis_key(user_id, session_id)
        try:
            raw = await self._redis.hgetall(key)
            if not raw:
                return {}

            result: dict[str, Any] = {}
            for field, value in raw.items():
                # Redis returns bytes or str depending on decode_responses setting
                field_str = field.decode() if isinstance(field, bytes) else field
                value_str = value.decode() if isinstance(value, bytes) else value

                if field_str == "last_updated":
                    result[field_str] = value_str
                elif field_str == "signal_count":
                    result[field_str] = int(value_str)
                else:
                    result[field_str] = float(value_str)

            return result

        except Exception:
            logger.warning(
                "session_delta get_delta failed: key=%s", key, exc_info=True
            )
            return {}

    async def flush_to_trip_cache(
        self,
        user_id: str,
        session_id: str,
        trip_id: str,
        trip_cache: Any,
    ) -> None:
        """
        Merge session delta into TripPersonaCache, then delete the session key.

        This is called when the app closes or after a ~30 min idle expiry is
        about to fire. The trip_cache argument should be a TripPersonaCache
        instance.

        If the session delta is empty or Redis is unavailable, this is a no-op.

        Args:
            user_id:    User UUID string.
            session_id: Opaque session identifier.
            trip_id:    Trip UUID string — determines the L2 cache key.
            trip_cache: A TripPersonaCache instance.
        """
        if self._redis is None:
            return

        delta = await self.get_delta(user_id, session_id)
        if not delta:
            logger.debug(
                "session_delta flush: nothing to flush for key=%s",
                _redis_key(user_id, session_id),
            )
            return

        try:
            await trip_cache.merge_session_delta(user_id, trip_id, delta)
            await self._delete(user_id, session_id)
            logger.info(
                "session_delta flushed to trip_cache: user=%s session=%s trip=%s signal_count=%s",
                user_id,
                session_id,
                trip_id,
                delta.get("signal_count", 0),
            )
        except Exception:
            logger.warning(
                "session_delta flush_to_trip_cache failed: user=%s session=%s trip=%s",
                user_id,
                session_id,
                trip_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _delete(self, user_id: str, session_id: str) -> None:
        """Delete the session delta key from Redis."""
        if self._redis is None:
            return
        key = _redis_key(user_id, session_id)
        try:
            await self._redis.delete(key)
            logger.debug("session_delta deleted: %s", key)
        except Exception:
            logger.warning(
                "session_delta delete failed: key=%s", key, exc_info=True
            )
