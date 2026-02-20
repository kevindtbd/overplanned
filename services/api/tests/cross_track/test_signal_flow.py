"""
Cross-track signal flow tests: Solo (Track 3) -> Post-Trip (Track 7).

Validates that signals written during solo trip generation and active phase
are readable and correctly structured for post-trip disambiguation rules.

These tests are purely in-memory (no DB). They exercise data shape contracts
between tracks -- the seam where one track's writes become another track's reads.
"""

from __future__ import annotations

from datetime import datetime, timezone


# ============================================================================
# 1. BehavioralSignals from solo generation are readable by disambiguation
# ============================================================================

class TestSoloSignalsReadableByDisambiguation:
    """Signals written by Track 3 (solo generation) must be queryable by
    the post-trip disambiguation rules in Track 7."""

    def test_all_generation_signals_have_required_fields(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Every BehavioralSignal has the fields that disambiguation queries need."""
        required_keys = {
            "id", "userId", "tripId", "slotId", "signalType",
            "signalValue", "tripPhase", "rawAction", "createdAt",
        }
        for signal in cross_solo_behavioral_signals:
            missing = required_keys - set(signal.keys())
            assert not missing, (
                f"Signal {signal['id']} missing keys for disambiguation: {missing}"
            )

    def test_generation_signals_link_to_trip_and_user(
        self,
        cross_user: dict,
        cross_solo_trip: dict,
        cross_solo_behavioral_signals: list[dict],
    ):
        """All signals reference the correct userId and tripId so Track 7
        can filter by trip when building the reflection context."""
        user_id = cross_user["id"]
        trip_id = cross_solo_trip["id"]
        for signal in cross_solo_behavioral_signals:
            assert signal["userId"] == user_id, (
                f"Signal {signal['id']} has wrong userId"
            )
            assert signal["tripId"] == trip_id, (
                f"Signal {signal['id']} has wrong tripId"
            )

    def test_post_trip_signals_include_loved_and_skipped(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Disambiguation needs post_loved and post_skipped signals to exist."""
        signal_types = {s["signalType"] for s in cross_solo_behavioral_signals}
        assert "post_loved" in signal_types, (
            "Missing post_loved signal -- disambiguation cannot identify highlights"
        )
        assert "post_skipped" in signal_types, (
            "Missing post_skipped signal -- disambiguation cannot identify skips"
        )


# ============================================================================
# 2. Slot impression signal schema correctness
# ============================================================================

class TestSlotImpressionSchema:
    """Slot impression signals must have the exact schema that the
    disambiguation batch job expects."""

    def test_impression_signals_have_slot_id(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Each slot_view impression must carry a slotId for join queries."""
        impressions = [
            s for s in cross_solo_behavioral_signals
            if s["signalType"] == "slot_view"
        ]
        assert len(impressions) > 0, "No slot_view impressions found"
        for sig in impressions:
            assert sig["slotId"] is not None, (
                f"Impression {sig['id']} has null slotId"
            )

    def test_impression_signal_value_is_positive(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Impressions represent exposure, so signalValue must be positive."""
        impressions = [
            s for s in cross_solo_behavioral_signals
            if s["signalType"] == "slot_view"
        ]
        for sig in impressions:
            assert sig["signalValue"] > 0, (
                f"Impression {sig['id']} has non-positive signalValue={sig['signalValue']}"
            )

    def test_impression_carries_trip_phase(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Each impression must declare its tripPhase so disambiguation knows
        which phase produced it."""
        impressions = [
            s for s in cross_solo_behavioral_signals
            if s["signalType"] == "slot_view"
        ]
        valid_phases = {"pre_trip", "active", "post_trip"}
        for sig in impressions:
            assert sig["tripPhase"] in valid_phases, (
                f"Impression {sig['id']} has invalid tripPhase={sig['tripPhase']}"
            )

    def test_impression_has_user_and_trip_ids(
        self,
        cross_user: dict,
        cross_solo_trip: dict,
        cross_solo_behavioral_signals: list[dict],
    ):
        """userId and tripId must be set for the disambiguation batch join."""
        impressions = [
            s for s in cross_solo_behavioral_signals
            if s["signalType"] == "slot_view"
        ]
        for sig in impressions:
            assert sig["userId"] == cross_user["id"]
            assert sig["tripId"] == cross_solo_trip["id"]

    def test_impression_has_activity_node_id(
        self,
        cross_activity_nodes: list[dict],
        cross_solo_behavioral_signals: list[dict],
    ):
        """activityNodeId links impressions to world knowledge for vibe matching."""
        node_ids = {n["id"] for n in cross_activity_nodes}
        impressions = [
            s for s in cross_solo_behavioral_signals
            if s["signalType"] == "slot_view"
        ]
        for sig in impressions:
            assert sig["activityNodeId"] in node_ids, (
                f"Impression {sig['id']} activityNodeId not in known nodes"
            )


# ============================================================================
# 3. IntentionSignals from skip reasons findable by disambiguation query
# ============================================================================

class TestSkipIntentionSignals:
    """IntentionSignals with source=user_explicit must be findable by
    the disambiguation batch job's typical query pattern:
    WHERE userId=X AND source='user_explicit' AND intentionType IN (...)."""

    def test_skip_intention_exists(self, cross_intention_signals: list[dict]):
        """At least one intention signal with type 'not_interested' exists."""
        skip_intentions = [
            s for s in cross_intention_signals
            if s["intentionType"] == "not_interested"
        ]
        assert len(skip_intentions) >= 1, (
            "No not_interested IntentionSignal found for disambiguation"
        )

    def test_skip_intention_is_user_explicit(
        self, cross_intention_signals: list[dict]
    ):
        """Skip intentions must have source=user_explicit so disambiguation
        trusts them as high-confidence signals."""
        skip_intentions = [
            s for s in cross_intention_signals
            if s["intentionType"] == "not_interested"
        ]
        for sig in skip_intentions:
            assert sig["source"] == "user_explicit", (
                f"IntentionSignal {sig['id']} has source={sig['source']}, "
                "expected user_explicit"
            )

    def test_skip_intention_links_to_behavioral_signal(
        self,
        cross_intention_signals: list[dict],
        cross_solo_behavioral_signals: list[dict],
    ):
        """Every IntentionSignal.behavioralSignalId must reference an existing
        BehavioralSignal so the disambiguation job can trace the chain."""
        bs_ids = {s["id"] for s in cross_solo_behavioral_signals}
        for intention in cross_intention_signals:
            assert intention["behavioralSignalId"] in bs_ids, (
                f"IntentionSignal {intention['id']} references "
                f"behavioralSignalId={intention['behavioralSignalId']} "
                "which is not in the behavioral signals set"
            )

    def test_preference_intention_also_present(
        self, cross_intention_signals: list[dict]
    ):
        """A 'preference' intention (from post_loved) should also exist for
        disambiguation to weight positive signals."""
        prefs = [
            s for s in cross_intention_signals
            if s["intentionType"] == "preference"
        ]
        assert len(prefs) >= 1, (
            "No preference IntentionSignal found -- disambiguation cannot "
            "weight positive signals"
        )

    def test_intention_confidence_in_valid_range(
        self, cross_intention_signals: list[dict]
    ):
        """Confidence must be in [0.0, 1.0] for disambiguation scoring."""
        for sig in cross_intention_signals:
            assert 0.0 <= sig["confidence"] <= 1.0, (
                f"IntentionSignal {sig['id']} confidence={sig['confidence']} "
                "out of [0, 1] range"
            )


# ============================================================================
# 4. Signal tripPhase transitions: pre_trip -> active -> post_trip
# ============================================================================

class TestTripPhaseTransitions:
    """The full lifecycle of trip phases must be represented in signals so
    disambiguation can differentiate planning-time vs runtime vs reflection."""

    def test_all_three_phases_present(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Signals must span all three phases: pre_trip, active, post_trip."""
        phases = {s["tripPhase"] for s in cross_solo_behavioral_signals}
        assert "pre_trip" in phases, "Missing pre_trip phase signals"
        assert "active" in phases, "Missing active phase signals"
        assert "post_trip" in phases, "Missing post_trip phase signals"

    def test_pre_trip_signals_are_earliest(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """pre_trip signals must have earlier createdAt than active signals."""
        pre_trip = [
            s for s in cross_solo_behavioral_signals
            if s["tripPhase"] == "pre_trip"
        ]
        active = [
            s for s in cross_solo_behavioral_signals
            if s["tripPhase"] == "active"
        ]
        if pre_trip and active:
            latest_pre = max(s["createdAt"] for s in pre_trip)
            earliest_active = min(s["createdAt"] for s in active)
            assert latest_pre <= earliest_active, (
                f"pre_trip signal at {latest_pre} is after "
                f"active signal at {earliest_active}"
            )

    def test_active_signals_before_post_trip(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """active signals must have earlier createdAt than post_trip signals."""
        active = [
            s for s in cross_solo_behavioral_signals
            if s["tripPhase"] == "active"
        ]
        post_trip = [
            s for s in cross_solo_behavioral_signals
            if s["tripPhase"] == "post_trip"
        ]
        if active and post_trip:
            latest_active = max(s["createdAt"] for s in active)
            earliest_post = min(s["createdAt"] for s in post_trip)
            assert latest_active <= earliest_post, (
                f"active signal at {latest_active} is after "
                f"post_trip signal at {earliest_post}"
            )

    def test_phase_signal_type_mapping(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Certain signal types belong to specific phases:
        - slot_view in pre_trip (generation impressions)
        - slot_confirm in active
        - post_loved / post_skipped in post_trip
        """
        phase_expectations = {
            "pre_trip": {"slot_view"},
            "active": {"slot_confirm"},
            "post_trip": {"post_loved", "post_skipped"},
        }
        for phase, expected_types in phase_expectations.items():
            phase_signals = [
                s for s in cross_solo_behavioral_signals
                if s["tripPhase"] == phase
            ]
            actual_types = {s["signalType"] for s in phase_signals}
            assert expected_types.issubset(actual_types), (
                f"Phase {phase} missing signal types: "
                f"{expected_types - actual_types}"
            )


# ============================================================================
# 5. RawEvents from generation flow through to post-trip reflection
# ============================================================================

class TestRawEventFlowToPostTrip:
    """RawEvents created during generation (itinerary_generated, slot_view)
    must be present and structured for post-trip reflection queries."""

    def test_itinerary_generated_event_exists(
        self, cross_raw_events: list[dict]
    ):
        """The itinerary_generated event must exist for post-trip to know
        when the itinerary was created."""
        gen_events = [
            e for e in cross_raw_events
            if e["eventType"] == "itinerary_generated"
        ]
        assert len(gen_events) == 1, (
            f"Expected exactly 1 itinerary_generated event, got {len(gen_events)}"
        )

    def test_itinerary_generated_has_slot_count(
        self, cross_raw_events: list[dict], cross_solo_slots: list[dict]
    ):
        """The itinerary_generated payload must include slotCount matching
        actual slots, so post-trip can validate completeness."""
        gen_event = next(
            e for e in cross_raw_events
            if e["eventType"] == "itinerary_generated"
        )
        assert gen_event["payload"]["slotCount"] == len(cross_solo_slots), (
            f"itinerary_generated payload slotCount={gen_event['payload']['slotCount']} "
            f"but actual slots={len(cross_solo_slots)}"
        )

    def test_slot_view_events_per_slot(
        self, cross_raw_events: list[dict], cross_solo_slots: list[dict]
    ):
        """Each slot should have at least one slot_view RawEvent."""
        slot_view_events = [
            e for e in cross_raw_events
            if e["eventType"] == "slot_view"
        ]
        event_slot_ids = {
            e["payload"]["slotId"]
            for e in slot_view_events
            if "slotId" in e.get("payload", {})
        }
        actual_slot_ids = {s["id"] for s in cross_solo_slots}
        assert event_slot_ids == actual_slot_ids, (
            f"slot_view events cover slots {event_slot_ids} "
            f"but expected {actual_slot_ids}"
        )

    def test_raw_events_have_session_id(self, cross_raw_events: list[dict]):
        """All RawEvents must have a sessionId for session-level grouping
        in post-trip analytics."""
        for event in cross_raw_events:
            assert event["sessionId"] is not None, (
                f"RawEvent {event['id']} has null sessionId"
            )

    def test_raw_events_have_valid_intent_class(
        self, cross_raw_events: list[dict]
    ):
        """intentClass must be one of explicit/implicit/contextual."""
        valid = {"explicit", "implicit", "contextual"}
        for event in cross_raw_events:
            assert event["intentClass"] in valid, (
                f"RawEvent {event['id']} has invalid intentClass={event['intentClass']}"
            )

    def test_raw_events_reference_trip(
        self, cross_solo_trip: dict, cross_raw_events: list[dict]
    ):
        """All generation RawEvents must reference the trip for post-trip filtering."""
        trip_id = cross_solo_trip["id"]
        for event in cross_raw_events:
            assert event["tripId"] == trip_id, (
                f"RawEvent {event['id']} has tripId={event['tripId']}, "
                f"expected {trip_id}"
            )


# ============================================================================
# 6. Pivot signals visible in post-trip reflection context
# ============================================================================

class TestPivotSignalsInPostTrip:
    """PivotEvent and associated signals from mid-trip (Track 6) must be
    visible and correctly shaped for post-trip reflection (Track 7)."""

    def test_pivot_event_is_accepted(self, cross_pivot_event: dict):
        """The weather pivot was accepted -- post-trip should show this."""
        assert cross_pivot_event["status"] == "accepted"

    def test_pivot_event_has_response_time(self, cross_pivot_event: dict):
        """responseTimeMs is needed for UX metrics in post-trip dashboard."""
        assert cross_pivot_event["responseTimeMs"] is not None
        assert cross_pivot_event["responseTimeMs"] > 0

    def test_pivot_event_references_trip_and_slot(
        self,
        cross_solo_trip: dict,
        cross_solo_slots: list[dict],
        cross_pivot_event: dict,
    ):
        """Pivot must link to correct trip and slot for context lookup."""
        assert cross_pivot_event["tripId"] == cross_solo_trip["id"]
        slot_ids = {s["id"] for s in cross_solo_slots}
        assert cross_pivot_event["slotId"] in slot_ids

    def test_pivot_accepted_signal_exists(
        self, cross_pivot_behavioral_signals: list[dict]
    ):
        """A pivot_accepted BehavioralSignal must exist for post-trip
        to know the user engaged with the pivot."""
        accepted = [
            s for s in cross_pivot_behavioral_signals
            if s["signalType"] == "pivot_accepted"
        ]
        assert len(accepted) >= 1, "No pivot_accepted behavioral signal found"

    def test_pivot_signal_has_weather_context(
        self, cross_pivot_behavioral_signals: list[dict]
    ):
        """Pivot signals should carry weatherContext for post-trip
        to explain why the pivot happened."""
        accepted = [
            s for s in cross_pivot_behavioral_signals
            if s["signalType"] == "pivot_accepted"
        ]
        for sig in accepted:
            assert sig["weatherContext"] is not None, (
                f"Pivot signal {sig['id']} missing weatherContext"
            )

    def test_pivot_resolved_raw_event_exists(
        self, cross_raw_events: list[dict]
    ):
        """A pivot_resolved RawEvent must exist for the post-trip timeline."""
        resolved = [
            e for e in cross_raw_events
            if e["eventType"] == "pivot_resolved"
        ]
        assert len(resolved) >= 1, "No pivot_resolved RawEvent found"

    def test_pivot_resolved_payload_has_decision(
        self, cross_raw_events: list[dict]
    ):
        """The pivot_resolved payload must include the decision for
        post-trip reflection narrative."""
        resolved = next(
            e for e in cross_raw_events
            if e["eventType"] == "pivot_resolved"
        )
        assert "decision" in resolved["payload"], (
            "pivot_resolved payload missing 'decision' field"
        )
        assert resolved["payload"]["decision"] in {"accepted", "rejected"}, (
            f"Invalid pivot decision: {resolved['payload']['decision']}"
        )

    def test_pivot_trigger_type_recorded(self, cross_pivot_event: dict):
        """triggerType must be set so post-trip can categorize pivots
        (weather vs venue_closed vs user_request etc)."""
        valid_triggers = {
            "weather_change", "venue_closed", "time_overrun",
            "user_mood", "user_request",
        }
        assert cross_pivot_event["triggerType"] in valid_triggers


# ============================================================================
# 7. Signal count per slot meets minimum threshold
# ============================================================================

class TestSignalCountPerSlot:
    """Each slot should have at least 1 BehavioralSignal + 1 RawEvent
    so post-trip disambiguation has sufficient data to work with."""

    def test_each_slot_has_at_least_one_behavioral_signal(
        self,
        cross_solo_slots: list[dict],
        cross_solo_behavioral_signals: list[dict],
    ):
        """Every slot must have at least one BehavioralSignal."""
        for slot in cross_solo_slots:
            slot_signals = [
                s for s in cross_solo_behavioral_signals
                if s["slotId"] == slot["id"]
            ]
            assert len(slot_signals) >= 1, (
                f"Slot {slot['id']} (sortOrder={slot['sortOrder']}) "
                f"has {len(slot_signals)} behavioral signals, expected >= 1"
            )

    def test_each_slot_has_at_least_one_raw_event(
        self,
        cross_solo_slots: list[dict],
        cross_raw_events: list[dict],
    ):
        """Every slot must have at least one RawEvent (slot_view at minimum)."""
        for slot in cross_solo_slots:
            # RawEvents reference slots via payload.slotId
            slot_events = [
                e for e in cross_raw_events
                if e.get("payload", {}).get("slotId") == slot["id"]
            ]
            assert len(slot_events) >= 1, (
                f"Slot {slot['id']} (sortOrder={slot['sortOrder']}) "
                f"has {len(slot_events)} raw events, expected >= 1"
            )

    def test_total_behavioral_signal_count(
        self, cross_solo_behavioral_signals: list[dict]
    ):
        """Sanity check: total signal count matches expected.

        3 pre_trip impressions + 3 active confirms + 1 post_loved + 1 post_skipped = 8
        """
        assert len(cross_solo_behavioral_signals) == 8, (
            f"Expected 8 solo behavioral signals, got "
            f"{len(cross_solo_behavioral_signals)}"
        )

    def test_total_raw_event_count(self, cross_raw_events: list[dict]):
        """Sanity check: 3 slot_views + 1 itinerary_generated + 1 pivot_resolved = 5."""
        assert len(cross_raw_events) == 5, (
            f"Expected 5 raw events, got {len(cross_raw_events)}"
        )

    def test_signal_to_slot_ratio_is_at_least_two(
        self,
        cross_solo_slots: list[dict],
        cross_solo_behavioral_signals: list[dict],
    ):
        """With pre_trip + active signals, each slot should have >= 2
        behavioral signals (impression + confirmation)."""
        for slot in cross_solo_slots:
            slot_signals = [
                s for s in cross_solo_behavioral_signals
                if s["slotId"] == slot["id"]
            ]
            assert len(slot_signals) >= 2, (
                f"Slot {slot['id']} has only {len(slot_signals)} signals, "
                "expected >= 2 (impression + confirmation)"
            )
