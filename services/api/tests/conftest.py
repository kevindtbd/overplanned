"""
Shared test fixtures for the Overplanned API test suite.

Provides:
- async FastAPI test client (no external services needed for unit tests)
- factory functions for core models (User, Trip, Session, ActivityNode, etc.)
- clean state isolation between tests
- reusable across all downstream tracks
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure test env vars before any app imports
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:25432/overplanned_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:26379/0")
os.environ.setdefault("QDRANT_URL", "http://localhost:26333")
os.environ.setdefault("QDRANT_API_KEY", "")
os.environ.setdefault("SENTRY_DSN", "")


# ---------------------------------------------------------------------------
# FastAPI test client — mocks Redis + Qdrant + DB for unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """In-memory mock Redis client for rate limiter tests."""
    redis = AsyncMock()
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[None, 0, None, None])
    redis.pipeline = MagicMock(return_value=pipe)
    redis.ping = AsyncMock()
    return redis


@pytest.fixture
def mock_db():
    """Mock async database pool. Tests needing real DB use the integration marker."""
    db = AsyncMock()
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(),
        __aexit__=AsyncMock(),
    ))
    db.execute = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service that returns deterministic 768-dim vectors."""
    service = MagicMock()
    service.model_name = "nomic-ai/nomic-embed-text-v1.5"
    service.dimensions = 768
    # Deterministic fake vector: all zeros except index 0
    fake_vector = [0.0] * 768
    fake_vector[0] = 1.0
    service.embed_single = MagicMock(return_value=fake_vector)
    service.embed_batch = MagicMock(return_value=[fake_vector])
    return service


@pytest.fixture
async def app(mock_redis, mock_db, mock_embedding_service):
    """Create a test FastAPI app with mocked dependencies."""
    from services.api.main import app as _app

    # Inject mocks into app state
    _app.state.redis = mock_redis
    _app.state.db = mock_db
    _app.state.settings = __import__(
        "services.api.config", fromlist=["settings"]
    ).settings

    # Mock qdrant client
    mock_qdrant = AsyncMock()
    mock_qdrant.search = AsyncMock(return_value=[])
    mock_qdrant.close = AsyncMock()
    _app.state.qdrant = mock_qdrant

    # Mock search service
    mock_search = AsyncMock()
    mock_search.search = AsyncMock(return_value={"results": [], "count": 0, "warning": None})
    _app.state.search_service = mock_search

    return _app


@pytest.fixture
async def client(app):
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Factory functions — one per core model
# ---------------------------------------------------------------------------

class _IDGenerator:
    """Generates deterministic UUIDs for test reproducibility."""

    def __call__(self) -> str:
        return str(uuid.uuid4())


_gen_id = _IDGenerator()


def make_user(**overrides: Any) -> dict:
    """Factory for User records.

    Handles nullable extension fields so downstream tracks (4/5)
    won't break Track 1 fixtures.
    """
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
        "name": "Test User",
        "avatarUrl": None,
        "googleId": f"google-{uuid.uuid4().hex[:12]}",
        "emailVerified": now,
        "subscriptionTier": "beta",
        "systemRole": "user",
        "featureFlags": None,
        "accessCohort": None,
        "stripeCustomerId": None,
        "stripeSubId": None,
        "stripePriceId": None,
        "onboardingComplete": False,
        "createdAt": now,
        "updatedAt": now,
        "lastActiveAt": None,
    }
    base.update(overrides)
    return base


def make_session(user_id: str | None = None, **overrides: Any) -> dict:
    """Factory for Session records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "sessionToken": f"tok-{uuid.uuid4().hex}",
        "userId": user_id or _gen_id(),
        "expires": now + timedelta(days=30),
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_trip(user_id: str | None = None, **overrides: Any) -> dict:
    """Factory for Trip records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "userId": user_id or _gen_id(),
        "mode": "solo",
        "status": "draft",
        "destination": "Tokyo, Japan",
        "city": "Tokyo",
        "country": "Japan",
        "timezone": "Asia/Tokyo",
        "startDate": now + timedelta(days=30),
        "endDate": now + timedelta(days=37),
        "groupId": None,
        "memberCount": None,
        "planningProgress": None,
        "presetTemplate": None,
        "personaSeed": None,
        "fairnessState": None,
        "affinityMatrix": None,
        "logisticsState": None,
        "createdAt": now,
        "updatedAt": now,
        "activatedAt": None,
        "completedAt": None,
    }
    base.update(overrides)
    return base


def make_activity_node(**overrides: Any) -> dict:
    """Factory for ActivityNode records."""
    now = datetime.now(timezone.utc)
    slug = f"test-{uuid.uuid4().hex[:8]}"
    base = {
        "id": _gen_id(),
        "name": "Test Activity",
        "slug": slug,
        "canonicalName": "Test Activity",
        "city": "Tokyo",
        "country": "Japan",
        "neighborhood": None,
        "latitude": 35.6762,
        "longitude": 139.6503,
        "category": "dining",
        "subcategory": None,
        "priceLevel": None,
        "hours": None,
        "address": None,
        "phoneNumber": None,
        "websiteUrl": None,
        "foursquareId": None,
        "googlePlaceId": None,
        "primaryImageUrl": None,
        "imageSource": None,
        "imageValidated": False,
        "sourceCount": 0,
        "convergenceScore": None,
        "authorityScore": None,
        "descriptionShort": None,
        "descriptionLong": None,
        "contentHash": None,
        "lastScrapedAt": None,
        "lastValidatedAt": None,
        "status": "pending",
        "flagReason": None,
        "resolvedToId": None,
        "isCanonical": True,
        "createdAt": now,
        "updatedAt": now,
    }
    base.update(overrides)
    return base


def make_behavioral_signal(user_id: str | None = None, **overrides: Any) -> dict:
    """Factory for BehavioralSignal records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "userId": user_id or _gen_id(),
        "tripId": None,
        "slotId": None,
        "activityNodeId": None,
        "signalType": "slot_view",
        "signalValue": 1.0,
        "tripPhase": "pre_trip",
        "rawAction": "view_slot",
        "weatherContext": None,
        "modelVersion": None,
        "promptVersion": None,
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_intention_signal(
    behavioral_signal_id: str | None = None,
    user_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Factory for IntentionSignal records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "behavioralSignalId": behavioral_signal_id or _gen_id(),
        "rawEventId": None,
        "userId": user_id or _gen_id(),
        "intentionType": "curiosity",
        "confidence": 0.8,
        "source": "model",
        "userProvided": False,
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_raw_event(
    user_id: str | None = None,
    session_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Factory for RawEvent records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "userId": user_id or _gen_id(),
        "sessionId": session_id or _gen_id(),
        "tripId": None,
        "activityNodeId": None,
        "clientEventId": f"evt-{uuid.uuid4().hex[:12]}",
        "eventType": "page_view",
        "intentClass": "implicit",
        "surface": "mobile",
        "payload": {},
        "platform": "ios",
        "screenWidth": 390,
        "networkType": "wifi",
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_itinerary_slot(trip_id: str | None = None, **overrides: Any) -> dict:
    """Factory for ItinerarySlot records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id or _gen_id(),
        "activityNodeId": None,
        "dayNumber": 1,
        "sortOrder": 0,
        "slotType": "anchor",
        "status": "proposed",
        "startTime": None,
        "endTime": None,
        "durationMinutes": None,
        "isLocked": False,
        "voteState": None,
        "isContested": False,
        "swappedFromId": None,
        "pivotEventId": None,
        "wasSwapped": False,
        "createdAt": now,
        "updatedAt": now,
    }
    base.update(overrides)
    return base


def make_quality_signal(activity_node_id: str | None = None, **overrides: Any) -> dict:
    """Factory for QualitySignal records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "activityNodeId": activity_node_id or _gen_id(),
        "sourceName": "reddit",
        "sourceUrl": "https://reddit.com/r/JapanTravel/...",
        "sourceAuthority": 0.7,
        "signalType": "positive_mention",
        "rawExcerpt": "This place is amazing",
        "extractedAt": now,
        "createdAt": now,
    }
    base.update(overrides)
    return base
