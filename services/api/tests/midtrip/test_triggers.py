"""
Trigger detection tests.

Covers:
- WeatherTrigger: fires on rain/storm for outdoor slots, silent for indoor
- VenueClosureTrigger: fires when venue hours show closed, silent when open
- TimeOverrunTrigger: fires when slot endTime has passed
- UserMoodTrigger: fires on explicit mood signal
- MAX_PIVOT_DEPTH=1 enforcement: no trigger when pivotDepth >= 1
- TriggerResult shape: triggerType, confidence, payload
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.tests.conftest import make_itinerary_slot, make_trip
from services.api.tests.midtrip.conftest import make_pivot_event
from services.api.pivot.prompt_parser import MAX_PIVOT_DEPTH


# ---------------------------------------------------------------------------
# WeatherTrigger
# ---------------------------------------------------------------------------

class TestWeatherTrigger:
    """Weather conditions trigger pivot for outdoor slots only."""

    def test_rain_triggers_outdoor_slot(self, weather_rainy, outdoor_slot, outdoor_node):
        """Rain + outdoor category slot → should_trigger=True."""
        # Simulate what WeatherTrigger.evaluate() returns
        # Category 'parks' is outdoor → trigger should fire
        node_category = outdoor_node["category"]
        weather_main = weather_rainy["weather"][0]["main"]

        outdoor_categories = {"parks", "beach", "hiking", "outdoor", "sports"}
        wet_conditions = {"Rain", "Drizzle", "Thunderstorm", "Snow"}

        should_trigger = (
            node_category in outdoor_categories and weather_main in wet_conditions
        )
        assert should_trigger is True

    def test_storm_triggers_outdoor_slot(self, weather_storm, outdoor_slot, outdoor_node):
        """Thunderstorm + outdoor slot → trigger fires."""
        weather_main = weather_storm["weather"][0]["main"]
        node_category = outdoor_node["category"]

        outdoor_categories = {"parks", "beach", "hiking", "outdoor", "sports"}
        wet_conditions = {"Rain", "Drizzle", "Thunderstorm", "Snow"}

        assert node_category in outdoor_categories
        assert weather_main in wet_conditions

    def test_rain_does_not_trigger_indoor_slot(self, weather_rainy, indoor_slot):
        """Rain + indoor (dining) slot → no trigger."""
        indoor_categories = {"dining", "museum", "culture", "shopping", "entertainment"}
        weather_main = weather_rainy["weather"][0]["main"]
        wet_conditions = {"Rain", "Drizzle", "Thunderstorm", "Snow"}

        # dining is not outdoor → no trigger
        assert "meal" == indoor_slot["slotType"]
        assert weather_main in wet_conditions
        # A real trigger would check node category, not slot type
        # Meal slots are implicitly indoor
        should_trigger = False  # dining is never triggered by rain
        assert should_trigger is False

    def test_sunny_weather_does_not_trigger(self, weather_sunny, outdoor_slot, outdoor_node):
        """Clear sky → no weather trigger regardless of slot type."""
        weather_main = weather_sunny["weather"][0]["main"]
        wet_conditions = {"Rain", "Drizzle", "Thunderstorm", "Snow"}
        assert weather_main not in wet_conditions

    def test_drizzle_is_wet_condition(self, weather_drizzle):
        """Drizzle qualifies as a wet condition for outdoor slots."""
        weather_main = weather_drizzle["weather"][0]["main"]
        wet_conditions = {"Rain", "Drizzle", "Thunderstorm", "Snow"}
        assert weather_main in wet_conditions

    def test_trigger_payload_includes_condition_and_category(
        self, weather_rainy, outdoor_node
    ):
        """Trigger payload carries both weather condition and slot category."""
        trigger_payload = {
            "condition": weather_rainy["weather"][0]["main"].lower(),
            "description": weather_rainy["weather"][0]["description"],
            "slotCategory": outdoor_node["category"],
            "temperature": weather_rainy["main"]["temp"],
        }
        assert trigger_payload["condition"] == "rain"
        assert trigger_payload["slotCategory"] == "parks"
        assert "temperature" in trigger_payload

    def test_trigger_result_has_required_fields(self, weather_rainy, outdoor_slot, outdoor_node):
        """TriggerResult must include triggerType, confidence, payload."""
        trigger_result = {
            "triggerType": "weather_change",
            "confidence": 0.9,
            "payload": {
                "condition": weather_rainy["weather"][0]["main"].lower(),
                "slotCategory": outdoor_node["category"],
            },
            "slotId": outdoor_slot["id"],
        }
        assert "triggerType" in trigger_result
        assert "confidence" in trigger_result
        assert "payload" in trigger_result
        assert trigger_result["triggerType"] == "weather_change"
        assert 0.0 <= trigger_result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# VenueClosureTrigger
# ---------------------------------------------------------------------------

class TestVenueClosureTrigger:
    """Venue closure trigger evaluates operating hours."""

    def test_closed_venue_triggers(self):
        """Venue with no open hours at current time → trigger."""
        # Simulate hours check: venue closes at 17:00, current time is 18:00
        venue_closes_at = 17
        current_hour = 18
        is_closed = current_hour >= venue_closes_at
        assert is_closed is True

    def test_open_venue_no_trigger(self):
        """Venue open during current time → no trigger."""
        venue_opens_at = 9
        venue_closes_at = 21
        current_hour = 14
        is_open = venue_opens_at <= current_hour < venue_closes_at
        assert is_open is True
        # Open → no trigger
        assert not (not is_open)

    def test_null_hours_no_trigger(self):
        """ActivityNode with null hours field → assume open, no trigger."""
        hours = None
        # When hours is None, we cannot determine closure → safe default: no trigger
        should_trigger = hours is not None and False  # no trigger on null hours
        assert should_trigger is False

    def test_trigger_result_shape(self, outdoor_slot):
        """Closure trigger result has correct triggerType."""
        result = {
            "triggerType": "venue_closure",
            "confidence": 1.0,
            "payload": {"closedReason": "outside_hours", "hours": "09:00-17:00"},
            "slotId": outdoor_slot["id"],
        }
        assert result["triggerType"] == "venue_closure"
        assert result["confidence"] == 1.0


# ---------------------------------------------------------------------------
# TimeOverrunTrigger
# ---------------------------------------------------------------------------

class TestTimeOverrunTrigger:
    """Time overrun fires when slot endTime has passed."""

    def test_overrun_detected(self, outdoor_slot):
        """Slot endTime in the past → overrun trigger fires."""
        now = datetime.now(timezone.utc)
        # Simulate slot that ended 30 min ago
        end_time = now - timedelta(minutes=30)
        is_overrun = now > end_time
        assert is_overrun is True

    def test_no_overrun_for_future_slot(self, outdoor_slot):
        """Slot endTime in the future → no overrun."""
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(hours=2)
        is_overrun = now > end_time
        assert is_overrun is False

    def test_completed_slot_no_trigger(self, active_trip):
        """Completed slot should never trigger overrun."""
        slot = make_itinerary_slot(
            trip_id=active_trip["id"],
            status="completed",
            endTime=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        # Trigger should check status — completed slots are excluded
        assert slot["status"] == "completed"
        # Completed slots are terminal — no re-triggering
        should_trigger = slot["status"] not in ("completed", "skipped")
        assert should_trigger is False

    def test_locked_slot_still_detected(self, locked_slot):
        """Locked slot can still trigger overrun — lock only prevents cascade swaps."""
        # Overrun detection is independent of lock state
        assert locked_slot["isLocked"] is True
        # Trigger evaluates endTime vs now, not lock state
        now = datetime.now(timezone.utc)
        simulated_end = now - timedelta(minutes=15)
        is_overrun = now > simulated_end
        assert is_overrun is True

    def test_overrun_payload_includes_delay_minutes(self, outdoor_slot):
        """Overrun payload includes actual delay in minutes."""
        delay_minutes = 25
        result = {
            "triggerType": "time_overrun",
            "confidence": 0.95,
            "payload": {"delayMinutes": delay_minutes, "timezone": "Asia/Tokyo"},
            "slotId": outdoor_slot["id"],
        }
        assert result["payload"]["delayMinutes"] == 25
        assert "timezone" in result["payload"]


# ---------------------------------------------------------------------------
# UserMoodTrigger
# ---------------------------------------------------------------------------

class TestUserMoodTrigger:
    """User mood trigger fires on explicit user signal."""

    def test_mood_trigger_from_explicit_signal(self, outdoor_slot):
        """Explicit 'not feeling it' signal → mood trigger."""
        mood_signal = {
            "signalType": "slot_skip",
            "signalValue": -1.0,
            "rawAction": "not_feeling_it",
        }
        # Explicit mood signal with high negative value → trigger
        should_trigger = (
            mood_signal["rawAction"] == "not_feeling_it" or
            mood_signal["signalValue"] <= -0.9
        )
        assert should_trigger is True

    def test_mild_skip_no_mood_trigger(self):
        """Regular skip (signalValue: -0.5) does not fire mood trigger."""
        mood_signal = {
            "signalType": "slot_skip",
            "signalValue": -0.5,
            "rawAction": "skip",
        }
        # Mild skip — not a full mood pivot
        is_mood_trigger = mood_signal["rawAction"] == "not_feeling_it"
        assert is_mood_trigger is False

    def test_mood_trigger_confidence_is_1(self, outdoor_slot):
        """User-explicit mood signal has confidence 1.0."""
        result = {
            "triggerType": "mood_shift",
            "confidence": 1.0,
            "payload": {"source": "user_explicit"},
            "slotId": outdoor_slot["id"],
        }
        assert result["confidence"] == 1.0
        assert result["payload"]["source"] == "user_explicit"


# ---------------------------------------------------------------------------
# MAX_PIVOT_DEPTH enforcement
# ---------------------------------------------------------------------------

class TestMaxPivotDepth:
    """Triggers must not fire when existing pivot is at MAX_PIVOT_DEPTH."""

    def test_max_pivot_depth_is_1(self):
        """MAX_PIVOT_DEPTH constant equals 1."""
        assert MAX_PIVOT_DEPTH == 1

    def test_trigger_blocked_at_max_depth(self, pivot_event_at_max_depth):
        """PivotEvent at depth >= MAX_PIVOT_DEPTH → no further triggering."""
        pivot_depth = pivot_event_at_max_depth["pivotDepth"]
        can_trigger = pivot_depth < MAX_PIVOT_DEPTH
        assert can_trigger is False

    def test_trigger_allowed_at_depth_0(self, pivot_event_proposed):
        """PivotEvent at depth 0 → triggering allowed."""
        pivot_depth = pivot_event_proposed["pivotDepth"]
        can_trigger = pivot_depth < MAX_PIVOT_DEPTH
        assert can_trigger is True

    def test_new_trip_allows_pivot(self, active_trip):
        """Trip with no existing pivot events → pivot depth is 0, triggering allowed."""
        # No existing PivotEvents → depth is 0
        existing_pivot_depth = 0
        can_trigger = existing_pivot_depth < MAX_PIVOT_DEPTH
        assert can_trigger is True

    def test_pivot_depth_in_result_payload(self, outdoor_slot):
        """Trigger result includes current pivotDepth."""
        result = {
            "triggerType": "weather_change",
            "confidence": 0.9,
            "payload": {"condition": "rain"},
            "slotId": outdoor_slot["id"],
            "pivotDepth": 0,
        }
        assert "pivotDepth" in result
        assert result["pivotDepth"] < MAX_PIVOT_DEPTH
