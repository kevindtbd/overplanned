"""
Shared test fixtures for the Admin track test suite.

Provides:
- MockSASession with admin-specific configuration
- Admin auth dependency overrides
- Factory functions for admin-specific models (AuditLog, ModelRegistry, etc.)
- FastAPI test client with admin routers mounted
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request

from services.api.tests.helpers.mock_sa import MockSASession

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:25432/overplanned_test")


# ---------------------------------------------------------------------------
# ID generator
# ---------------------------------------------------------------------------

def _gen_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Factory functions — admin-specific models
# ---------------------------------------------------------------------------

def make_admin_user(**overrides: Any) -> dict:
    """Factory for an admin user dict (as returned by _require_admin_user)."""
    base = {
        "id": _gen_id(),
        "email": f"admin-{uuid.uuid4().hex[:6]}@overplanned.app",
        "systemRole": "admin",
    }
    base.update(overrides)
    return base


def make_regular_user(**overrides: Any) -> dict:
    """Factory for a non-admin user dict."""
    base = {
        "id": _gen_id(),
        "email": f"user-{uuid.uuid4().hex[:6]}@example.com",
        "systemRole": "user",
    }
    base.update(overrides)
    return base


def make_audit_log_entry(**overrides: Any) -> dict:
    """Factory for AuditLog records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "actorId": _gen_id(),
        "action": "test.action",
        "targetType": "TestEntity",
        "targetId": _gen_id(),
        "before": None,
        "after": None,
        "ipAddress": "127.0.0.1",
        "userAgent": "pytest/1.0",
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_model_registry_entry(**overrides: Any) -> dict:
    """Factory for ModelRegistry records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "modelName": "vibe-classifier",
        "modelVersion": "1.0.0",
        "stage": "staging",
        "modelType": "classification",
        "description": "Test model",
        "artifactPath": "/models/vibe-classifier/1.0.0",
        "artifactHash": "sha256:" + uuid.uuid4().hex,
        "metrics": {"f1": 0.85, "precision": 0.88, "recall": 0.82},
        "evaluatedAt": now - timedelta(hours=1),
        "trainingDataRange": {"from": "2025-01-01", "to": "2025-06-01", "signal_count": 50000},
        "promotedAt": None,
        "promotedBy": None,
        "createdAt": now,
        "updatedAt": now,
    }
    base.update(overrides)
    return base


def make_shared_trip_token(trip_id: str | None = None, **overrides: Any) -> dict:
    """Factory for SharedTripToken records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id or _gen_id(),
        "token": uuid.uuid4().hex,
        "createdBy": _gen_id(),
        "expiresAt": now + timedelta(days=7),
        "revokedAt": None,
        "viewCount": 0,
        "importCount": 0,
        "createdAt": now,
        "trip": MagicMock(destination="Tokyo, Japan"),
    }
    base.update(overrides)
    return base


def make_invite_token(trip_id: str | None = None, **overrides: Any) -> dict:
    """Factory for InviteToken records."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "tripId": trip_id or _gen_id(),
        "token": uuid.uuid4().hex,
        "createdBy": _gen_id(),
        "maxUses": 10,
        "usedCount": 0,
        "role": "viewer",
        "expiresAt": now + timedelta(days=7),
        "revokedAt": None,
        "createdAt": now,
        "trip": MagicMock(destination="Kyoto, Japan"),
    }
    base.update(overrides)
    return base


def make_flagged_raw_event(user_id: str | None = None, **overrides: Any) -> dict:
    """Factory for RawEvent flagged as injection attempt."""
    now = datetime.now(timezone.utc)
    base = {
        "id": _gen_id(),
        "userId": user_id or _gen_id(),
        "sessionId": _gen_id(),
        "tripId": None,
        "eventType": "prompt_bar.injection_flagged",
        "surface": "mobile",
        "payload": {
            "rawInput": "ignore previous instructions and...",
            "detectorVersion": "1.0",
            "confidence": 0.95,
            "reviewStatus": "pending",
        },
        "createdAt": now,
    }
    base.update(overrides)
    return base


def make_cost_alert_config(**overrides: Any) -> dict:
    """Factory for cost_alert_config rows."""
    base = {
        "pipeline_stage": "seed_enrichment",
        "daily_limit_usd": 50.0,
        "enabled": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_mock_obj(data: dict) -> MagicMock:
    """Turn a dict into a MagicMock with attribute access."""
    obj = MagicMock()
    for k, v in data.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# Mock SA Session
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """
    MockSASession with queue-based execute() dispatcher.

    Usage in tests:
        session.returns_many([user1, user2])   # next execute -> scalars().all()
        session.returns_one(user)              # next execute -> scalars().first()
        session.returns_scalar(5)              # next execute -> scalar() = 5
        session.returns_get(node)              # next db.get() -> node
        session.returns_mapping_rows([...])    # next execute -> fetchall() with ._mapping

    Pass session.mock as the db dependency override.
    """
    return MockSASession()


@pytest.fixture
def admin_user():
    """Default admin user for tests."""
    return make_admin_user(id="admin-001", email="admin@overplanned.app")


@pytest.fixture
def regular_user():
    """Default non-admin user for tests."""
    return make_regular_user(id="user-001", email="user@example.com")


# ---------------------------------------------------------------------------
# Mock request
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_request():
    """Mock FastAPI Request with headers for audit extraction."""
    req = MagicMock(spec=Request)
    req.headers = {
        "X-Forwarded-For": "192.168.1.100",
        "User-Agent": "Mozilla/5.0 (Admin Test Suite)",
        "X-Admin-User-Id": "admin-001",
        "X-Admin-Role": "admin",
    }
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


# ---------------------------------------------------------------------------
# FastAPI test app with admin routers
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_app(mock_session, admin_user):
    """
    FastAPI app with all admin routers mounted and dependencies overridden.
    Uses MockSASession and a fixed admin user for all auth checks.
    """
    from services.api.routers.admin_users import router as users_router
    from services.api.routers.admin_safety import router as safety_router
    from services.api.routers.admin_models import router as models_router
    from services.api.routers.admin_pipeline import router as pipeline_router
    from services.api.routers.admin_nodes import router as nodes_router
    from services.api.routers.admin_sources import router as sources_router
    from services.api.routers._admin_deps import get_db as admin_get_db, require_admin_user

    app = FastAPI()
    app.include_router(users_router)
    app.include_router(safety_router)
    app.include_router(models_router)
    app.include_router(pipeline_router)
    app.include_router(nodes_router)
    app.include_router(sources_router)

    # Mock Redis on app state (used by admin_sources for staleness config)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    app.state.redis = mock_redis

    # Override dependencies -- all admin routers use shared deps from _admin_deps
    async def override_get_db():
        yield mock_session.mock

    app.dependency_overrides[admin_get_db] = override_get_db
    app.dependency_overrides[require_admin_user] = lambda: admin_user["id"]

    return app


@pytest.fixture
def unauthenticated_app(mock_session):
    """
    FastAPI app where admin auth dependency raises 401.
    Used to test the auth guard.
    """
    from fastapi import HTTPException
    from services.api.routers.admin_safety import router as safety_router
    from services.api.routers.admin_models import router as models_router
    from services.api.routers._admin_deps import get_db as admin_get_db, require_admin_user

    app = FastAPI()
    app.include_router(safety_router)
    app.include_router(models_router)

    def raise_unauth():
        raise HTTPException(status_code=401, detail="Authentication required")

    async def override_get_db():
        yield mock_session.mock

    app.dependency_overrides[admin_get_db] = override_get_db
    app.dependency_overrides[require_admin_user] = raise_unauth

    return app


@pytest.fixture
def non_admin_app(mock_session):
    """
    FastAPI app where admin auth dependency raises 403.
    Used to test the auth guard for non-admin users.
    """
    from fastapi import HTTPException
    from services.api.routers.admin_safety import router as safety_router
    from services.api.routers._admin_deps import get_db as admin_get_db, require_admin_user

    app = FastAPI()
    app.include_router(safety_router)

    def raise_forbidden():
        raise HTTPException(status_code=403, detail="Admin access required")

    async def override_get_db():
        yield mock_session.mock

    app.dependency_overrides[admin_get_db] = override_get_db
    app.dependency_overrides[require_admin_user] = raise_forbidden

    return app


@pytest.fixture
async def admin_client(admin_app):
    """Async HTTP client bound to the admin test app."""
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def unauth_client(unauthenticated_app):
    """Async HTTP client that will get 401 on all admin routes."""
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def forbidden_client(non_admin_app):
    """Async HTTP client that will get 403 on all admin routes."""
    transport = ASGITransport(app=non_admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
