"""
L2 — TripPersonaCache

Trip-scoped warm persona cache that persists across app opens.

Key format:  trip_persona_cache:{user_id}:{trip_id}
TTL:         trip.end_date + 48 hours, set via EXPIREAT (absolute timestamp)
             so long-lived entries survive server restarts and Redis reboots.

When a session ends, SessionPersonaDelta.flush_to_trip_cache() calls
merge_session_delta() here, which applies the float adjustments from L1
onto the base persona dimensions stored in this hash.

On the next app open, recommendation code reads get_cached_persona() instead
of hitting the PersonaDimension DB table. This gives within-trip persona
adaptation at Redis latency rather than Postgres query latency.

The nightly persona_updater job calls invalidate() after writing a fresh
PersonaDimension snapshot, so the next read fetches from DB and re-seeds
the cache via set_cached_persona().

Graceful degradation: all operations are no-ops / return None when redis
is None, allowing the app to fall back to direct DB reads.

GCP Cloud Memorystore compatibility:
- No Cluster-mode commands
- No Lua scripts
- Uses only standard Redis 6+ commands (HSET, HGETALL, EXPIREAT, DEL)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# How long after the trip end date we keep the cache alive (seconds)
_POST_TRIP_BUFFER_SECONDS = 48 * 60 * 60  # 48 hours

# Persona dimension keys stored in the trip hash (without _adj suffix)
_DIMENSION_KEYS = [
    "food_priority",
    "culture_engagement",
    "nature_preference",
    "nightlife_interest",
    "pace_preference",
    "energy_level",
    "authenticity_preference",
    "budget_orientation",
    "social_orientation",
]

# Bounds for clamping merged persona values
_PERSONA_MIN = 0.05
_PERSONA_MAX = 0.98


def _redis_key(user_id: str, trip_id: str) -> str:
    return f"trip_persona_cache:{user_id}:{trip_id}"


def _expiry_timestamp(trip_end_date: datetime) -> int:
    """
    Compute the Unix timestamp at which this cache entry should expire.

    Uses trip.end_date + 48 hours so that post-trip signals can still
    influence the persona during the reflection window.

    Args:
        trip_end_date: The trip's end datetime (timezone-aware recommended).

    Returns:
        Unix timestamp as int, suitable for Redis EXPIREAT.
    """
    if trip_end_date.tzinfo is None:
        trip_end_date = trip_end_date.replace(tzinfo=timezone.utc)
    expiry = trip_end_date + timedelta(seconds=_POST_TRIP_BUFFER_SECONDS)
    return int(expiry.timestamp())


def _encode_hash(data: dict[str, Any]) -> dict[str, str]:
    """Serialize a persona dict to flat string values for Redis HSET."""
    result: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (int, float)):
            result[k] = str(v)
        elif isinstance(v, str):
            result[k] = v
        else:
            result[k] = json.dumps(v)
    return result


def _decode_hash(raw: dict) -> dict[str, Any]:
    """Deserialize Redis HGETALL bytes/strings back to typed Python values."""
    result: dict[str, Any] = {}
    for field, value in raw.items():
        field_str = field.decode() if isinstance(field, bytes) else field
        value_str = value.decode() if isinstance(value, bytes) else value

        if field_str in ("last_updated",):
            result[field_str] = value_str
        elif field_str in ("signal_count_since_nightly", "nightly_sync_version"):
            try:
                result[field_str] = int(value_str)
            except (ValueError, TypeError):
                result[field_str] = 0
        else:
            # Dimension values are floats
            try:
                result[field_str] = float(value_str)
            except (ValueError, TypeError):
                result[field_str] = value_str
    return result


class TripPersonaCache:
    """
    L2 trip-scoped persona cache backed by Redis.

    Stores the full persona dimension snapshot for a user+trip combination,
    accumulated across multiple app sessions. Merges session deltas from
    SessionPersonaDelta to provide within-trip persona adaptation.

    Usage:
        cache = TripPersonaCache(app.state.redis)

        # On session end / nightly sync:
        await cache.set_cached_persona(user_id, trip_id, persona_dict, version, trip_end)

        # On app open (cold start bypass):
        persona = await cache.get_cached_persona(user_id, trip_id)
        if persona is None:
            persona = await db.fetch_persona(user_id)       # fallback
            await cache.set_cached_persona(...)             # warm the cache

        # After nightly persona_updater writes fresh PersonaDimension rows:
        await cache.invalidate(user_id, trip_id)
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

    async def get_cached_persona(
        self, user_id: str, trip_id: str
    ) -> dict[str, Any] | None:
        """
        Return the cached persona for a user+trip, or None on miss.

        A None return means the caller should fetch from PersonaDimension
        and call set_cached_persona() to warm the cache.

        Returns:
            Dict with keys: dimension names as floats, plus
            ``signal_count_since_nightly`` (int), ``nightly_sync_version`` (int),
            ``last_updated`` (ISO string). Returns None on cache miss or
            Redis unavailability.
        """
        if self._redis is None:
            return None

        key = _redis_key(user_id, trip_id)
        try:
            raw = await self._redis.hgetall(key)
            if not raw:
                logger.debug("trip_persona_cache miss: key=%s", key)
                return None
            persona = _decode_hash(raw)
            logger.debug(
                "trip_persona_cache hit: key=%s signal_count=%s",
                key,
                persona.get("signal_count_since_nightly", 0),
            )
            return persona
        except Exception:
            logger.warning(
                "trip_persona_cache get failed: key=%s", key, exc_info=True
            )
            return None

    async def set_cached_persona(
        self,
        user_id: str,
        trip_id: str,
        persona_dict: dict[str, float],
        version: int,
        trip_end_date: datetime,
    ) -> None:
        """
        Write a full persona snapshot with an absolute TTL.

        Called after fetching fresh PersonaDimension rows from DB, or after
        the nightly persona_updater updates and invalidates the stale entry.

        The TTL is set via EXPIREAT (absolute Unix timestamp = trip.end_date
        + 48 hours) so long-lived entries survive Redis restarts cleanly.

        Args:
            user_id:       User UUID string.
            trip_id:       Trip UUID string.
            persona_dict:  Dict of dimension_name -> float confidence value.
            version:       The ``PersonaDimension.version`` int from DB, used
                           for staleness checking via check_version().
            trip_end_date: The trip's end date (aware or naive datetime).
        """
        if self._redis is None:
            return

        key = _redis_key(user_id, trip_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        payload: dict[str, Any] = {**persona_dict}
        payload["nightly_sync_version"] = version
        payload["signal_count_since_nightly"] = 0
        payload["last_updated"] = now_iso

        expiry_ts = _expiry_timestamp(trip_end_date)

        try:
            await self._redis.hset(key, mapping=_encode_hash(payload))
            await self._redis.expireat(key, expiry_ts)
            logger.info(
                "trip_persona_cache set: key=%s version=%d expiry_ts=%d",
                key,
                version,
                expiry_ts,
            )
        except Exception:
            logger.warning(
                "trip_persona_cache set failed: key=%s", key, exc_info=True
            )

    async def merge_session_delta(
        self,
        user_id: str,
        trip_id: str,
        delta_dict: dict[str, Any],
    ) -> None:
        """
        Apply session delta adjustments onto the cached persona values.

        Each ``<dimension>_adj`` key in delta_dict is added to the
        corresponding dimension float in the cache. Values are clamped to
        [0.05, 0.98] after merging to match PersonaDimension confidence
        bounds.

        ``signal_count_since_nightly`` is incremented by the session's
        ``signal_count`` field.

        If the trip cache does not yet exist, this is a no-op (the delta
        will be applied the next time set_cached_persona() is called via
        a DB read + merge).

        Args:
            user_id:    User UUID string.
            trip_id:    Trip UUID string.
            delta_dict: Output of SessionPersonaDelta.get_delta() — contains
                        ``<dimension>_adj`` float keys and ``signal_count`` int.
        """
        if self._redis is None:
            return

        key = _redis_key(user_id, trip_id)

        try:
            # Check the cache exists before merging
            raw = await self._redis.hgetall(key)
            if not raw:
                logger.debug(
                    "trip_persona_cache merge: cache does not exist yet, skipping: key=%s",
                    key,
                )
                return

            current = _decode_hash(raw)
            updates: dict[str, str] = {}

            # Apply dimension adjustments
            for adj_field, adj_value in delta_dict.items():
                if not adj_field.endswith("_adj"):
                    continue
                # "food_priority_adj" -> "food_priority"
                dim = adj_field[:-4]
                if dim not in _DIMENSION_KEYS:
                    continue
                if not isinstance(adj_value, (int, float)):
                    continue

                current_val = float(current.get(dim, 0.5))
                merged = current_val + float(adj_value)
                clamped = max(_PERSONA_MIN, min(_PERSONA_MAX, merged))
                updates[dim] = str(round(clamped, 6))

            # Increment signal count
            session_signals = int(delta_dict.get("signal_count", 0))
            if session_signals > 0:
                await self._redis.hincrby(key, "signal_count_since_nightly", session_signals)

            # Write dimension updates + timestamp
            updates["last_updated"] = datetime.now(timezone.utc).isoformat()
            await self._redis.hset(key, mapping=updates)

            logger.info(
                "trip_persona_cache merge: key=%s session_signals=%d dims_updated=%d",
                key,
                session_signals,
                len(updates) - 1,  # exclude last_updated
            )

        except Exception:
            logger.warning(
                "trip_persona_cache merge failed: key=%s", key, exc_info=True
            )

    async def check_version(
        self,
        user_id: str,
        trip_id: str,
        current_db_version: int,
    ) -> bool:
        """
        Check whether the cached persona is still in sync with the DB.

        Returns True if the cache's nightly_sync_version matches
        current_db_version (cache is fresh). Returns False on version
        mismatch, cache miss, or Redis unavailability (conservative —
        caller should re-read from DB).

        Args:
            user_id:            User UUID string.
            trip_id:            Trip UUID string.
            current_db_version: The current ``PersonaDimension.version``
                                from the DB for this user.

        Returns:
            True if cache is fresh, False if stale or unavailable.
        """
        if self._redis is None:
            return False

        key = _redis_key(user_id, trip_id)
        try:
            raw = await self._redis.hget(key, "nightly_sync_version")
            if raw is None:
                return False
            value_str = raw.decode() if isinstance(raw, bytes) else raw
            cached_version = int(value_str)
            is_fresh = cached_version == current_db_version
            logger.debug(
                "trip_persona_cache check_version: key=%s cached=%d db=%d fresh=%s",
                key,
                cached_version,
                current_db_version,
                is_fresh,
            )
            return is_fresh
        except Exception:
            logger.warning(
                "trip_persona_cache check_version failed: key=%s", key, exc_info=True
            )
            return False

    async def invalidate(self, user_id: str, trip_id: str) -> None:
        """
        Force-evict the trip persona cache entry.

        Called by the nightly persona_updater after writing fresh
        PersonaDimension rows so the next recommendation request re-seeds
        the cache from the updated DB state.

        Args:
            user_id: User UUID string.
            trip_id: Trip UUID string.
        """
        if self._redis is None:
            return

        key = _redis_key(user_id, trip_id)
        try:
            await self._redis.delete(key)
            logger.info("trip_persona_cache invalidated: key=%s", key)
        except Exception:
            logger.warning(
                "trip_persona_cache invalidate failed: key=%s", key, exc_info=True
            )
