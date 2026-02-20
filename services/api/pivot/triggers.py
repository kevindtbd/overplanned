"""
Pivot trigger implementations.

Each trigger is a pure, stateless callable that inspects a slot + its context
and returns a TriggerResult indicating whether a pivot is warranted and why.

Design principles:
  - Triggers do NOT write to the database — PivotDetector owns all DB writes.
  - Triggers do NOT call external services directly — dependencies are injected.
  - Each trigger is independently testable with no external side effects.
  - Timezone-awareness is mandatory: all datetime comparisons use Trip.timezone.

Trigger registry (mirrors PivotTrigger enum):
  weather_change  -> WeatherTrigger
  venue_closed    -> VenueClosureTrigger
  time_overrun    -> TimeOverrunTrigger
  user_mood       -> UserMoodTrigger
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TriggerResult — returned by every trigger
# ---------------------------------------------------------------------------

@dataclass
class TriggerResult:
    """
    Outcome of evaluating a single pivot trigger against a slot.

    Attributes:
        triggered:    True if this trigger recommends a pivot.
        trigger_type: String matching PivotTrigger enum value.
        payload:      Structured evidence for the trigger (stored in PivotEvent.triggerPayload).
        reason:       Human-readable explanation (for logging / debug).
    """

    triggered: bool
    trigger_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @classmethod
    def no_trigger(cls, trigger_type: str, reason: str = "") -> "TriggerResult":
        return cls(triggered=False, trigger_type=trigger_type, reason=reason)

    @classmethod
    def fired(
        cls, trigger_type: str, payload: dict[str, Any], reason: str = ""
    ) -> "TriggerResult":
        return cls(triggered=True, trigger_type=trigger_type, payload=payload, reason=reason)


# ---------------------------------------------------------------------------
# WeatherTrigger
# ---------------------------------------------------------------------------

class WeatherTrigger:
    """
    Fires when the current weather poses a meaningful risk to an outdoor slot.

    Conditions:
      - Slot category is in _OUTDOOR_CATEGORIES (outdoors, active)
      - WeatherService reports rain, drizzle, or storm for the trip city

    Dependencies injected:
      - weather_service: WeatherService instance (has should_trigger_weather_pivot())
    """

    TRIGGER_TYPE = "weather_change"
    _OUTDOOR_CATEGORIES = {"outdoors", "active"}

    def __init__(self, weather_service) -> None:
        self._weather = weather_service

    async def evaluate(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        weather_summary: dict[str, Any] | None = None,
    ) -> TriggerResult:
        """
        Evaluate a weather trigger for a given slot.

        Args:
            slot:            ItinerarySlot record dict.
            trip:            Trip record dict (needs city, timezone).
            weather_summary: Pre-fetched weather dict from WeatherService.get_weather()
                             to avoid redundant API calls per slot.

        Returns:
            TriggerResult
        """
        category = slot.get("category") or slot.get("slotType", "")

        if not self._weather.is_outdoor_slot(category):
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Category '{category}' is not weather-sensitive",
            )

        if weather_summary is None:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason="No weather data available",
            )

        should_pivot = self._weather.should_trigger_weather_pivot(weather_summary, category)
        if not should_pivot:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Weather condition '{weather_summary.get('condition')}' not severe for outdoor slot",
            )

        payload = {
            "condition": weather_summary.get("condition"),
            "code": weather_summary.get("code"),
            "temp_c": weather_summary.get("temp_c"),
            "city": trip.get("city"),
            "slot_category": category,
        }
        return TriggerResult.fired(
            self.TRIGGER_TYPE,
            payload=payload,
            reason=(
                f"Outdoor slot (category={category}) during "
                f"{weather_summary.get('condition')} (code={weather_summary.get('code')})"
            ),
        )


# ---------------------------------------------------------------------------
# VenueClosureTrigger
# ---------------------------------------------------------------------------

def _parse_hours_range(hours_str: str) -> tuple[int, int] | None:
    """
    Parse a simple 'HH:MM-HH:MM' hours string into (open_minute, close_minute)
    offsets from midnight.

    Returns None if the string cannot be parsed.

    Examples:
        '09:00-22:00' -> (540, 1320)
        '00:00-00:00' -> None  (ambiguous — treat as unknown)
    """
    try:
        parts = hours_str.strip().split("-")
        if len(parts) != 2:
            return None
        open_h, open_m = map(int, parts[0].split(":"))
        close_h, close_m = map(int, parts[1].split(":"))
        open_minutes = open_h * 60 + open_m
        close_minutes = close_h * 60 + close_m
        if open_minutes == close_minutes:
            return None  # ambiguous
        return (open_minutes, close_minutes)
    except (ValueError, AttributeError):
        return None


class VenueClosureTrigger:
    """
    Fires when a venue is closed at the scheduled slot start time.

    Data source: ActivityNode.hours JSON field from Postgres.
    Hours format expected: {"monday": "09:00-22:00", "tuesday": "09:00-22:00", ...}

    Timezone awareness: uses Trip.timezone for local-time comparison.

    If hours data is absent or unparseable, trigger does NOT fire (safe default).
    """

    TRIGGER_TYPE = "venue_closed"
    _DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    async def evaluate(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        now_utc: datetime | None = None,
    ) -> TriggerResult:
        """
        Args:
            slot:    ItinerarySlot dict (needs startTime, activityNode with hours).
            trip:    Trip dict (needs timezone).
            now_utc: Override current time (for testing). Defaults to datetime.now(UTC).
        """
        activity_node = slot.get("activityNode") or {}
        hours_data: dict[str, str] | None = activity_node.get("hours")

        if not hours_data:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason="No hours data available for venue",
            )

        trip_tz_str = trip.get("timezone", "UTC")
        try:
            trip_tz = ZoneInfo(trip_tz_str)
        except Exception:
            logger.warning("Invalid timezone %r for trip %s, defaulting to UTC", trip_tz_str, trip.get("id"))
            trip_tz = ZoneInfo("UTC")

        now = (now_utc or datetime.now(timezone.utc)).astimezone(trip_tz)

        # Use slot startTime if available, else fall back to now
        slot_start_raw = slot.get("startTime")
        if slot_start_raw:
            if isinstance(slot_start_raw, str):
                try:
                    slot_time = datetime.fromisoformat(slot_start_raw).astimezone(trip_tz)
                except ValueError:
                    slot_time = now
            elif isinstance(slot_start_raw, datetime):
                slot_time = slot_start_raw.astimezone(trip_tz)
            else:
                slot_time = now
        else:
            slot_time = now

        day_name = self._DAY_NAMES[slot_time.weekday()]
        day_hours = hours_data.get(day_name)

        if not day_hours:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"No hours for {day_name}",
            )

        parsed = _parse_hours_range(day_hours)
        if parsed is None:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Could not parse hours string: {day_hours!r}",
            )

        open_minutes, close_minutes = parsed
        current_minutes = slot_time.hour * 60 + slot_time.minute

        is_open = open_minutes <= current_minutes < close_minutes
        if is_open:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Venue open at {slot_time.strftime('%H:%M')} ({day_name})",
            )

        payload = {
            "day": day_name,
            "hours": day_hours,
            "slot_time_local": slot_time.strftime("%H:%M"),
            "timezone": trip_tz_str,
            "venue_name": activity_node.get("name"),
            "google_place_id": activity_node.get("googlePlaceId"),
        }
        return TriggerResult.fired(
            self.TRIGGER_TYPE,
            payload=payload,
            reason=(
                f"Venue '{activity_node.get('name')}' closed at "
                f"{slot_time.strftime('%H:%M')} {trip_tz_str} ({day_name}: {day_hours})"
            ),
        )


# ---------------------------------------------------------------------------
# TimeOverrunTrigger
# ---------------------------------------------------------------------------

class TimeOverrunTrigger:
    """
    Fires when a slot's scheduled end time has passed but the slot is still active.

    Logic:
      - Slot must have an endTime set
      - Current time (in Trip.timezone) must be past endTime
      - Slot status must be 'active' or 'confirmed' (not already completed/skipped)

    This catch allows the system to suggest dropping or replacing a slot
    that has run over, freeing time for the next item.
    """

    TRIGGER_TYPE = "time_overrun"
    _ACTIVE_STATUSES = {"active", "confirmed"}

    async def evaluate(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        now_utc: datetime | None = None,
    ) -> TriggerResult:
        """
        Args:
            slot:    ItinerarySlot dict (needs endTime, status).
            trip:    Trip dict (needs timezone).
            now_utc: Override for current time (testing).
        """
        slot_status = slot.get("status", "")
        if slot_status not in self._ACTIVE_STATUSES:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Slot status '{slot_status}' is not active/confirmed",
            )

        end_time_raw = slot.get("endTime")
        if not end_time_raw:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason="Slot has no endTime set",
            )

        # Parse endTime
        if isinstance(end_time_raw, str):
            try:
                end_time = datetime.fromisoformat(end_time_raw)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
            except ValueError:
                return TriggerResult.no_trigger(
                    self.TRIGGER_TYPE,
                    reason=f"Could not parse endTime: {end_time_raw!r}",
                )
        elif isinstance(end_time_raw, datetime):
            end_time = end_time_raw
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
        else:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason="endTime is not a parseable type",
            )

        now = now_utc or datetime.now(timezone.utc)
        overrun_seconds = (now - end_time).total_seconds()

        if overrun_seconds <= 0:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Slot ends in {abs(overrun_seconds):.0f}s — not overrun",
            )

        trip_tz_str = trip.get("timezone", "UTC")
        try:
            trip_tz = ZoneInfo(trip_tz_str)
        except Exception:
            trip_tz = ZoneInfo("UTC")

        payload = {
            "slot_id": slot.get("id"),
            "end_time_utc": end_time.isoformat(),
            "now_utc": now.isoformat(),
            "overrun_seconds": int(overrun_seconds),
            "overrun_minutes": round(overrun_seconds / 60, 1),
            "timezone": trip_tz_str,
            "end_time_local": end_time.astimezone(trip_tz).strftime("%H:%M"),
        }
        return TriggerResult.fired(
            self.TRIGGER_TYPE,
            payload=payload,
            reason=f"Slot overran by {overrun_seconds / 60:.1f} minutes",
        )


# ---------------------------------------------------------------------------
# UserMoodTrigger
# ---------------------------------------------------------------------------

class UserMoodTrigger:
    """
    Fires when the user explicitly signals they are not feeling the current slot.

    This trigger is always explicitly user-initiated — it carries no ambiguity.
    The caller (API handler) validates the user signal and passes it in.

    Unlike other triggers, UserMoodTrigger does not need to inspect time or
    external data; it wraps the signal for uniform handling in PivotDetector.
    """

    TRIGGER_TYPE = "user_mood"

    async def evaluate(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        user_id: str = "",
        mood_signal: str = "not_feeling_it",
    ) -> TriggerResult:
        """
        Args:
            slot:         ItinerarySlot dict.
            trip:         Trip dict.
            user_id:      ID of the user who sent the signal.
            mood_signal:  Signal label (default: 'not_feeling_it').
        """
        # Slot must not already be completed or skipped
        slot_status = slot.get("status", "")
        if slot_status in {"completed", "skipped"}:
            return TriggerResult.no_trigger(
                self.TRIGGER_TYPE,
                reason=f"Slot already {slot_status} — mood signal ignored",
            )

        payload = {
            "user_id": user_id,
            "mood_signal": mood_signal,
            "slot_id": slot.get("id"),
            "slot_type": slot.get("slotType"),
            "activity_node_id": slot.get("activityNodeId"),
        }
        return TriggerResult.fired(
            self.TRIGGER_TYPE,
            payload=payload,
            reason=f"User '{user_id}' signalled '{mood_signal}' for slot {slot.get('id')}",
        )
