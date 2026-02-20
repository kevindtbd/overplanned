"""
Post-trip test fixtures.

Provides:
- completed_trip: Trip in 'completed' status with timezone-aware endDate in the past
- completed_user: User who completed the trip
- tokyo_trip / london_trip / honolulu_trip: Timezone-diverse trips for tz-aware tests
- reflection_slots: Slots with mixed statuses (completed, skipped, proposed)
- skip_signal: BehavioralSignal with signalType=post_skipped for disambiguation
- mock_redis_posttrip: Redis mock with sorted-set support for push/email queues
- mock_qdrant_posttrip: Qdrant mock returning destination suggestions
- loved_activities: ActivityNodes + post_loved signals for highlight computation
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
# ID helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def completed_user() -> dict:
    """User who just completed a trip."""
    return make_user(
        name="Post Trip Tester",
        email="posttrip-test@example.com",
        subscriptionTier="beta",
    )


@pytest.fixture
def second_user() -> dict:
    """Second user for isolation tests."""
    return make_user(
        name="Other Traveler",
        email="other@example.com",
        subscriptionTier="beta",
    )


# ---------------------------------------------------------------------------
# Trip fixtures — timezone diversity
# ---------------------------------------------------------------------------

@pytest.fixture
def completed_trip(completed_user: dict) -> dict:
    """Trip in Tokyo, completed yesterday."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
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


@pytest.fixture
def tokyo_trip(completed_user: dict) -> dict:
    """Trip with Asia/Tokyo timezone — UTC+9. endDate just passed in JST."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="Tokyo, Japan",
        city="Tokyo",
        country="Japan",
        timezone="Asia/Tokyo",
        startDate=now - timedelta(days=7),
        endDate=now - timedelta(hours=10),  # ended 10h ago UTC
        activatedAt=now - timedelta(days=7),
    )


@pytest.fixture
def london_trip(completed_user: dict) -> dict:
    """Trip with Europe/London timezone — UTC+0/+1 depending on DST."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="London, UK",
        city="London",
        country="United Kingdom",
        timezone="Europe/London",
        startDate=now - timedelta(days=7),
        endDate=now - timedelta(hours=1),
        activatedAt=now - timedelta(days=7),
    )


@pytest.fixture
def honolulu_trip(completed_user: dict) -> dict:
    """Trip with Pacific/Honolulu timezone — UTC-10. endDate not yet passed there."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="Honolulu, USA",
        city="Honolulu",
        country="United States",
        timezone="Pacific/Honolulu",
        startDate=now - timedelta(days=7),
        endDate=now + timedelta(hours=8),  # 8h from now UTC = still afternoon in Honolulu
        activatedAt=now - timedelta(days=7),
    )


@pytest.fixture
def future_trip(completed_user: dict) -> dict:
    """Trip that hasn't ended yet (endDate in the future)."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="Barcelona, Spain",
        city="Barcelona",
        country="Spain",
        timezone="Europe/Madrid",
        startDate=now - timedelta(days=2),
        endDate=now + timedelta(days=5),
        activatedAt=now - timedelta(days=2),
    )


@pytest.fixture
def trip_no_timezone(completed_user: dict) -> dict:
    """Trip missing timezone — should not auto-complete."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="Somewhere",
        city="Somewhere",
        country="Unknown",
        timezone=None,
        startDate=now - timedelta(days=7),
        endDate=now - timedelta(days=1),
    )


@pytest.fixture
def trip_no_enddate(completed_user: dict) -> dict:
    """Trip missing endDate — should not auto-complete."""
    now = datetime.now(timezone.utc)
    return make_trip(
        user_id=completed_user["id"],
        status="active",
        destination="Somewhere",
        city="Somewhere",
        country="Unknown",
        timezone="America/New_York",
        startDate=now - timedelta(days=7),
        endDate=None,
    )


# ---------------------------------------------------------------------------
# Slot fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reflection_slots(completed_trip: dict) -> list[dict]:
    """Mixed status slots for post-trip reflection.

    [0] completed — sushi restaurant (loved)
    [1] completed — temple visit
    [2] skipped   — park visit
    [3] proposed  — never confirmed (ignored)
    """
    trip_id = completed_trip["id"]
    return [
        make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=1,
            sortOrder=0,
            slotType="meal",
            status="completed",
            durationMinutes=90,
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=1,
            sortOrder=1,
            slotType="anchor",
            status="completed",
            durationMinutes=120,
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=2,
            sortOrder=0,
            slotType="anchor",
            status="skipped",
            durationMinutes=60,
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=2,
            sortOrder=1,
            slotType="flex",
            status="proposed",
            durationMinutes=45,
        ),
    ]


@pytest.fixture
def slot_completed_to_skipped(completed_trip: dict) -> dict:
    """A slot initially completed that the user wants to override to skipped."""
    return make_itinerary_slot(
        trip_id=completed_trip["id"],
        dayNumber=1,
        sortOrder=2,
        slotType="anchor",
        status="completed",
        durationMinutes=120,
    )


# ---------------------------------------------------------------------------
# Activity node fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loved_activities() -> list[dict]:
    """Activities the user loved — for highlight computation and suggestions."""
    return [
        make_activity_node(
            name="Tsukiji Outer Market",
            slug="tsukiji-outer-market",
            city="Tokyo",
            country="Japan",
            category="dining",
            primaryImageUrl="https://images.unsplash.com/tsukiji.jpg",
        ),
        make_activity_node(
            name="Senso-ji Temple",
            slug="sensoji-temple",
            city="Tokyo",
            country="Japan",
            category="culture",
            primaryImageUrl="https://images.unsplash.com/sensoji.jpg",
        ),
        make_activity_node(
            name="Shinjuku Gyoen",
            slug="shinjuku-gyoen",
            city="Tokyo",
            country="Japan",
            category="parks",
            primaryImageUrl=None,
        ),
    ]


@pytest.fixture
def skipped_activity() -> dict:
    """Activity that was skipped — for disambiguation."""
    return make_activity_node(
        name="Meiji Shrine",
        slug="meiji-shrine",
        city="Tokyo",
        country="Japan",
        category="outdoors",
    )


# ---------------------------------------------------------------------------
# Signal fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def skip_signal(completed_user: dict, completed_trip: dict, skipped_activity: dict) -> dict:
    """BehavioralSignal for a skipped slot — input for disambiguation."""
    return make_behavioral_signal(
        user_id=completed_user["id"],
        tripId=completed_trip["id"],
        activityNodeId=skipped_activity["id"],
        signalType="post_skipped",
        signalValue=-1.0,
        tripPhase="post_trip",
        rawAction="slot_skipped",
    )


@pytest.fixture
def loved_signals(completed_user: dict, completed_trip: dict, loved_activities: list[dict]) -> list[dict]:
    """post_loved signals for the loved activities."""
    return [
        make_behavioral_signal(
            user_id=completed_user["id"],
            tripId=completed_trip["id"],
            activityNodeId=act["id"],
            signalType="post_loved",
            signalValue=1.0,
            tripPhase="post_trip",
            rawAction="post_loved",
        )
        for act in loved_activities[:2]  # only first two loved
    ]


@pytest.fixture
def explicit_intention(
    completed_user: dict, skip_signal: dict
) -> dict:
    """Explicit user-provided intention for a skip (source=user_explicit)."""
    return make_intention_signal(
        behavioral_signal_id=skip_signal["id"],
        user_id=completed_user["id"],
        intentionType="not_interested",
        confidence=1.0,
        source="user_explicit",
        userProvided=True,
    )


@pytest.fixture
def pivot_signal_from_midtrip(
    completed_user: dict, completed_trip: dict
) -> dict:
    """A pivot_accepted signal from Track 5 (mid-trip) for cross-track visibility."""
    return make_behavioral_signal(
        user_id=completed_user["id"],
        tripId=completed_trip["id"],
        signalType="pivot_accepted",
        signalValue=1.0,
        tripPhase="mid_trip",
        rawAction="pivot_accept",
        weatherContext={"condition": "rain", "temp": 16.0},
    )


# ---------------------------------------------------------------------------
# Mock Redis — sorted set support for push/email queues
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis_posttrip():
    """Redis mock with sorted-set (ZADD/ZRANGEBYSCORE/ZREM) + hash support."""
    redis = AsyncMock()
    _store: dict[str, Any] = {}
    _sorted_sets: dict[str, dict[str, float]] = {}

    async def _zadd(key: str, mapping: dict[str, float]) -> int:
        if key not in _sorted_sets:
            _sorted_sets[key] = {}
        _sorted_sets[key].update(mapping)
        return len(mapping)

    async def _zrangebyscore(
        key: str, min_score: str, max_score, start: int = 0, num: int = 100
    ) -> list[str]:
        if key not in _sorted_sets:
            return []
        max_val = float(max_score) if max_score != "+inf" else float("inf")
        items = [
            (member, score)
            for member, score in _sorted_sets[key].items()
            if score <= max_val
        ]
        items.sort(key=lambda x: x[1])
        return [member for member, _ in items[start:start + num]]

    async def _zrem(key: str, member: str) -> int:
        if key in _sorted_sets and member in _sorted_sets[key]:
            del _sorted_sets[key][member]
            return 1
        return 0

    async def _exists(key: str) -> bool:
        return key in _store

    async def _get(key: str):
        return _store.get(key)

    async def _setex(key: str, ttl: int, value: str):
        _store[key] = value

    async def _delete(key: str):
        _store.pop(key, None)

    redis.zadd = AsyncMock(side_effect=_zadd)
    redis.zrangebyscore = AsyncMock(side_effect=_zrangebyscore)
    redis.zrem = AsyncMock(side_effect=_zrem)
    redis.exists = AsyncMock(side_effect=_exists)
    redis.get = AsyncMock(side_effect=_get)
    redis.setex = AsyncMock(side_effect=_setex)
    redis.delete = AsyncMock(side_effect=_delete)
    redis.ping = AsyncMock()

    # Pipeline support for consume_login_link
    async def _pipe_execute():
        return [None, 0]

    pipe = AsyncMock()
    pipe.get = MagicMock()
    pipe.delete = MagicMock()
    pipe.execute = AsyncMock(side_effect=_pipe_execute)
    redis.pipeline = MagicMock(return_value=pipe)

    # Expose internals for assertions
    redis._store = _store
    redis._sorted_sets = _sorted_sets

    return redis


# ---------------------------------------------------------------------------
# Mock Qdrant — destination suggestion search results
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_qdrant_posttrip():
    """Qdrant mock that returns destination suggestion results."""
    qdrant = AsyncMock()

    mock_client = AsyncMock()
    qdrant._get_client = AsyncMock(return_value=mock_client)

    # Default: return Kyoto-based results
    mock_hit_1 = MagicMock()
    mock_hit_1.score = 0.85
    mock_hit_1.payload = {
        "name": "Fushimi Inari",
        "city": "Kyoto",
        "country": "Japan",
        "category": "culture",
        "is_canonical": True,
    }

    mock_hit_2 = MagicMock()
    mock_hit_2.score = 0.78
    mock_hit_2.payload = {
        "name": "Arashiyama Bamboo Grove",
        "city": "Kyoto",
        "country": "Japan",
        "category": "parks",
        "is_canonical": True,
    }

    mock_hit_3 = MagicMock()
    mock_hit_3.score = 0.72
    mock_hit_3.payload = {
        "name": "Nishiki Market",
        "city": "Kyoto",
        "country": "Japan",
        "category": "dining",
        "is_canonical": True,
    }

    mock_client.search = AsyncMock(return_value=[mock_hit_1, mock_hit_2, mock_hit_3])

    return qdrant


# ---------------------------------------------------------------------------
# Mock Prisma DB — configurable for each test scenario
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_posttrip():
    """
    Prisma mock with configurable find/create methods.

    Callers override specific methods for their test scenario.
    Default: all finds return None/empty, creates return the input data.
    """
    db = AsyncMock()

    # Trip model
    db.trip = AsyncMock()
    db.trip.find_unique = AsyncMock(return_value=None)
    db.trip.find_many = AsyncMock(return_value=[])
    db.trip.update = AsyncMock(return_value=None)

    # User model
    db.user = AsyncMock()
    db.user.find_unique = AsyncMock(return_value=None)

    # ItinerarySlot model
    db.itineraryslot = AsyncMock()
    db.itineraryslot.find_many = AsyncMock(return_value=[])
    db.itineraryslot.update = AsyncMock(return_value=None)

    # BehavioralSignal model
    db.behavioralsignal = AsyncMock()
    db.behavioralsignal.find_many = AsyncMock(return_value=[])
    db.behavioralsignal.find_unique = AsyncMock(return_value=None)
    db.behavioralsignal.create = AsyncMock(return_value=None)

    # IntentionSignal model
    db.intentionsignal = AsyncMock()
    db.intentionsignal.find_first = AsyncMock(return_value=None)
    db.intentionsignal.create = AsyncMock(return_value=None)

    # ActivityNode model
    db.activitynode = AsyncMock()
    db.activitynode.find_many = AsyncMock(return_value=[])

    # RawEvent model
    db.rawevent = AsyncMock()
    db.rawevent.find_unique = AsyncMock(return_value=None)

    # Raw query support
    db.query_raw = AsyncMock(return_value=[])

    return db
