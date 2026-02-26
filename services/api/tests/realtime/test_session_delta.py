"""
Tests for L1 SessionPersonaDelta.

Uses a dict-backed FakeRedis to avoid real Redis connectivity.
All async tests use pytest-asyncio.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.api.realtime.session_delta import SessionPersonaDelta, _redis_key


# ---------------------------------------------------------------------------
# FakeRedis — dict-backed minimal implementation
# ---------------------------------------------------------------------------

class FakeRedis:
    """
    Minimal dict-backed Redis fake implementing the operations used by
    SessionPersonaDelta:
      hget, hset, hincrby, hgetall, expire, delete
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}
        self._ttls: dict[str, int] = {}

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

    async def expire(self, key: str, seconds: int) -> None:
        self._ttls[key] = seconds

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttls.pop(key, None)

    def key_exists(self, key: str) -> bool:
        return key in self._store

    def get_ttl(self, key: str) -> int | None:
        return self._ttls.get(key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def delta(fake_redis: FakeRedis) -> SessionPersonaDelta:
    return SessionPersonaDelta(fake_redis)


@pytest.fixture
def delta_no_redis() -> SessionPersonaDelta:
    """SessionPersonaDelta with redis=None for degradation tests."""
    return SessionPersonaDelta(None)


USER_ID = "user-111"
SESSION_ID = "sess-aaa"
TRIP_ID = "trip-xyz"


# ---------------------------------------------------------------------------
# Graceful degradation — redis=None
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_apply_signal_noop_when_no_redis(self, delta_no_redis):
        """apply_signal should silently succeed when redis is None."""
        await delta_no_redis.apply_signal(
            USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active"
        )
        # No exception raised — pass

    @pytest.mark.asyncio
    async def test_get_delta_returns_empty_when_no_redis(self, delta_no_redis):
        result = await delta_no_redis.get_delta(USER_ID, SESSION_ID)
        assert result == {}

    @pytest.mark.asyncio
    async def test_flush_noop_when_no_redis(self, delta_no_redis):
        mock_cache = AsyncMock()
        await delta_no_redis.flush_to_trip_cache(USER_ID, SESSION_ID, TRIP_ID, mock_cache)
        mock_cache.merge_session_delta.assert_not_called()


# ---------------------------------------------------------------------------
# apply_signal — positive signals
# ---------------------------------------------------------------------------

class TestApplySignalPositive:
    @pytest.mark.asyncio
    async def test_restaurant_slot_confirm_adjusts_food_priority(self, delta, fake_redis):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")

        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert "food_priority_adj" in result
        # direction=+1, weight=1.0, phase=active(1.0), step=0.1 => 0.1
        assert abs(result["food_priority_adj"] - 0.1) < 1e-6

    @pytest.mark.asyncio
    async def test_museum_slot_confirm_adjusts_culture_engagement(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "museum", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert "culture_engagement_adj" in result
        assert abs(result["culture_engagement_adj"] - 0.1) < 1e-6

    @pytest.mark.asyncio
    async def test_hike_adjusts_multiple_dimensions(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "hike", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # nature_preference weight=1.0 => adj=0.1
        assert abs(result["nature_preference_adj"] - 0.1) < 1e-6
        # energy_level weight=0.7 => adj=0.07
        assert abs(result["energy_level_adj"] - 0.07) < 1e-6

    @pytest.mark.asyncio
    async def test_discover_swipe_right_is_positive(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "discover_swipe_right", "museum", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result.get("culture_engagement_adj", 0) > 0

    @pytest.mark.asyncio
    async def test_post_loved_is_positive(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "post_loved", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result.get("food_priority_adj", 0) > 0


# ---------------------------------------------------------------------------
# apply_signal — negative signals
# ---------------------------------------------------------------------------

class TestApplySignalNegative:
    @pytest.mark.asyncio
    async def test_slot_skip_decrements_food_priority(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_skip", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result.get("food_priority_adj", 0) < 0
        assert abs(result["food_priority_adj"] - (-0.1)) < 1e-6

    @pytest.mark.asyncio
    async def test_card_dismissed_is_negative(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "card_dismissed", "museum", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result.get("culture_engagement_adj", 0) < 0

    @pytest.mark.asyncio
    async def test_discover_swipe_left_is_negative(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "discover_swipe_left", "park", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result.get("nature_preference_adj", 0) < 0


# ---------------------------------------------------------------------------
# Phase weights
# ---------------------------------------------------------------------------

class TestPhaseWeights:
    @pytest.mark.asyncio
    async def test_pre_trip_weight_0_4(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "pre_trip")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # direction=1, weight=1.0, phase=0.4, step=0.1 => 0.04
        assert abs(result["food_priority_adj"] - 0.04) < 1e-6

    @pytest.mark.asyncio
    async def test_post_trip_weight_3_0(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "post_trip")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # direction=1, weight=1.0, phase=3.0, step=0.1 => 0.3
        assert abs(result["food_priority_adj"] - 0.3) < 1e-6

    @pytest.mark.asyncio
    async def test_active_day1_weight_0_6(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "museum", "active_day1")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # direction=1, weight=1.0, phase=0.6, step=0.1 => 0.06
        assert abs(result["culture_engagement_adj"] - 0.06) < 1e-6

    @pytest.mark.asyncio
    async def test_active_day5_plus_weight_0_65(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "museum", "active_day5_plus")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert abs(result["culture_engagement_adj"] - 0.065) < 1e-6


# ---------------------------------------------------------------------------
# Accumulation across multiple signals
# ---------------------------------------------------------------------------

class TestAccumulation:
    @pytest.mark.asyncio
    async def test_multiple_signals_accumulate(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # 0.1 + 0.1 = 0.2
        assert abs(result["food_priority_adj"] - 0.2) < 1e-6

    @pytest.mark.asyncio
    async def test_mixed_signals_cancel_out(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_skip", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        # +0.1 - 0.1 = 0
        assert abs(result["food_priority_adj"]) < 1e-6

    @pytest.mark.asyncio
    async def test_signal_count_increments(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_skip", "museum", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result["signal_count"] == 2

    @pytest.mark.asyncio
    async def test_view_only_signal_increments_count_no_dim_adj(self, delta):
        """card_viewed has no directional component — only signal_count increments."""
        await delta.apply_signal(USER_ID, SESSION_ID, "card_viewed", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result["signal_count"] == 1
        assert result.get("food_priority_adj", 0.0) == 0.0

    @pytest.mark.asyncio
    async def test_unknown_category_increments_count_no_dim_adj(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "unknown_place", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result["signal_count"] == 1
        # No dimension adj keys except the mandatory ones at 0
        dim_adjs = {k: v for k, v in result.items() if k.endswith("_adj")}
        for v in dim_adjs.values():
            assert v == 0.0

    @pytest.mark.asyncio
    async def test_none_category_is_handled_gracefully(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", None, "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result["signal_count"] == 1


# ---------------------------------------------------------------------------
# TTL — sliding window
# ---------------------------------------------------------------------------

class TestTTL:
    @pytest.mark.asyncio
    async def test_ttl_set_on_apply_signal(self, delta, fake_redis):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        key = _redis_key(USER_ID, SESSION_ID)
        ttl = fake_redis.get_ttl(key)
        assert ttl == 30 * 60  # 1800 seconds

    @pytest.mark.asyncio
    async def test_ttl_reset_on_each_signal(self, delta, fake_redis):
        key = _redis_key(USER_ID, SESSION_ID)
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "museum", "active")
        # TTL should still be the sliding value (last set wins in FakeRedis)
        assert fake_redis.get_ttl(key) == 30 * 60


# ---------------------------------------------------------------------------
# get_delta
# ---------------------------------------------------------------------------

class TestGetDelta:
    @pytest.mark.asyncio
    async def test_returns_empty_on_cache_miss(self, delta):
        result = await delta.get_delta(USER_ID, "nonexistent-session")
        assert result == {}

    @pytest.mark.asyncio
    async def test_last_updated_is_iso_string(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert "last_updated" in result
        # Should be parseable as ISO datetime
        from datetime import datetime
        dt = datetime.fromisoformat(result["last_updated"])
        assert dt is not None


# ---------------------------------------------------------------------------
# flush_to_trip_cache
# ---------------------------------------------------------------------------

class TestFlushToTripCache:
    @pytest.mark.asyncio
    async def test_flush_calls_merge_session_delta(self, delta, fake_redis):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")

        mock_cache = AsyncMock()
        await delta.flush_to_trip_cache(USER_ID, SESSION_ID, TRIP_ID, mock_cache)

        mock_cache.merge_session_delta.assert_awaited_once()
        call_args = mock_cache.merge_session_delta.call_args
        assert call_args[0][0] == USER_ID
        assert call_args[0][1] == TRIP_ID
        delta_arg = call_args[0][2]
        assert delta_arg["signal_count"] == 1

    @pytest.mark.asyncio
    async def test_flush_deletes_session_key(self, delta, fake_redis):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")
        key = _redis_key(USER_ID, SESSION_ID)
        assert fake_redis.key_exists(key)

        mock_cache = AsyncMock()
        await delta.flush_to_trip_cache(USER_ID, SESSION_ID, TRIP_ID, mock_cache)

        assert not fake_redis.key_exists(key)

    @pytest.mark.asyncio
    async def test_flush_noop_when_empty_delta(self, delta):
        """Flush on an empty session (no signals yet) should not call merge."""
        mock_cache = AsyncMock()
        await delta.flush_to_trip_cache(USER_ID, "empty-session", TRIP_ID, mock_cache)
        mock_cache.merge_session_delta.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_passes_correct_delta_values(self, delta):
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "museum", "post_trip")
        # culture_engagement: direction=1, weight=1.0, phase=3.0, step=0.1 => 0.3
        mock_cache = AsyncMock()
        await delta.flush_to_trip_cache(USER_ID, SESSION_ID, TRIP_ID, mock_cache)

        delta_arg = mock_cache.merge_session_delta.call_args[0][2]
        assert abs(delta_arg["culture_engagement_adj"] - 0.3) < 1e-6


# ---------------------------------------------------------------------------
# Redis error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_apply_signal_survives_redis_error(self):
        """apply_signal should not propagate Redis exceptions."""
        bad_redis = AsyncMock()
        bad_redis.hget.side_effect = ConnectionError("Redis down")
        bad_redis.hset.side_effect = ConnectionError("Redis down")
        bad_redis.hincrby.side_effect = ConnectionError("Redis down")
        bad_redis.expire.side_effect = ConnectionError("Redis down")

        delta = SessionPersonaDelta(bad_redis)
        # Should not raise
        await delta.apply_signal(USER_ID, SESSION_ID, "slot_confirm", "restaurant", "active")

    @pytest.mark.asyncio
    async def test_get_delta_returns_empty_on_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.hgetall.side_effect = ConnectionError("Redis down")

        delta = SessionPersonaDelta(bad_redis)
        result = await delta.get_delta(USER_ID, SESSION_ID)
        assert result == {}
