"""
Shared test fixtures for the Admin track test suite.

Provides:
- Mock Prisma client with admin-specific model mocks
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
# Mock Prisma client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_prisma():
    """
    Mock Prisma client with all admin-relevant model delegates.
    Each delegate has find_many, find_unique, find_first, count, create,
    create_many, update, delete stubs.
    """
    db = AsyncMock()

    # AuditLog
    db.auditlog = AsyncMock()
    db.auditlog.create = AsyncMock(return_value=_make_mock_obj({"id": _gen_id()}))
    db.auditlog.create_many = AsyncMock(return_value=None)
    db.auditlog.find_many = AsyncMock(return_value=[])
    db.auditlog.count = AsyncMock(return_value=0)
    # AuditLog should NOT have update or delete
    db.auditlog.update = AsyncMock(side_effect=Exception("AuditLog is append-only: UPDATE rejected"))
    db.auditlog.delete = AsyncMock(side_effect=Exception("AuditLog is append-only: DELETE rejected"))

    # ModelRegistry
    db.modelregistry = AsyncMock()
    db.modelregistry.find_many = AsyncMock(return_value=[])
    db.modelregistry.find_unique = AsyncMock(return_value=None)
    db.modelregistry.find_first = AsyncMock(return_value=None)
    db.modelregistry.create = AsyncMock()
    db.modelregistry.update = AsyncMock()

    # SharedTripToken
    db.sharedtriptoken = AsyncMock()
    db.sharedtriptoken.find_many = AsyncMock(return_value=[])
    db.sharedtriptoken.find_unique = AsyncMock(return_value=None)
    db.sharedtriptoken.count = AsyncMock(return_value=0)
    db.sharedtriptoken.update = AsyncMock()

    # InviteToken
    db.invitetoken = AsyncMock()
    db.invitetoken.find_many = AsyncMock(return_value=[])
    db.invitetoken.find_unique = AsyncMock(return_value=None)
    db.invitetoken.count = AsyncMock(return_value=0)
    db.invitetoken.update = AsyncMock()

    # RawEvent
    db.rawevent = AsyncMock()
    db.rawevent.find_many = AsyncMock(return_value=[])
    db.rawevent.find_unique = AsyncMock(return_value=None)
    db.rawevent.count = AsyncMock(return_value=0)
    db.rawevent.update = AsyncMock()

    # User (for batch email lookups)
    db.user = AsyncMock()
    db.user.find_many = AsyncMock(return_value=[])
    db.user.find_unique = AsyncMock(return_value=None)
    db.user.count = AsyncMock(return_value=0)
    db.user.update = AsyncMock()

    # Trip
    db.trip = AsyncMock()
    db.trip.find_many = AsyncMock(return_value=[])

    # BehavioralSignal
    db.behavioralsignal = AsyncMock()
    db.behavioralsignal.find_many = AsyncMock(return_value=[])
    db.behavioralsignal.count = AsyncMock(return_value=0)

    # Raw SQL support
    db.query_raw = AsyncMock(return_value=[])
    db.execute_raw = AsyncMock(return_value=0)

    return db


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
def admin_app(mock_prisma, admin_user):
    """
    FastAPI app with admin routers mounted and dependencies overridden.
    Uses mock Prisma and a fixed admin user for all auth checks.
    """
    from services.api.routers.admin_safety import router as safety_router, _get_db, _require_admin_user
    from services.api.routers.admin_models import (
        router as models_router,
        _get_db as models_get_db,
        _require_admin_user as models_require_admin,
    )
    from services.api.routers.admin_pipeline import (
        router as pipeline_router,
        _get_db as pipeline_get_db,
        _require_admin_user as pipeline_require_admin,
    )

    app = FastAPI()
    app.include_router(safety_router)
    app.include_router(models_router)
    app.include_router(pipeline_router)

    # Override dependencies
    app.dependency_overrides[_get_db] = lambda: mock_prisma
    app.dependency_overrides[_require_admin_user] = lambda: admin_user
    app.dependency_overrides[models_get_db] = lambda: mock_prisma
    app.dependency_overrides[models_require_admin] = lambda: admin_user
    app.dependency_overrides[pipeline_get_db] = lambda: mock_prisma
    app.dependency_overrides[pipeline_require_admin] = lambda: admin_user

    return app


@pytest.fixture
def unauthenticated_app(mock_prisma):
    """
    FastAPI app where admin auth dependency raises 401.
    Used to test the auth guard.
    """
    from fastapi import HTTPException
    from services.api.routers.admin_safety import router as safety_router, _get_db, _require_admin_user
    from services.api.routers.admin_models import (
        router as models_router,
        _get_db as models_get_db,
        _require_admin_user as models_require_admin,
    )

    app = FastAPI()
    app.include_router(safety_router)
    app.include_router(models_router)

    def raise_unauth():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[_get_db] = lambda: mock_prisma
    app.dependency_overrides[_require_admin_user] = raise_unauth
    app.dependency_overrides[models_get_db] = lambda: mock_prisma
    app.dependency_overrides[models_require_admin] = raise_unauth

    return app


@pytest.fixture
def non_admin_app(mock_prisma):
    """
    FastAPI app where admin auth dependency raises 403.
    Used to test the auth guard for non-admin users.
    """
    from fastapi import HTTPException
    from services.api.routers.admin_safety import router as safety_router, _get_db, _require_admin_user

    app = FastAPI()
    app.include_router(safety_router)

    def raise_forbidden():
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[_get_db] = lambda: mock_prisma
    app.dependency_overrides[_require_admin_user] = raise_forbidden

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
