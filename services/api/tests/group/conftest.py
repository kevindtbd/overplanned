"""
Shared test fixtures for the Group trip test suite.

Provides:
- 3 test users (organizer + 2 participants)
- A group trip with all required fields
- Invite tokens (valid, expired, revoked, maxed)
- SharedTripToken factories
- Mock Prisma client wired for group operations
- Mock Redis for rate limiting
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.tests.helpers.mock_sa import MockSASession

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@localhost:25432/overplanned_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:26379/0")

# ---------------------------------------------------------------------------
# ID generator
# ---------------------------------------------------------------------------


def _gen_id() -> str:
    return str(uuid.uuid4())


def _make_obj(data: dict) -> MagicMock:
    """Turn a dict into a MagicMock with attribute access."""
    obj = MagicMock()
    for k, v in data.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------


def make_group_user(name: str, **overrides: Any) -> dict:
    """Factory for a group participant user."""
    now = datetime.now(timezone.utc)
    uid = _gen_id()
    base = {
        "id": uid,
        "email": f"{name.lower().replace(' ', '.')}-{uid[:6]}@example.com",
        "name": name,
        "avatarUrl": None,
        "googleId": f"google-{uid[:12]}",
        "emailVerified": now,
        "subscriptionTier": "beta",
        "systemRole": "user",
        "featureFlags": None,
        "createdAt": now,
        "updatedAt": now,
        "lastActiveAt": now,
    }
    base.update(overrides)
    return base


def make_group_trip(
    organizer_id: str,
    member_ids: list[str] | None = None,
    **overrides: Any,
) -> dict:
    """Factory for a group Trip record."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "userId": organizer_id,
        "mode": "group",
        "status": "active",
        "destination": "Kyoto, Japan",
        "city": "Kyoto",
        "country": "Japan",
        "timezone": "Asia/Tokyo",
        "startDate": now + timedelta(days=7),
        "endDate": now + timedelta(days=14),
        "groupId": _gen_id(),
        "memberCount": len(member_ids) + 1 if member_ids else 1,
        "planningProgress": 0.4,
        "presetTemplate": None,
        "personaSeed": None,
        "fairnessState": {
            "debts": {},
            "resolvedCount": 0,
            "abyleneEvents": 0,
        },
        "affinityMatrix": None,
        "logisticsState": None,
        "createdAt": now,
        "updatedAt": now,
        "activatedAt": now,
        "completedAt": None,
    }
    base.update(overrides)
    return base


def make_itinerary_slot_group(trip_id: str, **overrides: Any) -> dict:
    """Factory for an ItinerarySlot in a group trip context."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id,
        "activityNodeId": _gen_id(),
        "dayNumber": 1,
        "sortOrder": 0,
        "slotType": "anchor",
        "status": "proposed",
        "startTime": None,
        "endTime": None,
        "durationMinutes": 90,
        "isLocked": False,
        "voteState": {
            "votes": {},
            "threshold": 0.6,
            "resolved": False,
        },
        "isContested": False,
        "swappedFromId": None,
        "pivotEventId": None,
        "wasSwapped": False,
        "createdAt": now,
        "updatedAt": now,
    }
    base.update(overrides)
    return base


def make_invite_token(
    trip_id: str,
    created_by: str,
    **overrides: Any,
) -> dict:
    """Factory for an InviteToken record."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id,
        "token": uuid.uuid4().hex,
        "createdBy": created_by,
        "maxUses": 5,
        "usedCount": 0,
        "role": "editor",
        "expiresAt": now + timedelta(days=7),
        "revokedAt": None,
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_shared_trip_token(
    trip_id: str,
    created_by: str,
    **overrides: Any,
) -> dict:
    """Factory for a SharedTripToken record."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id,
        "token": uuid.uuid4().hex,
        "createdBy": created_by,
        "expiresAt": now + timedelta(days=7),
        "revokedAt": None,
        "viewCount": 0,
        "importCount": 0,
        "createdAt": now,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_alice() -> dict:
    """Trip organizer."""
    return make_group_user("Alice Nakamura", id="user-alice")


@pytest.fixture
def user_bob() -> dict:
    """First participant."""
    return make_group_user("Bob Chen", id="user-bob")


@pytest.fixture
def user_cara() -> dict:
    """Second participant."""
    return make_group_user("Cara Diaz", id="user-cara")


@pytest.fixture
def group_trip(user_alice, user_bob, user_cara) -> dict:
    """A fully-formed group trip with 3 members."""
    return make_group_trip(
        organizer_id=user_alice["id"],
        member_ids=[user_bob["id"], user_cara["id"]],
        id="trip-group-001",
        groupId="group-001",
        memberCount=3,
    )


@pytest.fixture
def valid_invite(group_trip, user_alice) -> dict:
    """Fresh, valid invite token."""
    return make_invite_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
    )


@pytest.fixture
def expired_invite(group_trip, user_alice) -> dict:
    """Invite token that has passed its expiry."""
    return make_invite_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
        expiresAt=datetime.now(timezone.utc) - timedelta(hours=1),
    )


@pytest.fixture
def revoked_invite(group_trip, user_alice) -> dict:
    """Invite token that was explicitly revoked."""
    return make_invite_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
        revokedAt=datetime.now(timezone.utc) - timedelta(hours=2),
    )


@pytest.fixture
def maxed_invite(group_trip, user_alice) -> dict:
    """Invite token that has hit its maxUses limit."""
    return make_invite_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
        maxUses=5,
        usedCount=5,
    )


@pytest.fixture
def valid_shared_token(group_trip, user_alice) -> dict:
    """Fresh, valid shared trip token."""
    return make_shared_trip_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
    )


@pytest.fixture
def expired_shared_token(group_trip, user_alice) -> dict:
    """Expired shared trip token."""
    return make_shared_trip_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
        expiresAt=datetime.now(timezone.utc) - timedelta(days=1),
    )


@pytest.fixture
def revoked_shared_token(group_trip, user_alice) -> dict:
    """Revoked shared trip token."""
    return make_shared_trip_token(
        trip_id=group_trip["id"],
        created_by=user_alice["id"],
        revokedAt=datetime.now(timezone.utc) - timedelta(hours=6),
    )


@pytest.fixture
def mock_session():
    """Mock SA session wired for group operations."""
    db = AsyncMock()

    # Trip
    db.trip = AsyncMock()
    db.trip.find_unique = AsyncMock(return_value=None)
    db.trip.find_many = AsyncMock(return_value=[])
    db.trip.update = AsyncMock()
    db.trip.create = AsyncMock()

    # User
    db.user = AsyncMock()
    db.user.find_unique = AsyncMock(return_value=None)
    db.user.find_many = AsyncMock(return_value=[])

    # InviteToken
    db.invitetoken = AsyncMock()
    db.invitetoken.find_unique = AsyncMock(return_value=None)
    db.invitetoken.find_first = AsyncMock(return_value=None)
    db.invitetoken.create = AsyncMock()
    db.invitetoken.update = AsyncMock()
    db.invitetoken.count = AsyncMock(return_value=0)

    # SharedTripToken
    db.sharedtriptoken = AsyncMock()
    db.sharedtriptoken.find_unique = AsyncMock(return_value=None)
    db.sharedtriptoken.find_first = AsyncMock(return_value=None)
    db.sharedtriptoken.create = AsyncMock()
    db.sharedtriptoken.update = AsyncMock()
    db.sharedtriptoken.count = AsyncMock(return_value=0)

    # ItinerarySlot
    db.itineraryslot = AsyncMock()
    db.itineraryslot.find_many = AsyncMock(return_value=[])
    db.itineraryslot.find_unique = AsyncMock(return_value=None)
    db.itineraryslot.update = AsyncMock()
    db.itineraryslot.create = AsyncMock()

    # BehavioralSignal
    db.behavioralsignal = AsyncMock()
    db.behavioralsignal.create = AsyncMock()
    db.behavioralsignal.find_many = AsyncMock(return_value=[])

    # AuditLog
    db.auditlog = AsyncMock()
    db.auditlog.create = AsyncMock()

    # Raw SQL
    db.query_raw = AsyncMock(return_value=[])
    db.execute_raw = AsyncMock(return_value=0)

    return db


@pytest.fixture
def mock_sa_session():
    """SA session mock for migrated code paths (invites, shared_trips, etc.)."""
    return MockSASession()


@pytest.fixture
def mock_redis():
    """In-memory mock Redis for rate limiting."""
    redis = AsyncMock()
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[None, 1, None, None])
    redis.pipeline = MagicMock(return_value=pipe)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.ping = AsyncMock()
    return redis
