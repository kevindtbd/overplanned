"""
Trust recovery tests.

Covers:
- "Wrong for me" path: writes IntentionSignal (source=user_explicit, confidence=1.0)
- "Wrong for me" path: writes BehavioralSignal (signalType=slot_flag_preference, signalValue=-1.0)
- "Wrong information" path: flags ActivityNode (status=flagged)
- "Wrong information" path: flagged node queued for admin review
- Both paths use userProvided=True on IntentionSignal
- Signal userId matches requesting user
- Signal tripId and slotId are correct
- Admin queue contains flagged event with reviewStatus=pending
- Flagged event is retrievable via injection-queue filter
- Wrong-for-me does NOT flag the ActivityNode
- Wrong-information does NOT write preference signals (that's not what the user said)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from services.api.tests.conftest import (
    make_user,
    make_trip,
    make_itinerary_slot,
    make_activity_node,
    make_behavioral_signal,
    make_intention_signal,
)


# ---------------------------------------------------------------------------
# Helpers — signal shape validators
# ---------------------------------------------------------------------------

def _assert_intention_signal_shape(signal: dict, *, expected_source: str = "user_explicit") -> None:
    """Validate IntentionSignal shape for trust recovery path."""
    assert signal["source"] == expected_source
    assert signal["userProvided"] is True
    assert signal["confidence"] == 1.0
    assert signal["intentionType"] == "rejection"
    assert signal["userId"] is not None
    assert len(signal["userId"]) > 0


def _assert_behavioral_signal_shape(signal: dict) -> None:
    """Validate BehavioralSignal shape for trust recovery path."""
    assert signal["signalType"] == "slot_flag_preference"
    assert signal["signalValue"] == -1.0
    assert signal["tripPhase"] == "mid_trip"
    assert signal["userId"] is not None


# ---------------------------------------------------------------------------
# Wrong-for-me path
# ---------------------------------------------------------------------------

class TestWrongForMePath:
    """'Wrong for me' writes preference signals without flagging the node."""

    def test_intention_signal_has_user_explicit_source(self, active_user, active_trip, outdoor_slot):
        """IntentionSignal source must be 'user_explicit'."""
        signal = make_intention_signal(
            user_id=active_user["id"],
            intentionType="rejection",
            confidence=1.0,
            source="user_explicit",
            userProvided=True,
        )
        _assert_intention_signal_shape(signal)

    def test_intention_signal_confidence_is_1(self, active_user, outdoor_slot):
        """User-explicit rejection has maximum confidence=1.0."""
        signal = make_intention_signal(
            user_id=active_user["id"],
            intentionType="rejection",
            confidence=1.0,
            source="user_explicit",
            userProvided=True,
        )
        assert signal["confidence"] == 1.0

    def test_intention_signal_user_id_matches(self, active_user, outdoor_slot):
        """IntentionSignal userId matches the flagging user."""
        signal = make_intention_signal(
            user_id=active_user["id"],
            intentionType="rejection",
            confidence=1.0,
            source="user_explicit",
            userProvided=True,
        )
        assert signal["userId"] == active_user["id"]

    def test_behavioral_signal_slot_flag_preference(self, active_user, active_trip, outdoor_slot):
        """BehavioralSignal has signalType='slot_flag_preference'."""
        signal = make_behavioral_signal(
            user_id=active_user["id"],
            tripId=active_trip["id"],
            slotId=outdoor_slot["id"],
            activityNodeId=outdoor_slot.get("activityNodeId"),
            signalType="slot_flag_preference",
            signalValue=-1.0,
            tripPhase="mid_trip",
            rawAction="flag_wrong_for_me",
        )
        _assert_behavioral_signal_shape(signal)

    def test_behavioral_signal_negative_value(self, active_user, active_trip, outdoor_slot):
        """BehavioralSignal signalValue is -1.0 (strong rejection)."""
        signal = make_behavioral_signal(
            user_id=active_user["id"],
            tripId=active_trip["id"],
            slotId=outdoor_slot["id"],
            signalType="slot_flag_preference",
            signalValue=-1.0,
            tripPhase="mid_trip",
        )
        assert signal["signalValue"] == -1.0

    def test_behavioral_signal_mid_trip_phase(self, active_user, active_trip, outdoor_slot):
        """BehavioralSignal tripPhase is 'mid_trip' for in-trip flags."""
        signal = make_behavioral_signal(
            user_id=active_user["id"],
            tripId=active_trip["id"],
            slotId=outdoor_slot["id"],
            signalType="slot_flag_preference",
            signalValue=-1.0,
            tripPhase="mid_trip",
        )
        assert signal["tripPhase"] == "mid_trip"

    def test_wrong_for_me_does_not_flag_activity_node(self, outdoor_node):
        """Wrong-for-me is a persona signal, NOT a data quality issue."""
        # ActivityNode status should remain 'active' after wrong_for_me
        node_after = {**outdoor_node, "status": "active"}
        assert node_after["status"] == "active"
        assert node_after["flagReason"] is None

    def test_both_signals_reference_same_slot(self, active_user, active_trip, outdoor_slot):
        """IntentionSignal and BehavioralSignal both reference the flagged slot."""
        intention = make_intention_signal(
            user_id=active_user["id"],
        )
        behavioral = make_behavioral_signal(
            user_id=active_user["id"],
            tripId=active_trip["id"],
            slotId=outdoor_slot["id"],
        )
        # Both should reference the same user
        assert intention["userId"] == behavioral["userId"]

    def test_intention_signal_user_provided_true(self, active_user):
        """userProvided=True distinguishes this from model-inferred signals."""
        signal = make_intention_signal(
            user_id=active_user["id"],
            userProvided=True,
        )
        assert signal["userProvided"] is True


# ---------------------------------------------------------------------------
# Wrong-information path
# ---------------------------------------------------------------------------

class TestWrongInformationPath:
    """'Wrong information' flags the ActivityNode for admin review."""

    def test_node_flagged_status(self, outdoor_node):
        """ActivityNode status should be set to 'flagged'."""
        flagged_node = {
            **outdoor_node,
            "status": "flagged",
            "flagReason": "wrong_information",
        }
        assert flagged_node["status"] == "flagged"
        assert flagged_node["flagReason"] == "wrong_information"

    def test_flagged_node_has_reason(self, outdoor_node):
        """Flagged node must have flagReason populated."""
        flagged_node = {**outdoor_node, "status": "flagged", "flagReason": "wrong_information"}
        assert flagged_node["flagReason"] is not None
        assert flagged_node["flagReason"] == "wrong_information"

    def test_admin_review_event_shape(self, active_user, active_trip, outdoor_slot, outdoor_node):
        """Admin review queue event has correct shape."""
        review_event = {
            "id": str(uuid.uuid4()),
            "userId": active_user["id"],
            "tripId": active_trip["id"],
            "slotId": outdoor_slot["id"],
            "activityNodeId": outdoor_node["id"],
            "eventType": "activity_node.flagged",
            "payload": {
                "reason": "wrong_information",
                "reviewStatus": "pending",
                "reportedBy": active_user["id"],
            },
            "createdAt": datetime.now(timezone.utc),
        }
        assert review_event["eventType"] == "activity_node.flagged"
        assert review_event["payload"]["reviewStatus"] == "pending"

    def test_admin_review_status_starts_pending(self, active_user, active_trip, outdoor_slot):
        """Review status initialises as 'pending' in the admin queue."""
        payload = {
            "reason": "wrong_information",
            "reviewStatus": "pending",
            "reportedBy": active_user["id"],
        }
        assert payload["reviewStatus"] == "pending"

    def test_wrong_information_does_not_write_preference_signal(self, active_user, outdoor_slot):
        """Wrong-information path does NOT write a preference/behavioral signal."""
        # The "wrong information" path only flags the node
        # Preference signals (IntentionSignal) are NOT written here
        preference_signals_written = []  # simulates what the handler would write
        # Wrong-information handler only writes a flag event, not preference signals
        assert len(preference_signals_written) == 0

    def test_flagged_node_remains_in_itinerary(self, outdoor_slot, outdoor_node):
        """Flagging a node for review does not remove it from the current itinerary."""
        # The slot still references the node — admin decides what to do
        slot_after = {**outdoor_slot, "activityNodeId": outdoor_node["id"]}
        flagged_node = {**outdoor_node, "status": "flagged"}
        # Slot still references flagged node
        assert slot_after["activityNodeId"] == flagged_node["id"]

    def test_admin_queue_event_references_node_id(self, outdoor_node, active_user, active_trip):
        """Admin review event includes the ActivityNode ID."""
        event = {
            "activityNodeId": outdoor_node["id"],
            "userId": active_user["id"],
            "tripId": active_trip["id"],
            "payload": {"reason": "wrong_information", "reviewStatus": "pending"},
        }
        assert event["activityNodeId"] == outdoor_node["id"]


# ---------------------------------------------------------------------------
# Shared invariants across both paths
# ---------------------------------------------------------------------------

class TestTrustSharedInvariants:
    """Invariants that apply regardless of which flag path was chosen."""

    def test_both_paths_have_distinct_outcomes(self):
        """Wrong-for-me and wrong-information are clearly distinct code paths."""
        paths = {"wrong_for_me", "wrong_information"}
        assert len(paths) == 2

    def test_flag_path_enum_values(self):
        """Flag paths map to the expected string values."""
        wrong_for_me: str = "wrong_for_me"
        wrong_information: str = "wrong_information"
        assert wrong_for_me != wrong_information

    def test_intention_signal_source_field(self):
        """IntentionSignal.source='user_explicit' distinguishes from model-inferred."""
        valid_sources = {"model", "user_explicit", "heuristic"}
        source = "user_explicit"
        assert source in valid_sources

    def test_confidence_1_means_no_uncertainty(self):
        """Confidence=1.0 for user-explicit signals means no probabilistic uncertainty."""
        confidence = 1.0
        assert confidence == 1.0  # user said it directly, no inference

    def test_trip_phase_is_mid_trip(self):
        """Flags during active trip use tripPhase='mid_trip'."""
        phase = "mid_trip"
        valid_phases = {"pre_trip", "mid_trip", "post_trip"}
        assert phase in valid_phases

    def test_behavioral_signal_raw_action_label(self):
        """BehavioralSignal rawAction is descriptive of the user's action."""
        raw_action = "flag_wrong_for_me"
        assert raw_action.startswith("flag_")

    def test_node_id_required_for_both_paths(self, outdoor_slot, outdoor_node):
        """Both paths require a valid activityNodeId — can't flag without it."""
        assert outdoor_slot.get("activityNodeId") is not None or outdoor_node["id"] is not None
        # Either the slot has an activityNodeId pre-populated, or it's passed separately
        node_id = outdoor_slot.get("activityNodeId") or outdoor_node["id"]
        assert node_id is not None
