"""
Tests for PivotDetector — the orchestrator that runs all triggers and writes PivotEvent records.

Covers:
  - MAX_PIVOT_DEPTH=1: wasSwapped slots are skipped entirely
  - Terminal slot statuses (completed, skipped) are skipped
  - Trigger priority order (UserMood > Weather > VenueClosure > TimeOverrun)
  - First-trigger-wins: only one PivotEvent per slot per evaluation
  - Alternative fetching via ActivitySearchService
  - DB persistence path (success + failure)
  - evaluate_trip: multi-slot evaluation with shared weather fetch
  - evaluate_slot: single-slot convenience method
  - Graceful degradation when search or DB fails
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.pivot.detector import PivotDetector, _build_alternative_query, MAX_PIVOT_DEPTH
from services.api.pivot.triggers import TriggerResult
from services.api.tests.conftest import make_trip, make_itinerary_slot, make_activity_node


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_trip(timezone: str = "UTC", city: str = "Tokyo") -> dict[str, Any]:
    t = make_trip()
    t["timezone"] = timezone
    t["city"] = city
    return t


def _make_active_slot(**overrides) -> dict[str, Any]:
    slot = make_itinerary_slot()
    slot["status"] = "active"
    slot["wasSwapped"] = False
    slot["activityNodeId"] = "node-original-001"
    slot.update(overrides)
    return slot


def _make_search_result(node_ids: list[str]) -> dict[str, Any]:
    return {
        "results": [{"id": nid, "score": 0.9 - (i * 0.05)} for i, nid in enumerate(node_ids)],
        "count": len(node_ids),
        "warning": None,
    }


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_search():
    svc = AsyncMock()
    svc.search = AsyncMock(return_value=_make_search_result(
        ["node-alt-001", "node-alt-002", "node-alt-003"]
    ))
    return svc


@pytest.fixture
def mock_weather_service():
    svc = MagicMock()
    # Default: clear weather, no triggers
    svc.get_weather = AsyncMock(return_value={"condition": "clear", "code": 800, "temp_c": 22.0})
    svc.is_outdoor_slot = MagicMock(return_value=False)
    svc.should_trigger_weather_pivot = MagicMock(return_value=False)
    return svc


@pytest.fixture
def detector(mock_db, mock_search, mock_weather_service):
    return PivotDetector(
        db=mock_db,
        search_service=mock_search,
        weather_service=mock_weather_service,
    )


# ---------------------------------------------------------------------------
# _build_alternative_query tests
# ---------------------------------------------------------------------------

class TestBuildAlternativeQuery:
    def test_with_category_and_no_vibe_tags(self):
        slot = _make_active_slot()
        slot["category"] = "outdoors"
        slot["activityNode"] = None
        query = _build_alternative_query(slot)
        assert "indoor" in query  # Fallback to indoor for outdoor category
        assert "outdoors" in query

    def test_with_vibe_tags(self):
        slot = _make_active_slot()
        slot["category"] = "culture"
        node = make_activity_node()
        node["vibeTags"] = [{"name": "historic", "slug": "historic"}, {"name": "quiet"}]
        slot["activityNode"] = node
        query = _build_alternative_query(slot)
        assert "culture" in query
        assert "historic" in query

    def test_with_no_category_falls_back(self):
        slot = _make_active_slot()
        slot["category"] = None
        slot["slotType"] = "flex"
        slot["activityNode"] = None
        query = _build_alternative_query(slot)
        assert "flex" in query or "activity" in query


# ---------------------------------------------------------------------------
# MAX_PIVOT_DEPTH enforcement
# ---------------------------------------------------------------------------

class TestMaxPivotDepth:
    @pytest.mark.asyncio
    async def test_swapped_slot_is_skipped(self, detector):
        trip = _make_trip()
        slot = _make_active_slot()
        slot["wasSwapped"] = True  # This slot is already a pivot replacement

        events = await detector.evaluate_trip(trip, [slot])

        assert events == []

    @pytest.mark.asyncio
    async def test_non_swapped_slot_is_evaluated(self, detector, mock_weather_service):
        """Non-swapped slots should go through trigger evaluation."""
        trip = _make_trip()
        slot = _make_active_slot()
        slot["wasSwapped"] = False

        # Simulate user mood trigger via mood slot_id
        # Weather and other triggers all return no-trigger by default in this fixture

        # Force weather trigger to fire
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 16.0}
        )
        slot["category"] = "outdoors"

        events = await detector.evaluate_trip(trip, [slot])

        assert len(events) == 1
        assert events[0]["triggerType"] == "weather_change"


# ---------------------------------------------------------------------------
# Terminal slot status guard
# ---------------------------------------------------------------------------

class TestTerminalStatusGuard:
    @pytest.mark.asyncio
    async def test_completed_slot_skipped(self, detector):
        trip = _make_trip()
        slot = _make_active_slot(status="completed")

        events = await detector.evaluate_trip(trip, [slot])
        assert events == []

    @pytest.mark.asyncio
    async def test_skipped_slot_skipped(self, detector):
        trip = _make_trip()
        slot = _make_active_slot(status="skipped")

        events = await detector.evaluate_trip(trip, [slot])
        assert events == []

    @pytest.mark.asyncio
    async def test_archived_slot_skipped(self, detector):
        trip = _make_trip()
        slot = _make_active_slot(status="archived")

        events = await detector.evaluate_trip(trip, [slot])
        assert events == []


# ---------------------------------------------------------------------------
# Trigger priority order
# ---------------------------------------------------------------------------

class TestTriggerPriority:
    @pytest.mark.asyncio
    async def test_user_mood_fires_before_weather(self, detector, mock_weather_service):
        """UserMoodTrigger has highest priority — if it fires, no other trigger is checked."""
        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        # Weather would also trigger
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 15.0}
        )

        # User mood for this specific slot
        events = await detector.evaluate_trip(
            trip,
            [slot],
            user_mood_slot_id=slot["id"],
            user_id="user-abc",
        )

        assert len(events) == 1
        # User mood should win
        assert events[0]["triggerType"] == "user_mood"

    @pytest.mark.asyncio
    async def test_only_one_event_per_slot(self, detector, mock_weather_service):
        """Only one PivotEvent should be created per slot per evaluation, even if multiple triggers fire."""
        trip = _make_trip()
        slot = _make_active_slot()

        # Force weather trigger
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 15.0}
        )
        slot["category"] = "outdoors"
        # Also set endTime in past to trigger TimeOverrun
        slot["endTime"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        events = await detector.evaluate_trip(trip, [slot])

        # Still only one event — weather fires first (higher priority than time_overrun)
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Alternative fetching
# ---------------------------------------------------------------------------

class TestAlternativeFetching:
    @pytest.mark.asyncio
    async def test_alternatives_exclude_original_node(self, mock_db, mock_weather_service):
        """Original activityNodeId must not appear in alternativeIds."""
        original_id = "node-original-001"
        # Put original in search results
        search_results = _make_search_result(
            [original_id, "node-alt-001", "node-alt-002"]
        )
        mock_search = AsyncMock()
        mock_search.search = AsyncMock(return_value=search_results)

        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)

        trip = _make_trip()
        slot = _make_active_slot(activityNodeId=original_id)
        slot["category"] = "outdoors"

        events = await det.evaluate_trip(trip, [slot])

        assert len(events) == 1
        assert original_id not in events[0]["alternativeIds"]
        assert "node-alt-001" in events[0]["alternativeIds"]

    @pytest.mark.asyncio
    async def test_alternatives_capped_at_max(self, mock_db, mock_weather_service):
        """alternativeIds should never exceed MAX_ALTERNATIVES (5)."""
        many_ids = [f"node-alt-{i:03d}" for i in range(10)]
        mock_search = AsyncMock()
        mock_search.search = AsyncMock(return_value=_make_search_result(many_ids))

        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)

        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        events = await det.evaluate_trip(trip, [slot])

        assert len(events[0]["alternativeIds"]) <= 5

    @pytest.mark.asyncio
    async def test_search_failure_returns_empty_alternatives(self, mock_db, mock_weather_service):
        """Search failure should not prevent pivot event creation — just empty alternatives."""
        mock_search = AsyncMock()
        mock_search.search = AsyncMock(side_effect=Exception("Qdrant down"))

        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 13.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)

        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        events = await det.evaluate_trip(trip, [slot])

        assert len(events) == 1
        assert events[0]["alternativeIds"] == []


# ---------------------------------------------------------------------------
# PivotEvent structure
# ---------------------------------------------------------------------------

class TestPivotEventStructure:
    @pytest.mark.asyncio
    async def test_pivot_event_has_required_fields(self, detector, mock_weather_service):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "storm", "code": 211, "temp_c": 19.0}
        )

        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "active"

        events = await detector.evaluate_trip(trip, [slot])

        assert len(events) == 1
        event = events[0]

        required_fields = [
            "id", "tripId", "slotId", "triggerType", "triggerPayload",
            "originalNodeId", "alternativeIds", "selectedNodeId", "status",
            "resolvedAt", "responseTimeMs", "createdAt",
        ]
        for field in required_fields:
            assert field in event, f"Missing field: {field}"

        assert event["status"] == "proposed"
        assert event["selectedNodeId"] is None
        assert event["resolvedAt"] is None
        assert event["tripId"] == trip["id"]
        assert event["slotId"] == slot["id"]

    @pytest.mark.asyncio
    async def test_pivot_event_trigger_payload_is_dict(self, detector, mock_weather_service):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "drizzle", "code": 310, "temp_c": 17.0}
        )

        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        events = await detector.evaluate_trip(trip, [slot])

        assert isinstance(events[0]["triggerPayload"], dict)


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

class TestDBPersistence:
    @pytest.mark.asyncio
    async def test_db_execute_called_on_pivot(self, mock_db, mock_search, mock_weather_service):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 502, "temp_c": 15.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        await det.evaluate_trip(trip, [slot])

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_failure_does_not_raise(self, mock_search, mock_weather_service):
        """DB write failure should be logged and swallowed — the in-memory event still returns."""
        failing_db = AsyncMock()
        failing_db.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=failing_db, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        events = await det.evaluate_trip(trip, [slot])

        # Event still returned despite DB failure
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_none_db_does_not_raise(self, mock_search, mock_weather_service):
        """If db=None (lifespan not yet wired), persistence is skipped gracefully."""
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=None, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()
        slot = _make_active_slot()
        slot["category"] = "outdoors"

        events = await det.evaluate_trip(trip, [slot])
        assert len(events) == 1


# ---------------------------------------------------------------------------
# evaluate_trip: multi-slot, shared weather fetch
# ---------------------------------------------------------------------------

class TestEvaluateTripMultiSlot:
    @pytest.mark.asyncio
    async def test_weather_fetched_once_for_multiple_slots(
        self, mock_db, mock_search, mock_weather_service
    ):
        """get_weather() is called once regardless of slot count — cache handles the rest."""
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "clear", "code": 800, "temp_c": 22.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()
        slots = [_make_active_slot() for _ in range(5)]

        await det.evaluate_trip(trip, slots)

        mock_weather_service.get_weather.assert_called_once_with("Tokyo")

    @pytest.mark.asyncio
    async def test_each_triggering_slot_gets_own_event(
        self, mock_db, mock_search, mock_weather_service
    ):
        """Multiple triggering slots each produce their own PivotEvent."""
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()
        slots = [_make_active_slot(category="outdoors") for _ in range(3)]

        events = await det.evaluate_trip(trip, slots)

        assert len(events) == 3
        # Each event should reference a different slot
        slot_ids = {e["slotId"] for e in events}
        assert len(slot_ids) == 3

    @pytest.mark.asyncio
    async def test_swapped_slots_excluded_non_swapped_evaluated(
        self, mock_db, mock_search, mock_weather_service
    ):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=True)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=True)
        mock_weather_service.get_weather = AsyncMock(
            return_value={"condition": "rain", "code": 501, "temp_c": 14.0}
        )

        det = PivotDetector(db=mock_db, search_service=mock_search, weather_service=mock_weather_service)
        trip = _make_trip()

        swapped = _make_active_slot(category="outdoors")
        swapped["wasSwapped"] = True

        fresh = _make_active_slot(category="outdoors")
        fresh["wasSwapped"] = False

        events = await det.evaluate_trip(trip, [swapped, fresh])

        assert len(events) == 1
        assert events[0]["slotId"] == fresh["id"]


# ---------------------------------------------------------------------------
# evaluate_slot: convenience method
# ---------------------------------------------------------------------------

class TestEvaluateSlot:
    @pytest.mark.asyncio
    async def test_evaluate_single_slot_returns_event(self, detector, mock_weather_service):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=False)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=False)
        mock_weather_service.get_weather = AsyncMock(return_value=None)

        trip = _make_trip()
        slot = _make_active_slot()
        slot["status"] = "active"

        # Trigger via user mood
        result = await detector.evaluate_slot(
            slot, trip, user_mood=True, user_id="u-test-123"
        )

        assert result is not None
        assert result["triggerType"] == "user_mood"

    @pytest.mark.asyncio
    async def test_evaluate_single_slot_no_trigger_returns_none(self, detector, mock_weather_service):
        mock_weather_service.is_outdoor_slot = MagicMock(return_value=False)
        mock_weather_service.should_trigger_weather_pivot = MagicMock(return_value=False)
        mock_weather_service.get_weather = AsyncMock(return_value=None)

        trip = _make_trip()
        slot = _make_active_slot()
        slot["endTime"] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        result = await detector.evaluate_slot(slot, trip, user_mood=False)

        assert result is None
