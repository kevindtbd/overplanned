"""
Unit tests: Admin auth guard.

Verifies:
- Unauthenticated requests → 401
- Non-admin users → 403
- Authenticated admin → 200 (passes through)
- Auth guard applied to ALL admin routes
"""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# C-ADM-001: Unauthenticated requests rejected with 401
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    """All admin endpoints reject unauthenticated requests."""

    ADMIN_ROUTES = [
        ("GET", "/admin/safety/tokens/shared"),
        ("GET", "/admin/safety/tokens/invite"),
        ("GET", "/admin/safety/injection-queue"),
        ("GET", "/admin/models"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    async def test_unauthenticated_returns_401(self, unauth_client, method, path):
        response = await unauth_client.request(method, path)
        assert response.status_code == 401

    async def test_unauthenticated_revoke_shared_token(self, unauth_client):
        response = await unauth_client.post("/admin/safety/tokens/shared/fake-id/revoke")
        assert response.status_code == 401

    async def test_unauthenticated_revoke_invite_token(self, unauth_client):
        response = await unauth_client.post("/admin/safety/tokens/invite/fake-id/revoke")
        assert response.status_code == 401

    async def test_unauthenticated_review_injection(self, unauth_client):
        response = await unauth_client.patch(
            "/admin/safety/injection-queue/fake-id",
            json={"status": "dismissed"},
        )
        assert response.status_code == 401

    async def test_unauthenticated_promote_model(self, unauth_client):
        response = await unauth_client.post(
            "/admin/models/fake-id/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# C-ADM-002: Non-admin users rejected with 403
# ---------------------------------------------------------------------------

class TestNonAdminAccess:
    """Non-admin users get 403 Forbidden on admin endpoints."""

    async def test_non_admin_list_tokens(self, forbidden_client):
        response = await forbidden_client.get("/admin/safety/tokens/shared")
        assert response.status_code == 403

    async def test_non_admin_list_injection_queue(self, forbidden_client):
        response = await forbidden_client.get("/admin/safety/injection-queue")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# C-ADM-003: Authenticated admin passes through
# ---------------------------------------------------------------------------

class TestAuthenticatedAdmin:
    """Admin users pass auth guard and reach route handlers."""

    async def test_admin_can_list_shared_tokens(self, admin_client):
        response = await admin_client.get("/admin/safety/tokens/shared")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    async def test_admin_can_list_invite_tokens(self, admin_client):
        response = await admin_client.get("/admin/safety/tokens/invite")
        assert response.status_code == 200

    async def test_admin_can_list_injection_queue(self, admin_client):
        response = await admin_client.get("/admin/safety/injection-queue")
        assert response.status_code == 200

    async def test_admin_can_list_models(self, admin_client):
        response = await admin_client.get("/admin/models")
        assert response.status_code == 200
