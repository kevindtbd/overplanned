"""
Unit tests: Alteration Signal Tagger — Phase 1.3.

Covers:
- Empty / None input returns empty list
- slot_swap signals get "itinerary_alteration_swap" (weight 1.3)
- Date shift detection: 2+ slot_swap signals with different dayNumbers in window
- Category shift detection: 2+ skip/swap signals of same category in window
- Priority ordering: category_shift > date_shift > slot_swap
- Window boundary: signals across window boundary are in separate sessions
- Signals without required fields are skipped gracefully
- Weight values are within DB CHECK constraint [-1.0, 3.0]
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
import uuid

import pytest

from services.api.signals.alteration_tagger import detect_alterations
from services.api.tests.conftest import make_behavioral_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


def _dt(minutes_offset: int = 0) -> datetime:
    """Base datetime at 2026-02-24 12:00 UTC, offset by minutes."""
    base = datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes_offset)


def _swap(
    user_id: str,
    day_number: int | None = None,
    category: str | None = None,
    minutes_offset: int = 0,
    **overrides: Any,
) -> dict:
    """Build a slot_swap BehavioralSignal dict."""
    payload: dict = {}
    if day_number is not None:
        payload["dayNumber"] = day_number
    if category is not None:
        payload["category"] = category
    sig = make_behavioral_signal(
        user_id=user_id,
        signalType="slot_swap",
        createdAt=_dt(minutes_offset),
        **overrides,
    )
    sig["payload"] = payload
    return sig


def _skip(
    user_id: str,
    category: str | None = None,
    minutes_offset: int = 0,
    **overrides: Any,
) -> dict:
    """Build a slot_skip BehavioralSignal dict."""
    payload: dict = {}
    if category is not None:
        payload["category"] = category
    sig = make_behavioral_signal(
        user_id=user_id,
        signalType="slot_skip",
        createdAt=_dt(minutes_offset),
        **overrides,
    )
    sig["payload"] = payload
    return sig


# ===================================================================
# 1. Empty / trivial inputs
# ===================================================================

class TestEmptyInputs:
    """detect_alterations should handle empty / degenerate inputs."""

    def test_empty_list_returns_empty(self):
        assert detect_alterations([]) == []

    def test_non_swap_signals_produce_no_output(self):
        """slot_view and slot_confirm signals are not alteration signals."""
        user_id = _id()
        signals = [
            make_behavioral_signal(user_id=user_id, signalType="slot_view", createdAt=_dt()),
            make_behavioral_signal(user_id=user_id, signalType="slot_confirm", createdAt=_dt(1)),
        ]
        result = detect_alterations(signals)
        assert result == []


# ===================================================================
# 2. slot_swap — basic itinerary_alteration_swap
# ===================================================================

class TestSlotSwapBasic:
    """Single slot_swap → itinerary_alteration_swap (weight 1.3)."""

    def test_single_swap_gets_swap_subflow(self):
        user_id = _id()
        sig = _swap(user_id, day_number=1, category="dining")
        result = detect_alterations([sig])

        assert len(result) == 1
        r = result[0]
        assert r["signal_id"] == sig["id"]
        assert r["subflow"] == "itinerary_alteration_swap"
        assert r["signal_weight"] == 1.3

    def test_two_swaps_different_categories_both_get_swap_subflow(self):
        user_id = _id()
        sig1 = _swap(user_id, day_number=1, category="dining", minutes_offset=0)
        sig2 = _swap(user_id, day_number=1, category="culture", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        ids = {r["signal_id"] for r in result}
        assert sig1["id"] in ids
        assert sig2["id"] in ids
        for r in result:
            assert r["signal_weight"] == 1.3


# ===================================================================
# 3. Date shift detection
# ===================================================================

class TestDateShiftDetection:
    """2+ slot_swap signals with different dayNumbers in a window = date shift."""

    def test_two_swaps_different_days_gives_date_shift(self):
        user_id = _id()
        sig1 = _swap(user_id, day_number=1, minutes_offset=0)
        sig2 = _swap(user_id, day_number=3, minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        assert len(result) == 2
        for r in result:
            assert r["subflow"] == "itinerary_alteration_date"
            assert r["signal_weight"] == 1.3

    def test_two_swaps_same_day_does_not_give_date_shift(self):
        user_id = _id()
        sig1 = _swap(user_id, day_number=2, category="dining", minutes_offset=0)
        sig2 = _swap(user_id, day_number=2, category="museums", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        # same day — no date shift, each is just a plain swap
        for r in result:
            assert r["subflow"] == "itinerary_alteration_swap"

    def test_swap_without_day_number_not_counted_for_date_shift(self):
        """Swaps lacking dayNumber in payload do not contribute to date shift."""
        user_id = _id()
        sig1 = _swap(user_id, day_number=None, minutes_offset=0)
        sig2 = _swap(user_id, day_number=None, minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        # No day numbers — neither date shift nor category shift
        for r in result:
            assert r["subflow"] == "itinerary_alteration_swap"


# ===================================================================
# 4. Category shift detection
# ===================================================================

class TestCategoryShiftDetection:
    """2+ skip/swap of same category in window = itinerary_alteration_category."""

    def test_two_skips_same_category_gives_category_shift(self):
        user_id = _id()
        sig1 = _skip(user_id, category="dining", minutes_offset=0)
        sig2 = _skip(user_id, category="dining", minutes_offset=10)
        result = detect_alterations([sig1, sig2])

        assert len(result) == 2
        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"
            assert r["signal_weight"] == 1.4

    def test_two_swaps_same_category_gives_category_shift(self):
        user_id = _id()
        sig1 = _swap(user_id, category="museums", minutes_offset=0)
        sig2 = _swap(user_id, category="museums", minutes_offset=8)
        result = detect_alterations([sig1, sig2])

        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"
            assert r["signal_weight"] == 1.4

    def test_one_skip_one_swap_same_category_gives_category_shift(self):
        user_id = _id()
        sig1 = _skip(user_id, category="parks", minutes_offset=0)
        sig2 = _swap(user_id, category="parks", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"

    def test_only_one_skip_of_category_does_not_trigger_category_shift(self):
        user_id = _id()
        sig = _skip(user_id, category="culture", minutes_offset=0)
        result = detect_alterations([sig])

        # Single skip — not a category shift; not a swap either (slot_skip only)
        # slot_skip is not in _SWAP_TYPES, so it shouldn't get any tag alone
        assert result == []

    def test_two_skips_different_categories_no_category_shift(self):
        user_id = _id()
        sig1 = _skip(user_id, category="dining", minutes_offset=0)
        sig2 = _skip(user_id, category="culture", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        # Different categories — no category shift; slot_skip alone not enriched
        assert result == []


# ===================================================================
# 5. Priority ordering (category_shift > date_shift > slot_swap)
# ===================================================================

class TestPriorityOrdering:
    """Higher-priority pattern wins when a signal qualifies for multiple."""

    def test_category_shift_beats_date_shift(self):
        """If a swap qualifies for both date_shift and category_shift, category wins."""
        user_id = _id()
        # 2 swaps: different days (triggers date_shift) AND same category (triggers category_shift)
        sig1 = _swap(user_id, day_number=1, category="dining", minutes_offset=0)
        sig2 = _swap(user_id, day_number=2, category="dining", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"
            assert r["signal_weight"] == 1.4

    def test_category_shift_beats_plain_swap(self):
        """Signals in a category_shift window get category tag, not plain swap tag."""
        user_id = _id()
        sig1 = _swap(user_id, category="nightlife", minutes_offset=0)
        sig2 = _swap(user_id, category="nightlife", minutes_offset=3)
        result = detect_alterations([sig1, sig2])

        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"

    def test_date_shift_beats_plain_swap(self):
        """Signals in a date_shift window get date tag, not plain swap tag."""
        user_id = _id()
        sig1 = _swap(user_id, day_number=1, category="dining", minutes_offset=0)
        sig2 = _swap(user_id, day_number=5, category="culture", minutes_offset=5)
        result = detect_alterations([sig1, sig2])

        for r in result:
            assert r["subflow"] == "itinerary_alteration_date"


# ===================================================================
# 6. Session windowing
# ===================================================================

class TestSessionWindowing:
    """Signals in different windows are treated as separate sessions."""

    def test_signals_in_different_windows_not_grouped(self):
        """Signals 35 minutes apart (default 30-min window) are separate sessions."""
        user_id = _id()
        # Window 1: minute 0
        sig1 = _swap(user_id, day_number=1, category="dining", minutes_offset=0)
        # Window 2: minute 35 (past the 30-min boundary)
        sig2 = _swap(user_id, day_number=3, category="dining", minutes_offset=35)

        result = detect_alterations([sig1, sig2])
        # Each window has only 1 swap — no category_shift or date_shift
        # sig1 and sig2 are in different windows → each is a plain swap
        subflows = {r["signal_id"]: r["subflow"] for r in result}
        assert subflows.get(sig1["id"]) == "itinerary_alteration_swap"
        assert subflows.get(sig2["id"]) == "itinerary_alteration_swap"

    def test_signals_within_window_are_grouped(self):
        """Signals 25 minutes apart are in the same 30-min session window."""
        user_id = _id()
        sig1 = _swap(user_id, day_number=1, category="museums", minutes_offset=0)
        sig2 = _swap(user_id, day_number=2, category="museums", minutes_offset=25)

        result = detect_alterations([sig1, sig2])
        # Same window — same category — category_shift
        for r in result:
            assert r["subflow"] == "itinerary_alteration_category"

    def test_different_users_not_grouped(self):
        """Signals from different users are never in the same session window."""
        user_a = _id()
        user_b = _id()
        sig1 = _swap(user_a, day_number=1, category="dining", minutes_offset=0)
        sig2 = _swap(user_b, day_number=3, category="dining", minutes_offset=0)

        result = detect_alterations([sig1, sig2])
        # Each user has 1 swap in their own session — no cross-user grouping
        subflows = {r["signal_id"]: r["subflow"] for r in result}
        for subflow in subflows.values():
            assert subflow == "itinerary_alteration_swap"

    def test_custom_window_minutes(self):
        """Custom window_minutes=10 creates finer-grained sessions."""
        user_id = _id()
        # 12 minutes apart with a 10-min window = different windows
        sig1 = _swap(user_id, day_number=1, category="culture", minutes_offset=0)
        sig2 = _swap(user_id, day_number=3, category="culture", minutes_offset=12)

        result = detect_alterations([sig1, sig2], window_minutes=10)
        # Different windows (12 > 10) — each is a plain swap, no date or category shift
        for r in result:
            assert r["subflow"] == "itinerary_alteration_swap"


# ===================================================================
# 7. Malformed / missing fields
# ===================================================================

class TestMalformedInputs:
    """Signals missing required fields are skipped without raising."""

    def test_signal_without_user_id_is_skipped(self):
        sig = make_behavioral_signal(signalType="slot_swap", createdAt=_dt())
        sig["userId"] = None
        result = detect_alterations([sig])
        assert result == []

    def test_signal_without_created_at_is_skipped(self):
        user_id = _id()
        sig = make_behavioral_signal(user_id=user_id, signalType="slot_swap")
        sig["createdAt"] = None
        result = detect_alterations([sig])
        assert result == []

    def test_signal_without_id_not_enriched(self):
        user_id = _id()
        sig = make_behavioral_signal(user_id=user_id, signalType="slot_swap", createdAt=_dt())
        sig["id"] = None
        result = detect_alterations([sig])
        assert result == []


# ===================================================================
# 8. Weight constraint compliance
# ===================================================================

class TestWeightConstraints:
    """All emitted signal_weight values must be within DB CHECK [-1.0, 3.0]."""

    def test_swap_weight_in_range(self):
        user_id = _id()
        sig = _swap(user_id, minutes_offset=0)
        result = detect_alterations([sig])
        for r in result:
            assert -1.0 <= r["signal_weight"] <= 3.0

    def test_date_shift_weight_in_range(self):
        user_id = _id()
        sig1 = _swap(user_id, day_number=1, minutes_offset=0)
        sig2 = _swap(user_id, day_number=2, minutes_offset=5)
        result = detect_alterations([sig1, sig2])
        for r in result:
            assert -1.0 <= r["signal_weight"] <= 3.0

    def test_category_shift_weight_in_range(self):
        user_id = _id()
        sig1 = _swap(user_id, category="dining", minutes_offset=0)
        sig2 = _swap(user_id, category="dining", minutes_offset=5)
        result = detect_alterations([sig1, sig2])
        for r in result:
            assert -1.0 <= r["signal_weight"] <= 3.0
