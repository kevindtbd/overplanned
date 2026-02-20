"""
Tests for individual pivot trigger classes.

Covers:
  - WeatherTrigger: outdoor category detection, bad weather conditions
  - VenueClosureTrigger: hours parsing, timezone-aware time comparison
  - TimeOverrunTrigger: endTime comparison, status filtering, timezone
  - UserMoodTrigger: explicit user signal, slot status guards

All tests are pure unit tests — no DB, no external services.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.pivot.triggers import (
    WeatherTrigger,
    VenueClosureTrigger,
    TimeOverrunTrigger,
    UserMoodTrigger,
    TriggerResult,
    _parse_hours_range,
)
from tests.conftest import make_trip, make_itinerary_slot, make_activity_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_weather_summary(
    condition: str = "clear",
    code: int = 800,
    temp_c: float = 22.0,
) -> dict[str, Any]:
    return {"condition": condition, "code": code, "temp_c": temp_c}


def _make_mock_weather_service(should_trigger: bool = False, is_outdoor: bool = True):
    """Return a mock WeatherService with configurable behaviour."""
    svc = MagicMock()
    svc.is_outdoor_slot = MagicMock(return_value=is_outdoor)
    svc.should_trigger_weather_pivot = MagicMock(return_value=should_trigger)
    return svc


def _slot_with_category(category: str, **overrides) -> dict[str, Any]:
    slot = make_itinerary_slot()
    slot["category"] = category
    slot.update(overrides)
    return slot


def _trip(timezone: str = "Asia/Tokyo") -> dict[str, Any]:
    t = make_trip()
    t["timezone"] = timezone
    t["city"] = "Tokyo"
    return t


# ---------------------------------------------------------------------------
# TriggerResult tests
# ---------------------------------------------------------------------------

class TestTriggerResult:
    def test_no_trigger_factory(self):
        result = TriggerResult.no_trigger("weather_change", reason="test")
        assert result.triggered is False
        assert result.trigger_type == "weather_change"
        assert result.reason == "test"
        assert result.payload == {}

    def test_fired_factory(self):
        payload = {"condition": "rain", "code": 501}
        result = TriggerResult.fired("weather_change", payload=payload, reason="raining")
        assert result.triggered is True
        assert result.trigger_type == "weather_change"
        assert result.payload == payload
        assert result.reason == "raining"


# ---------------------------------------------------------------------------
# WeatherTrigger tests
# ---------------------------------------------------------------------------

class TestWeatherTrigger:
    @pytest.mark.asyncio
    async def test_fires_for_outdoor_slot_in_rain(self):
        svc = _make_mock_weather_service(should_trigger=True, is_outdoor=True)
        trigger = WeatherTrigger(weather_service=svc)

        slot = _slot_with_category("outdoors")
        trip = _trip()
        summary = _make_weather_summary("rain", 501)

        result = await trigger.evaluate(slot, trip, weather_summary=summary)

        assert result.triggered is True
        assert result.trigger_type == "weather_change"
        assert "outdoor_risk" not in result.payload  # payload fields from trigger, not service
        assert result.payload["condition"] == "rain"

    @pytest.mark.asyncio
    async def test_does_not_fire_for_indoor_slot(self):
        svc = _make_mock_weather_service(should_trigger=True, is_outdoor=False)
        trigger = WeatherTrigger(weather_service=svc)

        slot = _slot_with_category("dining")
        trip = _trip()
        summary = _make_weather_summary("rain", 501)

        result = await trigger.evaluate(slot, trip, weather_summary=summary)

        assert result.triggered is False
        assert "not weather-sensitive" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_without_weather_data(self):
        svc = _make_mock_weather_service(should_trigger=False, is_outdoor=True)
        trigger = WeatherTrigger(weather_service=svc)

        slot = _slot_with_category("outdoors")
        trip = _trip()

        result = await trigger.evaluate(slot, trip, weather_summary=None)

        assert result.triggered is False
        assert "No weather data" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_for_clear_weather_outdoors(self):
        svc = _make_mock_weather_service(should_trigger=False, is_outdoor=True)
        trigger = WeatherTrigger(weather_service=svc)

        slot = _slot_with_category("outdoors")
        trip = _trip()
        summary = _make_weather_summary("clear", 800)

        result = await trigger.evaluate(slot, trip, weather_summary=summary)

        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_payload_includes_city_and_category(self):
        svc = _make_mock_weather_service(should_trigger=True, is_outdoor=True)
        trigger = WeatherTrigger(weather_service=svc)

        slot = _slot_with_category("active")
        trip = _trip()
        trip["city"] = "Osaka"
        summary = _make_weather_summary("thunderstorm", 211)

        result = await trigger.evaluate(slot, trip, weather_summary=summary)

        assert result.triggered is True
        assert result.payload["city"] == "Osaka"
        assert result.payload["slot_category"] == "active"
        assert result.payload["code"] == 211


# ---------------------------------------------------------------------------
# VenueClosureTrigger tests
# ---------------------------------------------------------------------------

class TestParseHoursRange:
    def test_normal_range(self):
        assert _parse_hours_range("09:00-22:00") == (540, 1320)

    def test_overnight_boundary(self):
        # Overnight ranges not supported — treated as normal parse
        result = _parse_hours_range("18:00-02:00")
        assert result == (1080, 120)  # parsed but close < open — caller handles

    def test_same_open_close_returns_none(self):
        assert _parse_hours_range("00:00-00:00") is None

    def test_invalid_format_returns_none(self):
        assert _parse_hours_range("always open") is None
        assert _parse_hours_range("9am-10pm") is None
        assert _parse_hours_range("") is None

    def test_midnight_close(self):
        result = _parse_hours_range("09:00-00:00")
        assert result == (540, 0)


class TestVenueClosureTrigger:
    def _make_slot_with_hours(
        self,
        hours: dict[str, str],
        start_time: datetime | None = None,
        **overrides,
    ) -> dict[str, Any]:
        node = make_activity_node()
        node["hours"] = hours
        node["name"] = "Test Venue"
        slot = make_itinerary_slot()
        slot["activityNode"] = node
        slot["startTime"] = start_time.isoformat() if start_time else None
        slot.update(overrides)
        return slot

    @pytest.mark.asyncio
    async def test_fires_when_venue_closed(self):
        trigger = VenueClosureTrigger()
        trip = _trip("Asia/Tokyo")

        # Monday hours: 09:00-17:00
        # Test at a Monday 18:00 UTC (which in Asia/Tokyo +9 = 03:00 Tuesday — so we pick Friday)
        # Simplest: use UTC timezone for trip and a fixed time
        trip["timezone"] = "UTC"
        # Friday 20:00 UTC (outside 09:00-17:00)
        test_now = datetime(2026, 2, 20, 20, 0, 0, tzinfo=timezone.utc)  # Friday
        slot = self._make_slot_with_hours(
            hours={"friday": "09:00-17:00"},
            start_time=test_now,
        )

        result = await trigger.evaluate(slot, trip, now_utc=test_now)

        assert result.triggered is True
        assert result.trigger_type == "venue_closed"
        assert "20:00" in result.payload["slot_time_local"]

    @pytest.mark.asyncio
    async def test_does_not_fire_when_open(self):
        trigger = VenueClosureTrigger()
        trip = _trip("UTC")

        # Friday 11:00 UTC — inside 09:00-22:00
        test_now = datetime(2026, 2, 20, 11, 0, 0, tzinfo=timezone.utc)
        slot = self._make_slot_with_hours(
            hours={"friday": "09:00-22:00"},
            start_time=test_now,
        )

        result = await trigger.evaluate(slot, trip, now_utc=test_now)

        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_does_not_fire_without_hours_data(self):
        trigger = VenueClosureTrigger()
        trip = _trip("UTC")

        node = make_activity_node()
        node["hours"] = None
        slot = make_itinerary_slot()
        slot["activityNode"] = node

        result = await trigger.evaluate(slot, trip)

        assert result.triggered is False
        assert "No hours data" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_when_no_hours_for_day(self):
        trigger = VenueClosureTrigger()
        trip = _trip("UTC")

        # Friday — no friday key in hours
        test_now = datetime(2026, 2, 20, 11, 0, 0, tzinfo=timezone.utc)
        slot = self._make_slot_with_hours(
            hours={"monday": "09:00-22:00"},  # No friday
            start_time=test_now,
        )

        result = await trigger.evaluate(slot, trip, now_utc=test_now)

        assert result.triggered is False
        assert "friday" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_does_not_fire_with_unparseable_hours(self):
        trigger = VenueClosureTrigger()
        trip = _trip("UTC")

        test_now = datetime(2026, 2, 20, 20, 0, 0, tzinfo=timezone.utc)
        slot = self._make_slot_with_hours(
            hours={"friday": "always open"},
            start_time=test_now,
        )

        result = await trigger.evaluate(slot, trip, now_utc=test_now)

        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_payload_includes_venue_name(self):
        trigger = VenueClosureTrigger()
        trip = _trip("UTC")

        test_now = datetime(2026, 2, 20, 20, 0, 0, tzinfo=timezone.utc)
        slot = self._make_slot_with_hours(
            hours={"friday": "09:00-17:00"},
            start_time=test_now,
        )
        slot["activityNode"]["name"] = "Senso-ji Temple"

        result = await trigger.evaluate(slot, trip, now_utc=test_now)

        assert result.triggered is True
        assert result.payload["venue_name"] == "Senso-ji Temple"
        assert result.payload["hours"] == "09:00-17:00"


# ---------------------------------------------------------------------------
# TimeOverrunTrigger tests
# ---------------------------------------------------------------------------

class TestTimeOverrunTrigger:
    @pytest.mark.asyncio
    async def test_fires_when_past_end_time(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        end_time = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 15, 30, 0, tzinfo=timezone.utc)  # 90 min overrun

        slot = make_itinerary_slot()
        slot["endTime"] = end_time.isoformat()
        slot["status"] = "active"

        result = await trigger.evaluate(slot, trip, now_utc=now)

        assert result.triggered is True
        assert result.trigger_type == "time_overrun"
        assert result.payload["overrun_minutes"] == 90.0

    @pytest.mark.asyncio
    async def test_does_not_fire_when_not_overrun(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        end_time = datetime(2026, 2, 20, 16, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)  # 2h before end

        slot = make_itinerary_slot()
        slot["endTime"] = end_time.isoformat()
        slot["status"] = "active"

        result = await trigger.evaluate(slot, trip, now_utc=now)

        assert result.triggered is False
        assert "not overrun" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_for_completed_slot(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        end_time = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 15, 0, 0, tzinfo=timezone.utc)

        slot = make_itinerary_slot()
        slot["endTime"] = end_time.isoformat()
        slot["status"] = "completed"  # Already done — no pivot needed

        result = await trigger.evaluate(slot, trip, now_utc=now)

        assert result.triggered is False
        assert "completed" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_for_skipped_slot(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        slot = make_itinerary_slot()
        slot["endTime"] = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc).isoformat()
        slot["status"] = "skipped"

        result = await trigger.evaluate(slot, trip, now_utc=datetime(2026, 2, 20, 15, 0, 0, tzinfo=timezone.utc))

        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_does_not_fire_without_end_time(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        slot = make_itinerary_slot()
        slot["endTime"] = None
        slot["status"] = "active"

        result = await trigger.evaluate(slot, trip, now_utc=datetime.now(timezone.utc))

        assert result.triggered is False
        assert "no endTime" in result.reason

    @pytest.mark.asyncio
    async def test_payload_includes_overrun_details(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        end_time = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 14, 45, 0, tzinfo=timezone.utc)  # 45 min over

        slot = make_itinerary_slot()
        slot["endTime"] = end_time.isoformat()
        slot["status"] = "confirmed"

        result = await trigger.evaluate(slot, trip, now_utc=now)

        assert result.triggered is True
        assert result.payload["overrun_minutes"] == 45.0
        assert "end_time_local" in result.payload
        assert "overrun_seconds" in result.payload

    @pytest.mark.asyncio
    async def test_fires_for_confirmed_status(self):
        trigger = TimeOverrunTrigger()
        trip = _trip("UTC")

        end_time = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 2, 20, 11, 0, 0, tzinfo=timezone.utc)

        slot = make_itinerary_slot()
        slot["endTime"] = end_time.isoformat()
        slot["status"] = "confirmed"

        result = await trigger.evaluate(slot, trip, now_utc=now)

        assert result.triggered is True


# ---------------------------------------------------------------------------
# UserMoodTrigger tests
# ---------------------------------------------------------------------------

class TestUserMoodTrigger:
    @pytest.mark.asyncio
    async def test_fires_for_active_slot(self):
        trigger = UserMoodTrigger()
        slot = make_itinerary_slot()
        slot["status"] = "active"
        trip = _trip()

        result = await trigger.evaluate(
            slot, trip, user_id="user-123", mood_signal="not_feeling_it"
        )

        assert result.triggered is True
        assert result.trigger_type == "user_mood"
        assert result.payload["user_id"] == "user-123"
        assert result.payload["mood_signal"] == "not_feeling_it"

    @pytest.mark.asyncio
    async def test_fires_for_proposed_slot(self):
        trigger = UserMoodTrigger()
        slot = make_itinerary_slot()
        slot["status"] = "proposed"
        trip = _trip()

        result = await trigger.evaluate(slot, trip, user_id="u-abc")

        assert result.triggered is True

    @pytest.mark.asyncio
    async def test_does_not_fire_for_completed_slot(self):
        trigger = UserMoodTrigger()
        slot = make_itinerary_slot()
        slot["status"] = "completed"
        trip = _trip()

        result = await trigger.evaluate(slot, trip, user_id="u-abc")

        assert result.triggered is False
        assert "completed" in result.reason

    @pytest.mark.asyncio
    async def test_does_not_fire_for_skipped_slot(self):
        trigger = UserMoodTrigger()
        slot = make_itinerary_slot()
        slot["status"] = "skipped"
        trip = _trip()

        result = await trigger.evaluate(slot, trip, user_id="u-abc")

        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_payload_includes_slot_details(self):
        trigger = UserMoodTrigger()
        slot = make_itinerary_slot()
        slot["status"] = "confirmed"
        slot["slotType"] = "anchor"
        slot["activityNodeId"] = "node-999"
        trip = _trip()

        result = await trigger.evaluate(
            slot, trip, user_id="user-x", mood_signal="not_feeling_it"
        )

        assert result.triggered is True
        assert result.payload["slot_id"] == slot["id"]
        assert result.payload["slot_type"] == "anchor"
        assert result.payload["activity_node_id"] == "node-999"
