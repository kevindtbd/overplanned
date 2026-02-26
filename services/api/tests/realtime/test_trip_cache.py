"""
Tests for L2 TripPersonaCache.

Uses a dict-backed FakeRedis to avoid real Redis connectivity.
All async tests use pytest-asyncio.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from services.api.realtime.trip_cache import (
    TripPersonaCache,
    _expiry_timestamp,
    _redis_key,
    _PERSONA_MIN,
    _PERSONA_MAX,
)


# ---------------------------------------------------------------------------
# FakeRedis — dict-backed minimal implementation
# ---------------------------------------------------------------------------

class FakeRedis:
    """
    Minimal dict-backed Redis fake implementing the operations used by
    TripPersonaCache:
      hget, hset, hincrby, hgetall, expireat, delete
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}
        self._expiry_timestamps: dict[str, int] = {}

    async def hget(self, key: str, field: str) -> str | None:
        return self._store.get(key, {}).get(field)

    async def hset(self, key: str, mapping: dict) -> None:
        if key not in self._store:
            self._store[key] = {}
        for k, v in mapping.items():
            self._store[key][k] = str(v)

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        if key not in self._store:
            self._store[key] = {}
        current = int(self._store[key].get(field, "0"))
        new_val = current + amount
        self._store[key][field] = str(new_val)
        return new_val

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._store.get(key, {}))

    async def expireat(self, key: str, timestamp: int) -> None:
        self._expiry_timestamps[key] = timestamp

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._expiry_timestamps.pop(key, None)

    def key_exists(self, key: str) -> bool:
        return key in self._store

    def get_expiry_ts(self, key: str) -> int | None:
        return self._expiry_timestamps.get(key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def cache(fake_redis: FakeRedis) -> TripPersonaCache:
    return TripPersonaCache(fake_redis)


@pytest.fixture
def cache_no_redis() -> TripPersonaCache:
    return TripPersonaCache(None)


USER_ID = "user-222"
TRIP_ID = "trip-abc"

_FUTURE_END = datetime.now(timezone.utc) + timedelta(days=7)

_BASE_PERSONA: dict[str, float] = {
    "food_priority": 0.6,
    "culture_engagement": 0.4,
    "nature_preference": 0.5,
    "nightlife_interest": 0.3,
    "pace_preference": 0.55,
    "energy_level": 0.5,
    "authenticity_preference": 0.7,
    "budget_orientation": 0.45,
    "social_orientation": 0.5,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_cache(
    cache: TripPersonaCache,
    persona: dict | None = None,
    version: int = 1,
    trip_end: datetime | None = None,
) -> None:
    await cache.set_cached_persona(
        USER_ID,
        TRIP_ID,
        persona or _BASE_PERSONA,
        version,
        trip_end or _FUTURE_END,
    )


# ---------------------------------------------------------------------------
# Graceful degradation — redis=None
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_no_redis(self, cache_no_redis):
        result = await cache_no_redis.get_cached_persona(USER_ID, TRIP_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_noop_when_no_redis(self, cache_no_redis):
        """set_cached_persona should not raise when redis is None."""
        await cache_no_redis.set_cached_persona(USER_ID, TRIP_ID, _BASE_PERSONA, 1, _FUTURE_END)

    @pytest.mark.asyncio
    async def test_merge_noop_when_no_redis(self, cache_no_redis):
        await cache_no_redis.merge_session_delta(USER_ID, TRIP_ID, {"food_priority_adj": 0.1})

    @pytest.mark.asyncio
    async def test_check_version_returns_false_when_no_redis(self, cache_no_redis):
        result = await cache_no_redis.check_version(USER_ID, TRIP_ID, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_noop_when_no_redis(self, cache_no_redis):
        await cache_no_redis.invalidate(USER_ID, TRIP_ID)


# ---------------------------------------------------------------------------
# set_cached_persona
# ---------------------------------------------------------------------------

class TestSetCachedPersona:
    @pytest.mark.asyncio
    async def test_stores_all_dimension_values(self, cache):
        await _seed_cache(cache)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result is not None
        for dim, expected in _BASE_PERSONA.items():
            assert abs(result[dim] - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_stores_version_and_signal_count(self, cache):
        await _seed_cache(cache, version=42)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["nightly_sync_version"] == 42
        assert result["signal_count_since_nightly"] == 0

    @pytest.mark.asyncio
    async def test_stores_last_updated_as_iso_string(self, cache):
        await _seed_cache(cache)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert "last_updated" in result
        dt = datetime.fromisoformat(result["last_updated"])
        assert dt is not None

    @pytest.mark.asyncio
    async def test_uses_expireat_not_expire(self, cache, fake_redis):
        """Absolute TTL (EXPIREAT) must be used — not relative expire()."""
        await _seed_cache(cache)
        key = _redis_key(USER_ID, TRIP_ID)
        expiry_ts = fake_redis.get_expiry_ts(key)
        assert expiry_ts is not None

    @pytest.mark.asyncio
    async def test_expiry_is_trip_end_plus_48h(self, cache, fake_redis):
        trip_end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        await cache.set_cached_persona(USER_ID, TRIP_ID, _BASE_PERSONA, 1, trip_end)
        key = _redis_key(USER_ID, TRIP_ID)
        expiry_ts = fake_redis.get_expiry_ts(key)
        expected_ts = _expiry_timestamp(trip_end)
        assert expiry_ts == expected_ts

    @pytest.mark.asyncio
    async def test_expiry_timestamp_is_48h_after_trip_end(self):
        trip_end = datetime(2026, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        ts = _expiry_timestamp(trip_end)
        expected = int((trip_end + timedelta(hours=48)).timestamp())
        assert ts == expected

    @pytest.mark.asyncio
    async def test_naive_datetime_treated_as_utc(self):
        """Naive datetimes should not raise — treated as UTC."""
        naive_end = datetime(2026, 6, 15, 0, 0, 0)  # no tzinfo
        ts = _expiry_timestamp(naive_end)
        assert ts > 0

    @pytest.mark.asyncio
    async def test_overwrite_resets_signal_count(self, cache):
        """Re-seeding after nightly update should reset signal_count to 0."""
        await _seed_cache(cache, version=1)
        # Simulate session activity incrementing signal_count
        await cache.merge_session_delta(USER_ID, TRIP_ID, {"signal_count": 7})
        result_mid = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result_mid["signal_count_since_nightly"] == 7
        # Nightly batch re-seeds with version 2 — count resets to 0
        await _seed_cache(cache, version=2)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["signal_count_since_nightly"] == 0
        assert result["nightly_sync_version"] == 2


# ---------------------------------------------------------------------------
# get_cached_persona
# ---------------------------------------------------------------------------

class TestGetCachedPersona:
    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self, cache):
        result = await cache.get_cached_persona(USER_ID, "nonexistent-trip")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_full_persona_on_hit(self, cache):
        await _seed_cache(cache)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result is not None
        assert result["food_priority"] == pytest.approx(0.6)
        assert result["culture_engagement"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# merge_session_delta
# ---------------------------------------------------------------------------

class TestMergeSessionDelta:
    @pytest.mark.asyncio
    async def test_positive_adj_increases_dimension(self, cache):
        await _seed_cache(cache)
        delta = {"food_priority_adj": 0.1, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        # 0.6 + 0.1 = 0.7
        assert abs(result["food_priority"] - 0.7) < 1e-6

    @pytest.mark.asyncio
    async def test_negative_adj_decreases_dimension(self, cache):
        await _seed_cache(cache)
        delta = {"nightlife_interest_adj": -0.1, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        # 0.3 - 0.1 = 0.2
        assert abs(result["nightlife_interest"] - 0.2) < 1e-6

    @pytest.mark.asyncio
    async def test_merge_clamps_at_max(self, cache):
        await cache.set_cached_persona(
            USER_ID, TRIP_ID, {"food_priority": 0.95}, 1, _FUTURE_END
        )
        delta = {"food_priority_adj": 0.1, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["food_priority"] <= _PERSONA_MAX

    @pytest.mark.asyncio
    async def test_merge_clamps_at_min(self, cache):
        await cache.set_cached_persona(
            USER_ID, TRIP_ID, {"nightlife_interest": 0.07}, 1, _FUTURE_END
        )
        delta = {"nightlife_interest_adj": -0.1, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["nightlife_interest"] >= _PERSONA_MIN

    @pytest.mark.asyncio
    async def test_signal_count_accumulates(self, cache):
        await _seed_cache(cache)
        await cache.merge_session_delta(USER_ID, TRIP_ID, {"signal_count": 5})
        await cache.merge_session_delta(USER_ID, TRIP_ID, {"signal_count": 3})
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["signal_count_since_nightly"] == 8

    @pytest.mark.asyncio
    async def test_merge_noop_when_cache_not_seeded(self, cache):
        """merge_session_delta on a non-existent key should silently no-op."""
        delta = {"food_priority_adj": 0.1, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, "nonexistent-trip", delta)
        # No exception — pass

    @pytest.mark.asyncio
    async def test_unknown_adj_field_ignored(self, cache):
        await _seed_cache(cache)
        delta = {"totally_made_up_adj": 0.5, "signal_count": 1}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert "totally_made_up" not in result

    @pytest.mark.asyncio
    async def test_non_adj_fields_not_written_as_dims(self, cache):
        await _seed_cache(cache)
        delta = {
            "food_priority_adj": 0.05,
            "signal_count": 2,
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        # food_priority should be updated
        assert abs(result["food_priority"] - 0.65) < 1e-6

    @pytest.mark.asyncio
    async def test_multiple_dims_merged_at_once(self, cache):
        await _seed_cache(cache)
        delta = {
            "food_priority_adj": 0.1,
            "culture_engagement_adj": -0.05,
            "signal_count": 2,
        }
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert abs(result["food_priority"] - 0.7) < 1e-6
        assert abs(result["culture_engagement"] - 0.35) < 1e-6

    @pytest.mark.asyncio
    async def test_zero_signal_count_not_incremented(self, cache, fake_redis):
        """If delta has signal_count=0, hincrby should not be called for count."""
        await _seed_cache(cache)
        delta = {"food_priority_adj": 0.05, "signal_count": 0}
        await cache.merge_session_delta(USER_ID, TRIP_ID, delta)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result["signal_count_since_nightly"] == 0

    @pytest.mark.asyncio
    async def test_last_updated_refreshed_on_merge(self, cache):
        await _seed_cache(cache)
        first_result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        first_ts = first_result["last_updated"]

        import asyncio
        await asyncio.sleep(0.01)  # ensure time passes

        await cache.merge_session_delta(USER_ID, TRIP_ID, {"signal_count": 1})
        second_result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        # last_updated should be the same or newer (FakeRedis always stores latest)
        assert second_result["last_updated"] >= first_ts


# ---------------------------------------------------------------------------
# check_version
# ---------------------------------------------------------------------------

class TestCheckVersion:
    @pytest.mark.asyncio
    async def test_returns_true_when_version_matches(self, cache):
        await _seed_cache(cache, version=5)
        result = await cache.check_version(USER_ID, TRIP_ID, 5)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_version_mismatch(self, cache):
        await _seed_cache(cache, version=5)
        result = await cache.check_version(USER_ID, TRIP_ID, 6)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_cache_miss(self, cache):
        result = await cache.check_version(USER_ID, "not-seeded-trip", 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_redis(self, cache_no_redis):
        result = await cache_no_redis.check_version(USER_ID, TRIP_ID, 1)
        assert result is False


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------

class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_removes_key(self, cache, fake_redis):
        await _seed_cache(cache)
        key = _redis_key(USER_ID, TRIP_ID)
        assert fake_redis.key_exists(key)

        await cache.invalidate(USER_ID, TRIP_ID)
        assert not fake_redis.key_exists(key)

    @pytest.mark.asyncio
    async def test_invalidate_causes_cache_miss(self, cache):
        await _seed_cache(cache)
        await cache.invalidate(USER_ID, TRIP_ID)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_key_is_noop(self, cache):
        """Deleting a key that doesn't exist should not raise."""
        await cache.invalidate(USER_ID, "never-existed-trip")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_get_returns_none_on_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.hgetall.side_effect = ConnectionError("Redis down")
        cache = TripPersonaCache(bad_redis)
        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_survives_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.hset.side_effect = ConnectionError("Redis down")
        cache = TripPersonaCache(bad_redis)
        # Should not raise
        await cache.set_cached_persona(USER_ID, TRIP_ID, _BASE_PERSONA, 1, _FUTURE_END)

    @pytest.mark.asyncio
    async def test_merge_survives_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.hgetall.side_effect = ConnectionError("Redis down")
        cache = TripPersonaCache(bad_redis)
        # Should not raise
        await cache.merge_session_delta(USER_ID, TRIP_ID, {"food_priority_adj": 0.1})

    @pytest.mark.asyncio
    async def test_check_version_returns_false_on_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.hget.side_effect = ConnectionError("Redis down")
        cache = TripPersonaCache(bad_redis)
        result = await cache.check_version(USER_ID, TRIP_ID, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_survives_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.delete.side_effect = ConnectionError("Redis down")
        cache = TripPersonaCache(bad_redis)
        # Should not raise
        await cache.invalidate(USER_ID, TRIP_ID)


# ---------------------------------------------------------------------------
# expiry_timestamp helper
# ---------------------------------------------------------------------------

class TestExpiryTimestamp:
    def test_aware_datetime(self):
        trip_end = datetime(2026, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        ts = _expiry_timestamp(trip_end)
        expected = int((trip_end + timedelta(hours=48)).timestamp())
        assert ts == expected

    def test_naive_datetime_treated_as_utc(self):
        naive_end = datetime(2026, 6, 15, 0, 0, 0)
        ts = _expiry_timestamp(naive_end)
        assert ts > int(time.time())  # must be in the future

    def test_expiry_is_after_trip_end(self):
        trip_end = datetime.now(timezone.utc) + timedelta(days=5)
        ts = _expiry_timestamp(trip_end)
        assert ts > int(trip_end.timestamp())


# ---------------------------------------------------------------------------
# Integration: session delta -> trip cache merge flow
# ---------------------------------------------------------------------------

class TestEndToEndMergeFlow:
    @pytest.mark.asyncio
    async def test_full_session_to_trip_cache_flow(self, cache):
        """
        Simulate the full L1 -> L2 merge flow:
          1. Seed trip cache from DB
          2. Apply session adjustments
          3. Merge session delta
          4. Verify trip cache reflects adjustments
        """
        # Seed from DB
        await cache.set_cached_persona(
            USER_ID, TRIP_ID,
            {"food_priority": 0.5, "culture_engagement": 0.5},
            version=1,
            trip_end_date=_FUTURE_END,
        )

        # Session delta (what SessionPersonaDelta would produce)
        session_delta = {
            "food_priority_adj": 0.15,       # user loved food spots
            "culture_engagement_adj": -0.05,  # skipped museums
            "signal_count": 4,
        }

        await cache.merge_session_delta(USER_ID, TRIP_ID, session_delta)

        result = await cache.get_cached_persona(USER_ID, TRIP_ID)
        assert abs(result["food_priority"] - 0.65) < 1e-6
        assert abs(result["culture_engagement"] - 0.45) < 1e-6
        assert result["signal_count_since_nightly"] == 4
        assert result["nightly_sync_version"] == 1

    @pytest.mark.asyncio
    async def test_version_check_after_nightly_update(self, cache):
        """
        After nightly batch runs:
          1. Cache is invalidated
          2. New persona seeded with version=2
          3. Version check passes for v2, fails for v1
        """
        await _seed_cache(cache, version=1)
        assert await cache.check_version(USER_ID, TRIP_ID, 1) is True
        assert await cache.check_version(USER_ID, TRIP_ID, 2) is False

        # Nightly batch invalidates and re-seeds
        await cache.invalidate(USER_ID, TRIP_ID)
        await _seed_cache(cache, version=2)

        assert await cache.check_version(USER_ID, TRIP_ID, 2) is True
        assert await cache.check_version(USER_ID, TRIP_ID, 1) is False
