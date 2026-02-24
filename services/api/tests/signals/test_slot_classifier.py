"""
Unit tests: Slot Outcome Classifier — Phase 1.1.

Covers:
- All 5 classification states with happy-path inputs
- Priority ordering (pivot_replaced beats confirmed_attended)
- Edge cases: None / missing fields, wasSwapped without pivotEventId
- get_completion_weight() returns correct values for each state
- COMPLETION_WEIGHTS dict completeness and range compliance
"""

import pytest

from services.api.posttrip.slot_classifier import (
    classify_slot_outcome,
    get_completion_weight,
    COMPLETION_WEIGHTS,
    SlotCompletionSignal,
)
from services.api.tests.conftest import make_itinerary_slot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot(**overrides) -> dict:
    """Build a minimal ItinerarySlot dict for classifier tests."""
    return make_itinerary_slot(**overrides)


# ===================================================================
# 1. Happy-path classification paths
# ===================================================================

class TestClassifySlotOutcome:
    """Tests for classify_slot_outcome() — all 5 outcome states."""

    def test_pivot_replaced_when_pivot_event_and_was_swapped(self):
        """pivot_replaced when pivotEventId is set AND wasSwapped=True."""
        slot = _slot(pivotEventId="pivot-abc", wasSwapped=True, status="proposed")
        result = classify_slot_outcome(slot)
        assert result == "pivot_replaced"

    def test_confirmed_attended_when_status_completed(self):
        """confirmed_attended when status == 'completed'."""
        slot = _slot(status="completed", pivotEventId=None, wasSwapped=False)
        result = classify_slot_outcome(slot)
        assert result == "confirmed_attended"

    def test_confirmed_skipped_when_status_skipped(self):
        """confirmed_skipped when status == 'skipped'."""
        slot = _slot(status="skipped", pivotEventId=None, wasSwapped=False)
        result = classify_slot_outcome(slot)
        assert result == "confirmed_skipped"

    def test_likely_attended_when_status_confirmed(self):
        """likely_attended when status == 'confirmed'."""
        slot = _slot(status="confirmed", pivotEventId=None, wasSwapped=False)
        result = classify_slot_outcome(slot)
        assert result == "likely_attended"

    def test_likely_attended_when_status_active(self):
        """likely_attended when status == 'active'."""
        slot = _slot(status="active", pivotEventId=None, wasSwapped=False)
        result = classify_slot_outcome(slot)
        assert result == "likely_attended"

    def test_no_show_ambiguous_for_proposed_status(self):
        """no_show_ambiguous for 'proposed' (never confirmed)."""
        slot = _slot(status="proposed")
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"

    def test_no_show_ambiguous_for_archived_status(self):
        """no_show_ambiguous for 'archived'."""
        slot = _slot(status="archived")
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"

    def test_no_show_ambiguous_for_unknown_status(self):
        """no_show_ambiguous for an unrecognised status string."""
        slot = _slot(status="some_future_status")
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"


# ===================================================================
# 2. Priority ordering
# ===================================================================

class TestClassifyPriority:
    """pivot_replaced must beat all other statuses when conditions are met."""

    def test_pivot_replaced_beats_completed(self):
        """Even if status == 'completed', pivot_replaced wins when conditions met."""
        slot = _slot(pivotEventId="pivot-xyz", wasSwapped=True, status="completed")
        result = classify_slot_outcome(slot)
        assert result == "pivot_replaced"

    def test_pivot_replaced_beats_skipped(self):
        """pivot_replaced wins over skipped."""
        slot = _slot(pivotEventId="pivot-xyz", wasSwapped=True, status="skipped")
        result = classify_slot_outcome(slot)
        assert result == "pivot_replaced"

    def test_pivot_id_without_was_swapped_does_not_pivot_replace(self):
        """Having a pivotEventId but wasSwapped=False should NOT give pivot_replaced."""
        slot = _slot(pivotEventId="pivot-xyz", wasSwapped=False, status="completed")
        result = classify_slot_outcome(slot)
        assert result == "confirmed_attended"

    def test_was_swapped_without_pivot_id_does_not_pivot_replace(self):
        """wasSwapped=True but no pivotEventId should NOT give pivot_replaced."""
        slot = _slot(pivotEventId=None, wasSwapped=True, status="completed")
        result = classify_slot_outcome(slot)
        assert result == "confirmed_attended"


# ===================================================================
# 3. Edge cases — None / missing fields
# ===================================================================

class TestClassifyEdgeCases:
    """Robustness against missing or None field values."""

    def test_empty_dict_gives_no_show_ambiguous(self):
        """An entirely empty dict should classify as no_show_ambiguous."""
        result = classify_slot_outcome({})
        assert result == "no_show_ambiguous"

    def test_none_status_gives_no_show_ambiguous(self):
        """None status (missing field) falls through to no_show_ambiguous."""
        slot = _slot(status=None)
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"

    def test_none_pivot_event_id_not_pivot_replaced(self):
        """None pivotEventId with wasSwapped=True should not give pivot_replaced."""
        slot = _slot(pivotEventId=None, wasSwapped=True, status="skipped")
        result = classify_slot_outcome(slot)
        assert result == "confirmed_skipped"

    def test_missing_was_swapped_treated_as_false(self):
        """Missing wasSwapped key is treated as False — no pivot_replaced."""
        slot = {"pivotEventId": "pivot-abc", "status": "completed"}
        result = classify_slot_outcome(slot)
        assert result == "confirmed_attended"

    def test_missing_pivot_event_id_treated_as_none(self):
        """Missing pivotEventId key is treated as None."""
        slot = {"wasSwapped": True, "status": "proposed"}
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"

    def test_factory_default_slot_is_no_show_ambiguous(self):
        """Default factory slot (status='proposed') classifies as no_show_ambiguous."""
        slot = make_itinerary_slot()
        result = classify_slot_outcome(slot)
        assert result == "no_show_ambiguous"


# ===================================================================
# 4. get_completion_weight()
# ===================================================================

class TestGetCompletionWeight:
    """Tests for get_completion_weight() accessor."""

    def test_confirmed_attended_weight_is_1_0(self):
        assert get_completion_weight("confirmed_attended") == 1.0

    def test_likely_attended_weight_is_0_7(self):
        assert get_completion_weight("likely_attended") == 0.7

    def test_confirmed_skipped_weight_is_negative_0_3(self):
        assert get_completion_weight("confirmed_skipped") == -0.3

    def test_pivot_replaced_weight_is_zero(self):
        assert get_completion_weight("pivot_replaced") == 0.0

    def test_no_show_ambiguous_weight_is_zero(self):
        assert get_completion_weight("no_show_ambiguous") == 0.0


# ===================================================================
# 5. COMPLETION_WEIGHTS dict integrity
# ===================================================================

class TestCompletionWeightsDict:
    """Validates the COMPLETION_WEIGHTS constant."""

    _ALL_STATES: list[str] = [
        "confirmed_attended",
        "likely_attended",
        "confirmed_skipped",
        "pivot_replaced",
        "no_show_ambiguous",
    ]

    def test_all_states_present(self):
        """Every SlotCompletionSignal state must have a weight entry."""
        for state in self._ALL_STATES:
            assert state in COMPLETION_WEIGHTS, f"Missing weight for state '{state}'"

    def test_all_weights_within_db_constraint(self):
        """All weights must be within the DB CHECK constraint [-1.0, 3.0]."""
        for state, weight in COMPLETION_WEIGHTS.items():
            assert -1.0 <= weight <= 3.0, (
                f"Weight {weight} for '{state}' violates CHECK [-1.0, 3.0]"
            )

    def test_no_extra_states(self):
        """COMPLETION_WEIGHTS should not contain unknown state keys."""
        extra = set(COMPLETION_WEIGHTS.keys()) - set(self._ALL_STATES)
        assert not extra, f"Unexpected states in COMPLETION_WEIGHTS: {extra}"
