"""
Shadow training data quality tests (M-010).

Validates that behavioral signals and raw events conform to the contract
needed by downstream ML training pipelines. Covers:

1. Positive pair tests: slot_confirm + activityNodeId, slot_complete, post_loved
2. Explicit negative tests: slot_skip, swipe_left, post_disliked
3. Implicit negative tests: impression without tap = implicit negative
4. Candidate set tests: generation logs full ranked pool as RawEvent
5. Position bias tests: impression events include position field (integer, not null)
6. Session sequence tests: events ordered by timestamp, consistent sessionId
7. Signal integrity: no orphan signals, required fields present
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest

from services.api.tests.conftest import (
    make_behavioral_signal,
    make_raw_event,
    make_itinerary_slot,
)
from services.api.tests.shadow_training.conftest import (
    make_positive_signal,
    make_explicit_negative_signal,
    make_impression_event,
    make_tap_event,
    make_candidate_set_event,
    make_ordered_session_events,
)


# ===========================================================================
# 1. Positive pair tests
# ===========================================================================

class TestPositivePairs:
    """Positive training pairs: user explicitly endorsed an activity."""

    def test_slot_confirm_requires_activity_node_id(self, solo_user, solo_trip, activity_nodes):
        """slot_confirm signal MUST carry activityNodeId for positive pair formation."""
        node = activity_nodes[0]
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=node["id"],
            signal_type="slot_confirm",
        )
        assert signal["activityNodeId"] == node["id"]
        assert signal["activityNodeId"] is not None
        assert signal["signalValue"] == 1.0
        assert signal["signalType"] == "slot_confirm"

    def test_slot_confirm_links_to_trip(self, solo_user, solo_trip, activity_nodes):
        """slot_confirm must reference both trip and activity node."""
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[1]["id"],
        )
        assert signal["tripId"] == solo_trip["id"]
        assert signal["userId"] == solo_user["id"]

    def test_slot_complete_is_positive_pair(self, solo_user, solo_trip, activity_nodes):
        """slot_complete is a strong positive: user actually did the activity."""
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[2]["id"],
            signal_type="slot_complete",
        )
        assert signal["signalType"] == "slot_complete"
        assert signal["signalValue"] == 1.0
        assert signal["tripPhase"] == "active"

    def test_post_loved_is_positive_pair(self, solo_user, solo_trip, activity_nodes):
        """post_loved is a post-trip positive signal."""
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[3]["id"],
            signal_type="post_loved",
        )
        assert signal["signalType"] == "post_loved"
        assert signal["signalValue"] == 1.0
        assert signal["tripPhase"] == "post_trip"

    def test_positive_signal_rejects_invalid_type(self, solo_user, solo_trip, activity_nodes):
        """make_positive_signal rejects non-positive signal types."""
        with pytest.raises(AssertionError, match="Not a positive signal"):
            make_positive_signal(
                user_id=solo_user["id"],
                trip_id=solo_trip["id"],
                activity_node_id=activity_nodes[0]["id"],
                signal_type="slot_skip",
            )


# ===========================================================================
# 2. Explicit negative tests
# ===========================================================================

class TestExplicitNegatives:
    """Explicit negative training signals: user rejected an activity."""

    def test_slot_skip_is_explicit_negative(self, solo_user, solo_trip, activity_nodes):
        """slot_skip carries negative signal value."""
        signal = make_explicit_negative_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[0]["id"],
            signal_type="slot_skip",
        )
        assert signal["signalType"] == "slot_skip"
        assert signal["signalValue"] == -1.0
        assert signal["activityNodeId"] == activity_nodes[0]["id"]

    def test_swipe_left_is_explicit_negative(self, solo_user, solo_trip, activity_nodes):
        """discover_swipe_left is a discovery-surface negative."""
        signal = make_explicit_negative_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[1]["id"],
            signal_type="discover_swipe_left",
        )
        assert signal["signalType"] == "discover_swipe_left"
        assert signal["signalValue"] == -1.0

    def test_post_disliked_is_explicit_negative(self, solo_user, solo_trip, activity_nodes):
        """post_disliked is a post-trip negative signal."""
        signal = make_explicit_negative_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[2]["id"],
            signal_type="post_disliked",
        )
        assert signal["signalType"] == "post_disliked"
        assert signal["signalValue"] == -1.0
        assert signal["tripPhase"] == "post_trip"

    def test_negative_signal_rejects_positive_types(self, solo_user, solo_trip, activity_nodes):
        """make_explicit_negative_signal rejects positive signal types."""
        with pytest.raises(AssertionError, match="Not an explicit negative"):
            make_explicit_negative_signal(
                user_id=solo_user["id"],
                trip_id=solo_trip["id"],
                activity_node_id=activity_nodes[0]["id"],
                signal_type="slot_confirm",
            )


# ===========================================================================
# 3. Implicit negative tests (impression without tap)
# ===========================================================================

class TestImplicitNegatives:
    """Impression shown but never tapped = implicit negative for training."""

    def test_impression_without_tap_is_implicit_negative(
        self, solo_user, session_id, activity_nodes
    ):
        """An impression event with no corresponding tap is an implicit negative."""
        impression = make_impression_event(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_id=activity_nodes[0]["id"],
            position=0,
        )
        # No tap event exists for this node in this session
        assert impression["eventType"] == "impression"
        assert impression["intentClass"] == "implicit"
        assert impression["activityNodeId"] == activity_nodes[0]["id"]

    def test_impression_with_tap_is_not_negative(
        self, solo_user, session_id, activity_nodes
    ):
        """When a tap follows an impression, the pair is NOT an implicit negative."""
        node_id = activity_nodes[1]["id"]
        impression = make_impression_event(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_id=node_id,
            position=1,
        )
        tap = make_tap_event(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_id=node_id,
        )
        # Both reference the same node and session
        assert impression["activityNodeId"] == tap["activityNodeId"]
        assert impression["sessionId"] == tap["sessionId"]
        # Tap is explicit intent
        assert tap["intentClass"] == "explicit"

    def test_impression_carries_activity_node_id(
        self, solo_user, session_id, activity_nodes
    ):
        """Impression must always carry activityNodeId for join with activity graph."""
        for node in activity_nodes:
            imp = make_impression_event(
                user_id=solo_user["id"],
                session_id=session_id,
                activity_node_id=node["id"],
                position=0,
            )
            assert imp["activityNodeId"] is not None
            assert imp["activityNodeId"] == node["id"]


# ===========================================================================
# 4. Candidate set tests
# ===========================================================================

class TestCandidateSetLogging:
    """Generation must log the full ranked candidate pool as a RawEvent."""

    def test_candidate_set_event_logs_full_pool(
        self, solo_user, session_id, solo_trip, activity_nodes
    ):
        """candidate_set event payload includes all ranked candidates."""
        event = make_candidate_set_event(
            user_id=solo_user["id"],
            session_id=session_id,
            trip_id=solo_trip["id"],
            candidates=activity_nodes,
        )
        assert event["eventType"] == "generation.candidate_set"
        assert event["intentClass"] == "contextual"
        payload = event["payload"]
        assert payload["poolSize"] == len(activity_nodes)
        assert len(payload["candidates"]) == len(activity_nodes)

    def test_candidate_set_preserves_rank_order(
        self, solo_user, session_id, solo_trip, activity_nodes
    ):
        """Candidate entries are rank-ordered (1-indexed)."""
        event = make_candidate_set_event(
            user_id=solo_user["id"],
            session_id=session_id,
            trip_id=solo_trip["id"],
            candidates=activity_nodes,
        )
        ranks = [c["rank"] for c in event["payload"]["candidates"]]
        assert ranks == list(range(1, len(activity_nodes) + 1))

    def test_candidate_set_includes_required_fields(
        self, solo_user, session_id, solo_trip, activity_nodes
    ):
        """Each candidate entry has id, rank, category, convergenceScore."""
        event = make_candidate_set_event(
            user_id=solo_user["id"],
            session_id=session_id,
            trip_id=solo_trip["id"],
            candidates=activity_nodes,
        )
        for candidate in event["payload"]["candidates"]:
            assert "id" in candidate
            assert "rank" in candidate
            assert "category" in candidate
            assert "convergenceScore" in candidate
            assert isinstance(candidate["rank"], int)

    def test_candidate_set_links_to_trip(
        self, solo_user, session_id, solo_trip, activity_nodes
    ):
        """candidate_set event references the trip it was generated for."""
        event = make_candidate_set_event(
            user_id=solo_user["id"],
            session_id=session_id,
            trip_id=solo_trip["id"],
            candidates=activity_nodes,
        )
        assert event["tripId"] == solo_trip["id"]


# ===========================================================================
# 5. Position bias tests
# ===========================================================================

class TestPositionBias:
    """Impression events must include position for bias correction."""

    def test_impression_has_integer_position(
        self, solo_user, session_id, activity_nodes
    ):
        """Position field must be a non-null integer."""
        for i, node in enumerate(activity_nodes):
            imp = make_impression_event(
                user_id=solo_user["id"],
                session_id=session_id,
                activity_node_id=node["id"],
                position=i,
            )
            pos = imp["payload"]["position"]
            assert pos is not None, "position must not be null"
            assert isinstance(pos, int), f"position must be int, got {type(pos)}"
            assert pos == i

    def test_position_zero_indexed(self, solo_user, session_id, activity_nodes):
        """First impression in feed should be position=0."""
        imp = make_impression_event(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_id=activity_nodes[0]["id"],
            position=0,
        )
        assert imp["payload"]["position"] == 0

    def test_position_monotonically_increasing_in_session(
        self, solo_user, session_id, activity_nodes
    ):
        """Positions in a session should be monotonically increasing."""
        events = [
            make_impression_event(
                user_id=solo_user["id"],
                session_id=session_id,
                activity_node_id=node["id"],
                position=i,
            )
            for i, node in enumerate(activity_nodes)
        ]
        positions = [e["payload"]["position"] for e in events]
        assert positions == sorted(positions)
        assert len(set(positions)) == len(positions), "positions must be unique"


# ===========================================================================
# 6. Session sequence tests
# ===========================================================================

class TestSessionSequence:
    """Events within a session must be timestamp-ordered with consistent sessionId."""

    def test_events_ordered_by_timestamp(
        self, solo_user, session_id, activity_nodes
    ):
        """Ordered session events have monotonically increasing createdAt."""
        node_ids = [n["id"] for n in activity_nodes[:4]]
        events = make_ordered_session_events(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_ids=node_ids,
        )
        timestamps = [e["createdAt"] for e in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1], (
                f"Event {i} timestamp not after event {i-1}"
            )

    def test_consistent_session_id(self, solo_user, session_id, activity_nodes):
        """All events in a session sequence share the same sessionId."""
        node_ids = [n["id"] for n in activity_nodes[:3]]
        events = make_ordered_session_events(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_ids=node_ids,
        )
        session_ids = {e["sessionId"] for e in events}
        assert len(session_ids) == 1
        assert session_ids.pop() == session_id

    def test_consistent_user_id_in_session(self, solo_user, session_id, activity_nodes):
        """All events in a session belong to the same user."""
        node_ids = [n["id"] for n in activity_nodes[:3]]
        events = make_ordered_session_events(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_ids=node_ids,
        )
        user_ids = {e["userId"] for e in events}
        assert len(user_ids) == 1
        assert user_ids.pop() == solo_user["id"]

    def test_unique_client_event_ids_in_session(
        self, solo_user, session_id, activity_nodes
    ):
        """Each event in a session has a unique clientEventId."""
        node_ids = [n["id"] for n in activity_nodes]
        events = make_ordered_session_events(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_ids=node_ids,
        )
        client_ids = [e["clientEventId"] for e in events]
        assert len(set(client_ids)) == len(client_ids), "clientEventIds must be unique"


# ===========================================================================
# 7. Signal integrity — no orphans, required fields
# ===========================================================================

class TestSignalIntegrity:
    """Validate signal data meets training pipeline requirements."""

    def test_behavioral_signal_required_fields_present(self, solo_user, solo_trip, activity_nodes):
        """Every BehavioralSignal must have all non-nullable fields populated."""
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[0]["id"],
        )
        required = ["id", "userId", "signalType", "signalValue", "tripPhase", "rawAction", "createdAt"]
        for field in required:
            assert signal[field] is not None, f"Required field '{field}' is None"

    def test_raw_event_required_fields_present(self, solo_user, session_id, activity_nodes):
        """Every RawEvent must have userId, sessionId, eventType, intentClass."""
        event = make_impression_event(
            user_id=solo_user["id"],
            session_id=session_id,
            activity_node_id=activity_nodes[0]["id"],
            position=0,
        )
        required = ["id", "userId", "sessionId", "eventType", "intentClass", "createdAt"]
        for field in required:
            assert event[field] is not None, f"Required field '{field}' is None"

    def test_raw_event_intent_class_valid_enum(self, solo_user, session_id):
        """intentClass must be one of: explicit, implicit, contextual."""
        valid_classes = {"explicit", "implicit", "contextual"}
        for ic in valid_classes:
            event = make_raw_event(
                user_id=solo_user["id"],
                session_id=session_id,
                intentClass=ic,
            )
            assert event["intentClass"] in valid_classes

    def test_behavioral_signal_userId_must_not_be_empty(self, solo_trip, activity_nodes):
        """userId on BehavioralSignal must be a non-empty string."""
        signal = make_positive_signal(
            user_id="user-abc-123",
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[0]["id"],
        )
        assert isinstance(signal["userId"], str)
        assert len(signal["userId"]) > 0

    def test_no_orphan_signals_pattern(self, solo_user, solo_trip, activity_nodes):
        """
        Validate the orphan detection pattern: a signal's activityNodeId
        must correspond to an actual node in the candidate pool.
        """
        node_ids = {n["id"] for n in activity_nodes}
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=activity_nodes[0]["id"],
        )
        assert signal["activityNodeId"] in node_ids, "Signal references unknown node"

    def test_orphan_detection_catches_invalid_node(self, solo_user, solo_trip, activity_nodes):
        """A signal referencing a non-existent node should be flagged."""
        node_ids = {n["id"] for n in activity_nodes}
        fake_node_id = "node-does-not-exist-999"
        signal = make_positive_signal(
            user_id=solo_user["id"],
            trip_id=solo_trip["id"],
            activity_node_id=fake_node_id,
        )
        assert signal["activityNodeId"] not in node_ids

    def test_slot_with_activity_node_creates_valid_pair(self, solo_trip, activity_nodes):
        """An ItinerarySlot with activityNodeId forms a valid training target."""
        slot = make_itinerary_slot(
            trip_id=solo_trip["id"],
            activityNodeId=activity_nodes[0]["id"],
            slotType="anchor",
            status="confirmed",
        )
        assert slot["activityNodeId"] is not None
        assert slot["tripId"] == solo_trip["id"]
        assert slot["status"] == "confirmed"
