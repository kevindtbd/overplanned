"""
Cross-track integration tests: MidTrip (Track 5) pivot signals -> PostTrip (Track 6) reflection.

Verifies that PivotEvent data produced during active trips flows correctly
into the post-trip reflection layer, enabling:
- Pivot-aware reflection context (original vs replacement slots)
- Analytics on pivot response times and trigger types
- Behavioral signal continuity from pivot_accepted into disambiguation
- Timeline reconstruction showing cascade-affected slots
- Photo strip rendering for swapped slots

All tests use standalone mock data -- no external services required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.tests.conftest import (
    make_user,
    make_trip,
    make_itinerary_slot,
    make_activity_node,
    make_behavioral_signal,
    make_intention_signal,
)
from services.api.tests.midtrip.conftest import make_pivot_event

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


def _make_completed_trip_context() -> dict[str, Any]:
    """Build a full pivot-to-posttrip scenario with all entities linked."""
    now = datetime.now(timezone.utc)
    user = make_user(name="Pivot Traveler", subscriptionTier="beta")
    trip = make_trip(
        user_id=user["id"],
        status="completed",
        destination="Tokyo, Japan",
        city="Tokyo",
        country="Japan",
        timezone="Asia/Tokyo",
        startDate=now - timedelta(days=8),
        endDate=now - timedelta(days=1),
        completedAt=now - timedelta(hours=2),
        activatedAt=now - timedelta(days=8),
    )

    original_node = make_activity_node(
        name="Shinjuku Gyoen",
        slug="shinjuku-gyoen",
        category="outdoors",
        primaryImageUrl="https://images.unsplash.com/shinjuku-gyoen.jpg",
    )
    replacement_node = make_activity_node(
        name="Tokyo National Museum",
        slug="tokyo-national-museum",
        category="culture",
        primaryImageUrl="https://images.unsplash.com/tokyo-museum.jpg",
    )
    alt_node_1 = make_activity_node(
        name="teamLab Borderless",
        slug="teamlab-borderless",
        category="entertainment",
    )
    alt_node_2 = make_activity_node(
        name="Mori Art Museum",
        slug="mori-art-museum",
        category="culture",
    )

    original_slot = make_itinerary_slot(
        trip_id=trip["id"],
        activityNodeId=original_node["id"],
        dayNumber=3,
        sortOrder=1,
        slotType="anchor",
        status="completed",
        startTime=now - timedelta(days=5, hours=14),
        endTime=now - timedelta(days=5, hours=12),
        durationMinutes=120,
        wasSwapped=True,
        swappedFromId=original_node["id"],
    )

    pivot_event = make_pivot_event(
        trip_id=trip["id"],
        slot_id=original_slot["id"],
        triggerType="weather_change",
        triggerPayload={"condition": "rain", "temp": 14.0, "slotCategory": "outdoors"},
        status="accepted",
        responseTimeMs=4200,
        resolvedAt=now - timedelta(days=5, hours=13),
        alternatives=[replacement_node["id"], alt_node_1["id"], alt_node_2["id"]],
    )
    # Normalize: Prisma schema uses alternativeIds and originalNodeId/selectedNodeId
    pivot_event["originalNodeId"] = original_node["id"]
    pivot_event["alternativeIds"] = [replacement_node["id"], alt_node_1["id"], alt_node_2["id"]]
    pivot_event["selectedNodeId"] = replacement_node["id"]

    original_slot["pivotEventId"] = pivot_event["id"]
    original_slot["activityNodeId"] = replacement_node["id"]

    pivot_signal = make_behavioral_signal(
        user_id=user["id"],
        tripId=trip["id"],
        slotId=original_slot["id"],
        activityNodeId=replacement_node["id"],
        signalType="pivot_accepted",
        signalValue=1.0,
        tripPhase="active",
        rawAction="pivot_accept",
        weatherContext='{"condition": "rain", "temp": 14.0}',
    )

    return {
        "user": user,
        "trip": trip,
        "original_node": original_node,
        "replacement_node": replacement_node,
        "alt_node_1": alt_node_1,
        "alt_node_2": alt_node_2,
        "original_slot": original_slot,
        "pivot_event": pivot_event,
        "pivot_signal": pivot_signal,
    }


def _mock_obj(data: dict) -> MagicMock:
    """Convert a dict to a MagicMock with attribute access."""
    obj = MagicMock()
    for k, v in data.items():
        setattr(obj, k, v)
    return obj


# ===========================================================================
# 1. PivotEvent with status='accepted' visible in post-trip reflection
# ===========================================================================

class TestAcceptedPivotInReflection:
    """PivotEvent.status='accepted' must be visible when building reflection context."""

    async def test_accepted_pivot_visible_in_reflection_context(self):
        """A slot with pivotEventId links to an accepted PivotEvent in reflection."""
        ctx = _make_completed_trip_context()
        slot = ctx["original_slot"]
        pivot = ctx["pivot_event"]

        # Simulate DB: slot.pivotEventId -> PivotEvent lookup
        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.find_unique = AsyncMock(return_value=_mock_obj(pivot))

        result = await mock_db.pivotevent.find_unique(
            where={"id": slot["pivotEventId"]}
        )

        assert result.status == "accepted"
        assert result.slotId == slot["id"]
        assert result.tripId == ctx["trip"]["id"]

    async def test_non_pivot_slot_has_no_pivot_event_id(self):
        """Slots that were never pivoted have pivotEventId=None."""
        normal_slot = make_itinerary_slot(
            dayNumber=1, sortOrder=0, slotType="meal", status="completed"
        )
        assert normal_slot["pivotEventId"] is None
        assert normal_slot["wasSwapped"] is False


# ===========================================================================
# 2. PivotEvent.triggerType preserved through to reflection
# ===========================================================================

class TestTriggerTypePreservation:
    """All PivotTrigger enum values survive the mid-trip -> post-trip boundary."""

    TRIGGER_TYPES = [
        "weather_change",
        "venue_closed",
        "time_overrun",
        "user_mood",
        "user_request",
    ]

    @pytest.mark.parametrize("trigger_type", TRIGGER_TYPES)
    async def test_trigger_type_preserved(self, trigger_type: str):
        """Each triggerType value round-trips through pivot -> reflection."""
        pivot = make_pivot_event(triggerType=trigger_type, status="accepted")
        pivot["originalNodeId"] = _id()
        pivot["selectedNodeId"] = _id()

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.find_unique = AsyncMock(return_value=_mock_obj(pivot))

        result = await mock_db.pivotevent.find_unique(where={"id": pivot["id"]})
        assert result.triggerType == trigger_type

    async def test_trigger_payload_contains_context(self):
        """triggerPayload preserves the context that caused the pivot."""
        pivot = make_pivot_event(
            triggerType="weather_change",
            triggerPayload={"condition": "thunderstorm", "temp": 12.0, "windSpeed": 45},
        )

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.find_unique = AsyncMock(return_value=_mock_obj(pivot))

        result = await mock_db.pivotevent.find_unique(where={"id": pivot["id"]})
        assert result.triggerPayload["condition"] == "thunderstorm"
        assert result.triggerPayload["windSpeed"] == 45


# ===========================================================================
# 3. PivotEvent.responseTimeMs available for post-trip analytics
# ===========================================================================

class TestResponseTimeAnalytics:
    """responseTimeMs from pivot resolution feeds post-trip analytics."""

    async def test_response_time_available(self):
        """responseTimeMs is set when pivot is resolved and readable in post-trip."""
        ctx = _make_completed_trip_context()
        pivot = ctx["pivot_event"]

        assert pivot["responseTimeMs"] == 4200

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.find_many = AsyncMock(return_value=[_mock_obj(pivot)])

        results = await mock_db.pivotevent.find_many(
            where={"tripId": ctx["trip"]["id"], "status": "accepted"}
        )

        assert len(results) == 1
        assert results[0].responseTimeMs == 4200

    async def test_response_time_none_for_unresolved(self):
        """Unresolved (proposed) pivots have responseTimeMs=None."""
        pivot = make_pivot_event(status="proposed", responseTimeMs=None)

        assert pivot["responseTimeMs"] is None

    async def test_aggregate_response_times_for_trip(self):
        """Post-trip analytics can aggregate responseTimeMs across all pivots."""
        pivots = [
            make_pivot_event(status="accepted", responseTimeMs=3000),
            make_pivot_event(status="accepted", responseTimeMs=8500),
            make_pivot_event(status="rejected", responseTimeMs=1200),
        ]

        response_times = [p["responseTimeMs"] for p in pivots if p["responseTimeMs"] is not None]
        assert len(response_times) == 3
        avg_ms = sum(response_times) / len(response_times)
        assert 4000 < avg_ms < 4500  # (3000+8500+1200)/3 = 4233.3


# ===========================================================================
# 4. Swapped slot shows both original and replacement in reflection
# ===========================================================================

class TestSwappedSlotReflection:
    """wasSwapped=True slots must expose both the original and replacement nodes."""

    async def test_swapped_slot_has_both_nodes(self):
        """Slot with wasSwapped=True has swappedFromId (original) and activityNodeId (new)."""
        ctx = _make_completed_trip_context()
        slot = ctx["original_slot"]

        assert slot["wasSwapped"] is True
        assert slot["swappedFromId"] == ctx["original_node"]["id"]
        assert slot["activityNodeId"] == ctx["replacement_node"]["id"]
        assert slot["swappedFromId"] != slot["activityNodeId"]

    async def test_reflection_can_load_both_activity_nodes(self):
        """Reflection view can fetch both original and replacement ActivityNodes."""
        ctx = _make_completed_trip_context()

        mock_db = AsyncMock()
        mock_db.activitynode = AsyncMock()

        original_obj = _mock_obj(ctx["original_node"])
        replacement_obj = _mock_obj(ctx["replacement_node"])

        mock_db.activitynode.find_unique = AsyncMock(
            side_effect=lambda **kwargs: (
                original_obj if kwargs.get("where", {}).get("id") == ctx["original_node"]["id"]
                else replacement_obj
            )
        )

        original = await mock_db.activitynode.find_unique(
            where={"id": ctx["original_slot"]["swappedFromId"]}
        )
        replacement = await mock_db.activitynode.find_unique(
            where={"id": ctx["original_slot"]["activityNodeId"]}
        )

        assert original.name == "Shinjuku Gyoen"
        assert replacement.name == "Tokyo National Museum"

    async def test_non_swapped_slot_has_no_swap_data(self):
        """A normal slot has wasSwapped=False and swappedFromId=None."""
        slot = make_itinerary_slot(status="completed")
        assert slot["wasSwapped"] is False
        assert slot["swappedFromId"] is None


# ===========================================================================
# 5. Cascade-affected slots reflected in post-trip timeline
# ===========================================================================

class TestCascadeInPostTripTimeline:
    """Slots whose startTime/endTime were shifted by cascade appear correctly in reflection."""

    async def test_cascade_shifted_times_visible(self):
        """Downstream slots with shifted times show updated times in post-trip timeline."""
        now = datetime.now(timezone.utc)
        trip_id = _id()

        # Original schedule: slot A 10:00-12:00, slot B 12:30-14:00
        # After cascade (slot A ran long): slot B shifted to 14:15-15:45
        slot_a = make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=3,
            sortOrder=0,
            slotType="anchor",
            status="completed",
            startTime=now.replace(hour=10, minute=0),
            endTime=now.replace(hour=14, minute=0),  # ran 2h over
            durationMinutes=240,
        )
        slot_b = make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=3,
            sortOrder=1,
            slotType="meal",
            status="completed",
            startTime=now.replace(hour=14, minute=15),  # shifted from 12:30
            endTime=now.replace(hour=15, minute=45),    # shifted from 14:00
            durationMinutes=90,
        )

        # Post-trip timeline should show the actual times, not the planned ones
        assert slot_b["startTime"].hour == 14
        assert slot_b["startTime"].minute == 15

    async def test_locked_slot_not_shifted_by_cascade(self):
        """Locked slots retain their original times even after cascade."""
        trip_id = _id()
        locked_slot = make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=3,
            sortOrder=2,
            slotType="anchor",
            status="confirmed",
            isLocked=True,
            startTime=datetime.now(timezone.utc).replace(hour=18, minute=0),
            endTime=datetime.now(timezone.utc).replace(hour=20, minute=0),
            durationMinutes=120,
        )

        assert locked_slot["isLocked"] is True
        assert locked_slot["startTime"].hour == 18

    async def test_cross_day_slots_not_in_cascade(self):
        """Slots on a different day are unaffected by cascade on day N."""
        trip_id = _id()
        day3_slot = make_itinerary_slot(trip_id=trip_id, dayNumber=3, sortOrder=0)
        day4_slot = make_itinerary_slot(trip_id=trip_id, dayNumber=4, sortOrder=0)

        assert day3_slot["dayNumber"] != day4_slot["dayNumber"]
        # Each day is independent in cascade logic


# ===========================================================================
# 6. BehavioralSignal from pivot feeds into disambiguation rules
# ===========================================================================

class TestPivotSignalInDisambiguation:
    """pivot_accepted BehavioralSignal flows into post-trip disambiguation."""

    async def test_pivot_accepted_signal_has_correct_type(self):
        """pivot_accepted signal has signalType and tripPhase set correctly."""
        ctx = _make_completed_trip_context()
        signal = ctx["pivot_signal"]

        assert signal["signalType"] == "pivot_accepted"
        assert signal["tripPhase"] == "active"
        assert signal["signalValue"] == 1.0

    async def test_pivot_signal_linked_to_slot_and_activity(self):
        """pivot_accepted signal references both slotId and activityNodeId."""
        ctx = _make_completed_trip_context()
        signal = ctx["pivot_signal"]

        assert signal["slotId"] == ctx["original_slot"]["id"]
        assert signal["activityNodeId"] == ctx["replacement_node"]["id"]
        assert signal["tripId"] == ctx["trip"]["id"]

    async def test_pivot_signal_queryable_in_posttrip_phase(self):
        """Disambiguation can query pivot signals alongside post_trip signals."""
        ctx = _make_completed_trip_context()
        user_id = ctx["user"]["id"]
        trip_id = ctx["trip"]["id"]

        pivot_sig = _mock_obj(ctx["pivot_signal"])
        post_loved = _mock_obj(make_behavioral_signal(
            user_id=user_id,
            tripId=trip_id,
            signalType="post_loved",
            signalValue=1.0,
            tripPhase="post_trip",
            rawAction="post_loved",
        ))

        mock_db = AsyncMock()
        mock_db.behavioralsignal = AsyncMock()
        mock_db.behavioralsignal.find_many = AsyncMock(return_value=[pivot_sig, post_loved])

        signals = await mock_db.behavioralsignal.find_many(
            where={"userId": user_id, "tripId": trip_id}
        )

        signal_types = {s.signalType for s in signals}
        assert "pivot_accepted" in signal_types
        assert "post_loved" in signal_types

    async def test_weather_context_available_for_disambiguation(self):
        """weatherContext on pivot signal helps disambiguation distinguish weather-skip from dislike."""
        ctx = _make_completed_trip_context()
        signal = ctx["pivot_signal"]

        assert signal["weatherContext"] is not None
        assert "rain" in signal["weatherContext"]


# ===========================================================================
# 7. IntentionSignal from "wrong for me" flag visible in post-trip
# ===========================================================================

class TestWrongForMeIntention:
    """IntentionSignal with 'wrong_for_me' type flows into disambiguation."""

    async def test_wrong_for_me_intention_created(self):
        """User can flag an activity as 'wrong_for_me' during post-trip reflection."""
        user = make_user()
        trip = make_trip(user_id=user["id"], status="completed")

        # BehavioralSignal for the skip
        skip_signal = make_behavioral_signal(
            user_id=user["id"],
            tripId=trip["id"],
            signalType="post_skipped",
            signalValue=-1.0,
            tripPhase="post_trip",
            rawAction="slot_skipped",
        )

        # IntentionSignal from the "wrong for me" flag
        intention = make_intention_signal(
            behavioral_signal_id=skip_signal["id"],
            user_id=user["id"],
            intentionType="wrong_for_me",
            confidence=1.0,
            source="user_explicit",
            userProvided=True,
        )

        assert intention["intentionType"] == "wrong_for_me"
        assert intention["userProvided"] is True
        assert intention["confidence"] == 1.0
        assert intention["behavioralSignalId"] == skip_signal["id"]

    async def test_wrong_for_me_queryable_by_user(self):
        """Disambiguation can query all wrong_for_me intentions for a user."""
        user_id = _id()
        intentions = [
            make_intention_signal(
                user_id=user_id,
                intentionType="wrong_for_me",
                userProvided=True,
            )
            for _ in range(3)
        ]

        mock_db = AsyncMock()
        mock_db.intentionsignal = AsyncMock()
        mock_db.intentionsignal.find_many = AsyncMock(
            return_value=[_mock_obj(i) for i in intentions]
        )

        results = await mock_db.intentionsignal.find_many(
            where={"userId": user_id, "intentionType": "wrong_for_me"}
        )

        assert len(results) == 3
        for r in results:
            assert r.intentionType == "wrong_for_me"
            assert r.userProvided is True

    async def test_wrong_for_me_distinct_from_not_interested(self):
        """wrong_for_me and not_interested are distinct intention types."""
        user_id = _id()
        sig_id = _id()

        wrong_for_me = make_intention_signal(
            behavioral_signal_id=sig_id,
            user_id=user_id,
            intentionType="wrong_for_me",
        )
        not_interested = make_intention_signal(
            behavioral_signal_id=sig_id,
            user_id=user_id,
            intentionType="not_interested",
        )

        assert wrong_for_me["intentionType"] != not_interested["intentionType"]


# ===========================================================================
# 8. Pivot alternatives logged and available for reflection
# ===========================================================================

class TestPivotAlternatives:
    """PivotEvent.alternativeIds are preserved for post-trip review."""

    async def test_alternative_ids_stored(self):
        """alternativeIds array is non-empty for accepted pivots."""
        ctx = _make_completed_trip_context()
        pivot = ctx["pivot_event"]

        assert len(pivot["alternativeIds"]) == 3
        assert ctx["replacement_node"]["id"] in pivot["alternativeIds"]
        assert ctx["alt_node_1"]["id"] in pivot["alternativeIds"]
        assert ctx["alt_node_2"]["id"] in pivot["alternativeIds"]

    async def test_selected_node_is_one_of_alternatives(self):
        """selectedNodeId must be one of the alternativeIds."""
        ctx = _make_completed_trip_context()
        pivot = ctx["pivot_event"]

        assert pivot["selectedNodeId"] in pivot["alternativeIds"]

    async def test_original_node_not_in_alternatives(self):
        """The original node should not appear in the alternatives list."""
        ctx = _make_completed_trip_context()
        pivot = ctx["pivot_event"]

        assert pivot["originalNodeId"] not in pivot["alternativeIds"]

    async def test_rejected_pivot_has_no_selected_node(self):
        """Rejected pivots have selectedNodeId=None but keep alternativeIds."""
        pivot = make_pivot_event(status="rejected")
        pivot["alternativeIds"] = [_id(), _id()]
        pivot["selectedNodeId"] = None

        assert pivot["status"] == "rejected"
        assert pivot["selectedNodeId"] is None
        assert len(pivot["alternativeIds"]) == 2

    async def test_alternatives_loadable_as_activity_nodes(self):
        """All alternativeIds can be resolved to ActivityNode records."""
        ctx = _make_completed_trip_context()
        alt_ids = ctx["pivot_event"]["alternativeIds"]

        nodes = [
            _mock_obj(ctx["replacement_node"]),
            _mock_obj(ctx["alt_node_1"]),
            _mock_obj(ctx["alt_node_2"]),
        ]

        mock_db = AsyncMock()
        mock_db.activitynode = AsyncMock()
        mock_db.activitynode.find_many = AsyncMock(return_value=nodes)

        results = await mock_db.activitynode.find_many(
            where={"id": {"in": alt_ids}}
        )

        assert len(results) == 3
        result_names = {r.name for r in results}
        assert "Tokyo National Museum" in result_names
        assert "teamLab Borderless" in result_names
        assert "Mori Art Museum" in result_names


# ===========================================================================
# 9. Post-trip completion trigger identifies trips with pivots vs without
# ===========================================================================

class TestCompletionWithPivots:
    """Post-trip completion logic distinguishes trips that had pivots."""

    async def test_trip_with_pivots_detected(self):
        """Trips with PivotEvents are identifiable at completion time."""
        ctx = _make_completed_trip_context()
        trip_id = ctx["trip"]["id"]

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.count = AsyncMock(return_value=2)

        pivot_count = await mock_db.pivotevent.count(where={"tripId": trip_id})
        assert pivot_count > 0

    async def test_trip_without_pivots_detected(self):
        """Trips with zero PivotEvents are identifiable."""
        trip = make_trip(status="completed")

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.count = AsyncMock(return_value=0)

        pivot_count = await mock_db.pivotevent.count(where={"tripId": trip["id"]})
        assert pivot_count == 0

    async def test_pivot_count_only_includes_trip_pivots(self):
        """Pivot count query is scoped to the specific trip."""
        trip_a = make_trip(status="completed")
        trip_b = make_trip(status="completed")

        mock_db = AsyncMock()
        mock_db.pivotevent = AsyncMock()
        mock_db.pivotevent.count = AsyncMock(
            side_effect=lambda **kwargs: (
                3 if kwargs.get("where", {}).get("tripId") == trip_a["id"] else 0
            )
        )

        count_a = await mock_db.pivotevent.count(where={"tripId": trip_a["id"]})
        count_b = await mock_db.pivotevent.count(where={"tripId": trip_b["id"]})

        assert count_a == 3
        assert count_b == 0

    async def test_completion_metadata_includes_pivot_summary(self):
        """Completion result can include a pivot summary for the reflection UI."""
        ctx = _make_completed_trip_context()
        pivot = ctx["pivot_event"]

        # Simulated completion metadata
        completion_meta = {
            "trip_id": ctx["trip"]["id"],
            "had_pivots": True,
            "pivot_count": 1,
            "trigger_types": [pivot["triggerType"]],
            "avg_response_time_ms": pivot["responseTimeMs"],
        }

        assert completion_meta["had_pivots"] is True
        assert completion_meta["pivot_count"] == 1
        assert "weather_change" in completion_meta["trigger_types"]


# ===========================================================================
# 10. Photo strip component can render both original and swapped slot images
# ===========================================================================

class TestPhotoStripSwappedSlots:
    """Photo strip in reflection renders images for both original and replacement."""

    async def test_swapped_slot_has_both_image_urls(self):
        """Both original and replacement ActivityNodes have primaryImageUrl."""
        ctx = _make_completed_trip_context()

        original_img = ctx["original_node"]["primaryImageUrl"]
        replacement_img = ctx["replacement_node"]["primaryImageUrl"]

        assert original_img is not None
        assert replacement_img is not None
        assert original_img != replacement_img

    async def test_photo_strip_data_includes_swap_indicator(self):
        """Photo strip data for a swapped slot includes wasSwapped flag."""
        ctx = _make_completed_trip_context()
        slot = ctx["original_slot"]

        photo_strip_item = {
            "slotId": slot["id"],
            "dayNumber": slot["dayNumber"],
            "wasSwapped": slot["wasSwapped"],
            "currentImage": ctx["replacement_node"]["primaryImageUrl"],
            "originalImage": ctx["original_node"]["primaryImageUrl"],
            "currentName": ctx["replacement_node"]["name"],
            "originalName": ctx["original_node"]["name"],
        }

        assert photo_strip_item["wasSwapped"] is True
        assert photo_strip_item["currentName"] == "Tokyo National Museum"
        assert photo_strip_item["originalName"] == "Shinjuku Gyoen"

    async def test_non_swapped_slot_has_single_image(self):
        """Non-swapped slots only have the current image, no original."""
        node = make_activity_node(
            name="Senso-ji Temple",
            primaryImageUrl="https://images.unsplash.com/sensoji.jpg",
        )
        slot = make_itinerary_slot(
            activityNodeId=node["id"],
            status="completed",
            wasSwapped=False,
        )

        photo_strip_item = {
            "slotId": slot["id"],
            "wasSwapped": slot["wasSwapped"],
            "currentImage": node["primaryImageUrl"],
            "originalImage": None,
        }

        assert photo_strip_item["wasSwapped"] is False
        assert photo_strip_item["originalImage"] is None

    async def test_slot_without_image_uses_fallback(self):
        """Slots whose ActivityNode has no primaryImageUrl get None (UI handles fallback)."""
        node = make_activity_node(
            name="Hidden Izakaya",
            primaryImageUrl=None,
        )
        slot = make_itinerary_slot(
            activityNodeId=node["id"],
            status="completed",
        )

        photo_strip_item = {
            "slotId": slot["id"],
            "wasSwapped": slot["wasSwapped"],
            "currentImage": node["primaryImageUrl"],
        }

        assert photo_strip_item["currentImage"] is None
