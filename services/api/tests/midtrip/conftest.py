"""
Mid-trip test fixtures.

Provides:
- active_trip: Trip in 'active' status with today as startDate
- weather_data: Canonical weather payload shapes for sunny / rainy / storm
- pivot_event_proposed: A PivotEvent in proposed status
- outdoor_slot: An ItinerarySlot for an outdoor activity (category: parks)
- indoor_slot: An ItinerarySlot for an indoor activity (category: dining)
- locked_slot: An ItinerarySlot with isLocked=True
- slot_sequence: Four ordered slots on day 1 for cascade testing
- mock_anthropic: Pre-configured AsyncAnthropic mock for Haiku tests
- prompt_parser: PromptParser instance backed by mock_anthropic + mock_db
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Trip fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def active_user() -> dict:
    """User currently on a trip."""
    return make_user(systemRole="user", subscriptionTier="beta")


@pytest.fixture
def active_trip(active_user: dict) -> dict:
    """Trip with status='active', start=today, end=7 days out."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=active_user["id"],
        status="active",
        destination="Tokyo, Japan",
        city="Tokyo",
        country="Japan",
        timezone="Asia/Tokyo",
        startDate=now,
        endDate=now + timedelta(days=6),
        activatedAt=now,
    )


@pytest.fixture
def trip_id(active_trip: dict) -> str:
    return active_trip["id"]


@pytest.fixture
def user_id(active_user: dict) -> str:
    return active_user["id"]


# ---------------------------------------------------------------------------
# Weather data fixtures
# ---------------------------------------------------------------------------

def _owm_payload(weather_id: int, main: str, description: str, temp: float) -> dict:
    """Minimal OpenWeatherMap /weather response payload."""
    return {
        "weather": [{"id": weather_id, "main": main, "description": description}],
        "main": {"temp": temp, "feels_like": temp - 2, "humidity": 75},
        "wind": {"speed": 3.5},
        "dt": int(datetime.now(timezone.utc).timestamp()),
        "name": "Tokyo",
    }


@pytest.fixture
def weather_sunny() -> dict:
    return _owm_payload(800, "Clear", "clear sky", 22.0)


@pytest.fixture
def weather_rainy() -> dict:
    return _owm_payload(500, "Rain", "light rain", 16.0)


@pytest.fixture
def weather_storm() -> dict:
    return _owm_payload(212, "Thunderstorm", "heavy thunderstorm", 14.0)


@pytest.fixture
def weather_drizzle() -> dict:
    return _owm_payload(300, "Drizzle", "light intensity drizzle", 18.0)


# ---------------------------------------------------------------------------
# Slot fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def outdoor_slot(active_trip: dict) -> dict:
    """Outdoor activity slot — parks category, day 1."""
    return make_itinerary_slot(
        trip_id=active_trip["id"],
        dayNumber=1,
        sortOrder=0,
        slotType="anchor",
        status="proposed",
        startTime=datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0),
        endTime=datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0),
        durationMinutes=120,
        isLocked=False,
    )


@pytest.fixture
def indoor_slot(active_trip: dict) -> dict:
    """Indoor activity slot — dining category, day 1."""
    return make_itinerary_slot(
        trip_id=active_trip["id"],
        dayNumber=1,
        sortOrder=1,
        slotType="meal",
        status="proposed",
        startTime=datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0),
        endTime=datetime.now(timezone.utc).replace(hour=14, minute=30, second=0, microsecond=0),
        durationMinutes=90,
        isLocked=False,
    )


@pytest.fixture
def locked_slot(active_trip: dict) -> dict:
    """Locked slot — should never be displaced by cascade."""
    return make_itinerary_slot(
        trip_id=active_trip["id"],
        dayNumber=1,
        sortOrder=2,
        slotType="anchor",
        status="confirmed",
        isLocked=True,
        durationMinutes=60,
    )


@pytest.fixture
def slot_sequence(active_trip: dict) -> list[dict]:
    """Four ordered slots on day 1 for cascade testing.

    [0] anchor  09:00-11:00  sortOrder=0
    [1] meal    12:00-13:00  sortOrder=1
    [2] flex    14:00-15:00  sortOrder=2
    [3] anchor  16:00-18:00  sortOrder=3  (locked)
    """
    base_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def _slot(sort_order: int, hour_start: int, hour_end: int, slot_type: str, locked: bool = False) -> dict:
        return make_itinerary_slot(
            trip_id=active_trip["id"],
            dayNumber=1,
            sortOrder=sort_order,
            slotType=slot_type,
            status="confirmed" if locked else "proposed",
            startTime=base_date + timedelta(hours=hour_start),
            endTime=base_date + timedelta(hours=hour_end),
            durationMinutes=(hour_end - hour_start) * 60,
            isLocked=locked,
        )

    return [
        _slot(0, 9, 11, "anchor"),
        _slot(1, 12, 13, "meal"),
        _slot(2, 14, 15, "flex"),
        _slot(3, 16, 18, "anchor", locked=True),
    ]


@pytest.fixture
def day2_slot(active_trip: dict) -> dict:
    """Slot on day 2 — should NOT be affected by day 1 cascade."""
    return make_itinerary_slot(
        trip_id=active_trip["id"],
        dayNumber=2,
        sortOrder=0,
        slotType="anchor",
        status="proposed",
        durationMinutes=90,
    )


# ---------------------------------------------------------------------------
# Activity node fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def outdoor_node() -> dict:
    """ActivityNode for outdoor activity (parks)."""
    return make_activity_node(
        name="Shinjuku Gyoen",
        slug="shinjuku-gyoen",
        city="Tokyo",
        country="Japan",
        category="parks",
        latitude=35.6851,
        longitude=139.7100,
        status="active",
    )


@pytest.fixture
def nearby_node() -> dict:
    """ActivityNode within 200m of a transit path."""
    return make_activity_node(
        name="Nearby Coffee",
        slug="nearby-coffee",
        city="Tokyo",
        country="Japan",
        category="dining",
        # ~150m from Shinjuku Gyoen main gate
        latitude=35.6866,
        longitude=139.7112,
        status="active",
    )


@pytest.fixture
def far_node() -> dict:
    """ActivityNode >200m away — should not appear in proximity results."""
    return make_activity_node(
        name="Far Museum",
        slug="far-museum",
        city="Tokyo",
        country="Japan",
        category="culture",
        # ~800m away
        latitude=35.6925,
        longitude=139.7025,
        status="active",
    )


# ---------------------------------------------------------------------------
# PivotEvent fixture
# ---------------------------------------------------------------------------

def make_pivot_event(
    trip_id: str | None = None,
    slot_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Factory for PivotEvent records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": str(uuid.uuid4()),
        "tripId": trip_id or str(uuid.uuid4()),
        "slotId": slot_id or str(uuid.uuid4()),
        "triggerType": "weather_change",
        "triggerPayload": {"condition": "rain", "slotCategory": "parks"},
        "status": "proposed",
        "alternatives": [],
        "pivotDepth": 0,
        "responseTimeMs": None,
        "resolvedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    base.update(overrides)
    return base


@pytest.fixture
def pivot_event_proposed(active_trip: dict, outdoor_slot: dict) -> dict:
    """PivotEvent in proposed state for the outdoor slot."""
    return make_pivot_event(
        trip_id=active_trip["id"],
        slot_id=outdoor_slot["id"],
        triggerType="weather_change",
        status="proposed",
        pivotDepth=0,
    )


@pytest.fixture
def pivot_event_at_max_depth(active_trip: dict, outdoor_slot: dict) -> dict:
    """PivotEvent already at MAX_PIVOT_DEPTH=1."""
    return make_pivot_event(
        trip_id=active_trip["id"],
        slot_id=outdoor_slot["id"],
        triggerType="weather_change",
        status="proposed",
        pivotDepth=1,  # at limit
    )


# ---------------------------------------------------------------------------
# Anthropic / PromptParser fixtures
# ---------------------------------------------------------------------------

def _make_haiku_response(content_text: str) -> MagicMock:
    """Build a mock anthropic Messages response with given text content."""
    content_block = MagicMock()
    content_block.text = content_text

    response = MagicMock()
    response.content = [content_block]
    response.usage = MagicMock(input_tokens=50, output_tokens=20)
    return response


@pytest.fixture
def mock_anthropic_haiku_weather() -> MagicMock:
    """Haiku returns weather_change classification."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_haiku_response(
            json.dumps({
                "classification": "weather_change",
                "confidence": 0.92,
                "entities": {"location": None, "time": None, "activity_type": "outdoor"},
            })
        )
    )
    return client


@pytest.fixture
def mock_anthropic_haiku_mood() -> MagicMock:
    """Haiku returns mood_shift classification."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_haiku_response(
            json.dumps({
                "classification": "mood_shift",
                "confidence": 0.78,
                "entities": {"location": None, "time": None, "activity_type": None},
            })
        )
    )
    return client


@pytest.fixture
def mock_anthropic_timeout() -> MagicMock:
    """Haiku call times out."""
    import asyncio

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())
    return client


@pytest.fixture
def mock_anthropic_bad_json() -> MagicMock:
    """Haiku returns invalid JSON."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_haiku_response("I cannot help with that request.")
    )
    return client


@pytest.fixture
def mock_anthropic_unknown_classification() -> MagicMock:
    """Haiku returns a classification not in VALID_CLASSIFICATIONS."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_make_haiku_response(
            json.dumps({
                "classification": "food_poisoning",
                "confidence": 0.99,
                "entities": {},
            })
        )
    )
    return client


@pytest.fixture
def mock_db_for_prompt() -> AsyncMock:
    """Minimal mock DB for PromptParser audit logging."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture
def prompt_parser_haiku_weather(mock_anthropic_haiku_weather, mock_db_for_prompt):
    """PromptParser configured with weather-returning Haiku mock."""
    from services.api.pivot.prompt_parser import PromptParser
    return PromptParser(
        anthropic_client=mock_anthropic_haiku_weather,
        db=mock_db_for_prompt,
    )


@pytest.fixture
def prompt_parser_timeout(mock_anthropic_timeout, mock_db_for_prompt):
    """PromptParser where Haiku always times out."""
    from services.api.pivot.prompt_parser import PromptParser
    return PromptParser(
        anthropic_client=mock_anthropic_timeout,
        db=mock_db_for_prompt,
    )


@pytest.fixture
def prompt_parser_bad_json(mock_anthropic_bad_json, mock_db_for_prompt):
    """PromptParser where Haiku returns non-JSON."""
    from services.api.pivot.prompt_parser import PromptParser
    return PromptParser(
        anthropic_client=mock_anthropic_bad_json,
        db=mock_db_for_prompt,
    )
