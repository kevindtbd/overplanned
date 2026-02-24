"""
Tests for rejection_recovery.py — Phase 5.1.

Covers:
  - Burst detection: 3+ rejections within 120s triggers recovery
  - Burst detection: 2 rejections does NOT trigger
  - Burst detection: 3 rejections spread over >120s does NOT trigger
  - Once-per-trip: second call for same trip returns None
  - Weight cap: signal_weight == RECOVERY_WEIGHT_CAP (-0.4)
  - Weight cap within DB CHECK range [-1.0, 3.0]
  - Vibe analysis: anti_vibes derived from rejected slot vibe tags
  - Vibe analysis: slotType used as fallback when no vibeTags
  - Inversion: suggested_vibes are different from anti_vibes
  - suggested_vibes is non-empty even when no anti_vibes mapped
  - signal_weight not returned to clients (server-only field confirmed present in return)
  - DB logging failure does not suppress recovery result
  - reset_fired_trips allows re-triggering in tests
"""

from __future__ import annotations

import time
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from services.api.subflows.rejection_recovery import (
    check_rejection_burst,
    reset_fired_trips,
    BURST_THRESHOLD,
    BURST_WINDOW_SECONDS,
    RECOVERY_WEIGHT_CAP,
    _is_burst,
    _extract_anti_vibes,
    _invert_vibes,
    _get_vibe_slugs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_ts() -> float:
    return time.time()


def make_timestamps(n: int, spread_seconds: float = 10.0) -> list[float]:
    """Generate n timestamps spaced spread_seconds apart, ending at now."""
    base = now_ts()
    return [base - (n - 1 - i) * spread_seconds for i in range(n)]


def make_slot(vibes: list[str] | None = None, slot_type: str = "anchor") -> dict:
    """Build a minimal rejected slot dict."""
    slot: dict = {"slotType": slot_type}
    if vibes is not None:
        slot["vibeTags"] = [{"slug": v} for v in vibes]
    return slot


def build_mock_pool(raise_on_execute: bool = False) -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()

    if raise_on_execute:
        conn.execute = AsyncMock(side_effect=Exception("DB error"))
    else:
        conn.execute = AsyncMock(return_value=None)

    @asynccontextmanager
    async def acquire_ctx():
        yield conn

    pool.acquire = acquire_ctx
    return pool


# ---------------------------------------------------------------------------
# Setup: always reset the in-memory guard before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_fired_trips():
    reset_fired_trips()
    yield
    reset_fired_trips()


# ---------------------------------------------------------------------------
# _is_burst unit tests
# ---------------------------------------------------------------------------

class TestIsBurst:
    def test_three_within_window_triggers(self):
        ts = make_timestamps(3, spread_seconds=30.0)
        assert _is_burst(ts) is True

    def test_two_does_not_trigger(self):
        ts = make_timestamps(2, spread_seconds=10.0)
        assert _is_burst(ts) is False

    def test_empty_list_does_not_trigger(self):
        assert _is_burst([]) is False

    def test_three_outside_window_does_not_trigger(self):
        """3 rejections spread over > BURST_WINDOW_SECONDS: not a burst."""
        base = now_ts()
        ts = [
            base - BURST_WINDOW_SECONDS - 200,
            base - BURST_WINDOW_SECONDS - 100,
            base,  # only 1 within window
        ]
        assert _is_burst(ts) is False

    def test_five_within_window_triggers(self):
        ts = make_timestamps(5, spread_seconds=15.0)
        assert _is_burst(ts) is True

    def test_exactly_at_window_boundary(self):
        """Rejection exactly at window_start should be included."""
        base = now_ts()
        ts = [
            base - BURST_WINDOW_SECONDS,  # exactly at boundary — included
            base - 60,
            base,
        ]
        assert _is_burst(ts) is True

    def test_burst_threshold_is_3(self):
        assert BURST_THRESHOLD == 3

    def test_burst_window_is_120(self):
        assert BURST_WINDOW_SECONDS == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# _extract_anti_vibes unit tests
# ---------------------------------------------------------------------------

class TestExtractAntiVibes:
    def test_most_common_vibes_returned(self):
        slots = [
            make_slot(vibes=["touristy", "crowded"]),
            make_slot(vibes=["touristy"]),
            make_slot(vibes=["expensive"]),
        ]
        anti = _extract_anti_vibes(slots)
        # "touristy" appears twice — should be first
        assert anti[0] == "touristy"

    def test_max_three_returned(self):
        slots = [
            make_slot(vibes=["a"]),
            make_slot(vibes=["b"]),
            make_slot(vibes=["c"]),
            make_slot(vibes=["d"]),
            make_slot(vibes=["e"]),
        ]
        anti = _extract_anti_vibes(slots)
        assert len(anti) <= 3

    def test_fallback_to_slot_type_when_no_vibes(self):
        slots = [
            make_slot(vibes=[], slot_type="museum"),
            make_slot(vibes=[], slot_type="museum"),
        ]
        anti = _extract_anti_vibes(slots)
        assert "museum" in anti

    def test_empty_slots_returns_empty(self):
        assert _extract_anti_vibes([]) == []

    def test_vibe_slugs_lowercased(self):
        slots = [make_slot(vibes=["Touristy"])]
        anti = _extract_anti_vibes(slots)
        assert "touristy" in anti


# ---------------------------------------------------------------------------
# _invert_vibes unit tests
# ---------------------------------------------------------------------------

class TestInvertVibes:
    def test_known_vibe_returns_alternatives(self):
        alts = _invert_vibes(["touristy"])
        assert len(alts) > 0
        assert "touristy" not in alts

    def test_unknown_vibe_returns_defaults(self):
        alts = _invert_vibes(["completely-unknown-vibe-xyz"])
        assert len(alts) > 0  # default fallback

    def test_empty_anti_vibes_returns_defaults(self):
        alts = _invert_vibes([])
        assert len(alts) > 0

    def test_max_five_suggestions(self):
        # Many anti-vibes
        anti = ["touristy", "crowded", "expensive", "fine-dining", "chain"]
        alts = _invert_vibes(anti)
        assert len(alts) <= 5

    def test_no_duplicates_in_suggestions(self):
        anti = ["touristy", "crowded", "expensive"]
        alts = _invert_vibes(anti)
        assert len(alts) == len(set(alts))


# ---------------------------------------------------------------------------
# check_rejection_burst integration tests
# ---------------------------------------------------------------------------

class TestCheckRejectionBurst:
    @pytest.mark.asyncio
    async def test_burst_returns_recovery_dict(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        slots = [make_slot(vibes=["touristy"])] * 3
        pool = build_mock_pool()

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-1",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        assert result is not None
        assert result["trigger"] is True

    @pytest.mark.asyncio
    async def test_non_burst_returns_none(self):
        ts = make_timestamps(2, spread_seconds=10.0)
        slots = [make_slot()] * 2
        pool = build_mock_pool()

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-2",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_once_per_trip_second_call_returns_none(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        slots = [make_slot()] * 3
        pool = build_mock_pool()

        # First call — should trigger
        result1 = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-once",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        # Second call for same trip — should be suppressed
        result2 = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-once",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        assert result1 is not None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_different_trips_fire_independently(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        slots = [make_slot()] * 3
        pool = build_mock_pool()

        result_a = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-A",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )
        result_b = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-B",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        assert result_a is not None
        assert result_b is not None

    @pytest.mark.asyncio
    async def test_signal_weight_within_cap(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        pool = build_mock_pool()

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-w",
            rejection_timestamps=ts,
            rejected_slots=[make_slot()],
            db_pool=pool,
        )

        assert result is not None
        assert result["signal_weight"] <= RECOVERY_WEIGHT_CAP
        # Must be within DB CHECK [-1.0, 3.0]
        assert result["signal_weight"] >= -1.0

    @pytest.mark.asyncio
    async def test_recovery_weight_cap_is_minus_0_4(self):
        assert RECOVERY_WEIGHT_CAP == pytest.approx(-0.4)

    @pytest.mark.asyncio
    async def test_anti_vibes_in_result(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        slots = [
            make_slot(vibes=["touristy"]),
            make_slot(vibes=["touristy"]),
            make_slot(vibes=["crowded"]),
        ]
        pool = build_mock_pool()

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-vibes",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )

        assert result is not None
        assert "touristy" in result["anti_vibes"]

    @pytest.mark.asyncio
    async def test_suggested_vibes_non_empty(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        pool = build_mock_pool()

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-sv",
            rejection_timestamps=ts,
            rejected_slots=[make_slot()],
            db_pool=pool,
        )

        assert result is not None
        assert isinstance(result["suggested_vibes"], list)
        assert len(result["suggested_vibes"]) > 0

    @pytest.mark.asyncio
    async def test_db_failure_does_not_suppress_result(self):
        """If the DB log fails, we still return the recovery suggestion."""
        ts = make_timestamps(3, spread_seconds=20.0)
        pool = build_mock_pool(raise_on_execute=True)

        result = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-dbfail",
            rejection_timestamps=ts,
            rejected_slots=[make_slot(vibes=["touristy"])],
            db_pool=pool,
        )

        assert result is not None
        assert result["trigger"] is True

    @pytest.mark.asyncio
    async def test_reset_fired_trips_allows_retrigger(self):
        ts = make_timestamps(3, spread_seconds=20.0)
        slots = [make_slot()] * 3
        pool = build_mock_pool()

        result1 = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-reset",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )
        assert result1 is not None

        reset_fired_trips()

        result2 = await check_rejection_burst(
            user_id="user-1",
            trip_id="trip-reset",
            rejection_timestamps=ts,
            rejected_slots=slots,
            db_pool=pool,
        )
        assert result2 is not None


# ---------------------------------------------------------------------------
# Vibe slug extraction
# ---------------------------------------------------------------------------

class TestGetVibeSlugs:
    def test_list_of_dicts_with_slug(self):
        slot = {"vibeTags": [{"slug": "ramen"}, {"slug": "izakaya"}]}
        slugs = _get_vibe_slugs(slot)
        assert "ramen" in slugs
        assert "izakaya" in slugs

    def test_list_of_strings(self):
        slot = {"vibeTags": ["ramen", "izakaya"]}
        slugs = _get_vibe_slugs(slot)
        assert "ramen" in slugs

    def test_empty_returns_empty(self):
        assert _get_vibe_slugs({}) == []

    def test_none_vibe_tags_returns_empty(self):
        slot = {"vibeTags": None}
        assert _get_vibe_slugs(slot) == []
