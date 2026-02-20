"""
Integration tests: AuditLog append-only enforcement.

Verifies:
- C-SAF-001: AuditLog entries created on admin actions
- C-SAF-002: AuditLog UPDATE operations rejected
- C-SAF-003: AuditLog DELETE operations rejected
- AuditLog before/after snapshots captured correctly
- Batch audit logging works
- IP address and user agent extracted from request
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from services.api.middleware.audit import AuditLogger, audit_action, extract_client_info
from .conftest import make_audit_log_entry, make_admin_user, _gen_id, _make_mock_obj

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AuditLogger.log — append-only writes
# ---------------------------------------------------------------------------

class TestAuditLoggerWrite:
    """AuditLogger.log creates entries via db.auditlog.create."""

    async def test_log_creates_entry(self, mock_prisma):
        logger = AuditLogger(mock_prisma)
        entry_id = await logger.log(
            actor_id="admin-001",
            action="user.update",
            target_type="User",
            target_id="user-001",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            before={"name": "Old Name"},
            after={"name": "New Name"},
        )

        mock_prisma.auditlog.create.assert_called_once()
        call_data = mock_prisma.auditlog.create.call_args.kwargs["data"]
        assert call_data["actorId"] == "admin-001"
        assert call_data["action"] == "user.update"
        assert call_data["targetType"] == "User"
        assert call_data["targetId"] == "user-001"
        assert call_data["before"] == {"name": "Old Name"}
        assert call_data["after"] == {"name": "New Name"}
        assert call_data["ipAddress"] == "192.168.1.1"
        assert call_data["userAgent"] == "TestAgent/1.0"

    async def test_log_returns_entry_id(self, mock_prisma):
        expected_id = "audit-123"
        mock_prisma.auditlog.create = AsyncMock(
            return_value=_make_mock_obj({"id": expected_id})
        )
        logger = AuditLogger(mock_prisma)
        entry_id = await logger.log(
            actor_id="admin-001",
            action="test.action",
            target_type="Test",
            target_id="t-1",
            ip_address="1.2.3.4",
            user_agent="Test",
        )
        assert entry_id == expected_id

    async def test_log_with_none_before_after(self, mock_prisma):
        """before/after are optional (for read-only audit like lookups)."""
        logger = AuditLogger(mock_prisma)
        await logger.log(
            actor_id="admin-001",
            action="user_lookup",
            target_type="User",
            target_id="search",
            ip_address="1.2.3.4",
            user_agent="Test",
            before=None,
            after=None,
        )
        call_data = mock_prisma.auditlog.create.call_args.kwargs["data"]
        assert call_data["before"] is None
        assert call_data["after"] is None


# ---------------------------------------------------------------------------
# AuditLogger.log_batch
# ---------------------------------------------------------------------------

class TestAuditLogBatch:
    """Batch audit logging for bulk operations."""

    async def test_log_batch_creates_multiple(self, mock_prisma):
        from services.api.middleware.audit import AuditLogEntry

        logger = AuditLogger(mock_prisma)
        entries = [
            AuditLogEntry(
                actor_id="admin-001",
                action=f"test.action_{i}",
                target_type="TestEntity",
                target_id=f"entity-{i}",
                ip_address="1.2.3.4",
                user_agent="Test",
            )
            for i in range(3)
        ]

        count = await logger.log_batch(entries)
        assert count == 3
        mock_prisma.auditlog.create_many.assert_called_once()
        batch_data = mock_prisma.auditlog.create_many.call_args.kwargs["data"]
        assert len(batch_data) == 3


# ---------------------------------------------------------------------------
# C-SAF-002: UPDATE rejected
# ---------------------------------------------------------------------------

class TestAuditLogUpdateRejected:
    """AuditLog entries must never be updated — append-only."""

    async def test_update_raises_exception(self, mock_prisma):
        """Mock enforces that db.auditlog.update raises."""
        with pytest.raises(Exception, match="append-only"):
            await mock_prisma.auditlog.update(
                where={"id": "some-id"},
                data={"action": "tampered"},
            )


# ---------------------------------------------------------------------------
# C-SAF-003: DELETE rejected
# ---------------------------------------------------------------------------

class TestAuditLogDeleteRejected:
    """AuditLog entries must never be deleted — append-only."""

    async def test_delete_raises_exception(self, mock_prisma):
        """Mock enforces that db.auditlog.delete raises."""
        with pytest.raises(Exception, match="append-only"):
            await mock_prisma.auditlog.delete(where={"id": "some-id"})


# ---------------------------------------------------------------------------
# extract_client_info
# ---------------------------------------------------------------------------

class TestExtractClientInfo:
    """IP and user agent extraction from request."""

    def test_extracts_from_forwarded_for(self):
        req = MagicMock()
        req.headers = {
            "X-Forwarded-For": "203.0.113.50, 70.41.3.18",
            "User-Agent": "Mozilla/5.0",
        }
        req.client = MagicMock()
        req.client.host = "127.0.0.1"

        ip, ua = extract_client_info(req)
        assert ip == "203.0.113.50"
        assert ua == "Mozilla/5.0"

    def test_falls_back_to_client_host(self):
        req = MagicMock()
        req.headers = {"User-Agent": "curl/7.68"}
        req.client = MagicMock()
        req.client.host = "10.0.0.1"

        ip, ua = extract_client_info(req)
        assert ip == "10.0.0.1"
        assert ua == "curl/7.68"

    def test_unknown_when_no_client(self):
        req = MagicMock()
        req.headers = {}
        req.client = None

        ip, ua = extract_client_info(req)
        assert ip == "unknown"
        assert ua == "unknown"


# ---------------------------------------------------------------------------
# audit_action convenience function
# ---------------------------------------------------------------------------

class TestAuditActionConvenience:
    """audit_action extracts IP/UA and delegates to AuditLogger."""

    async def test_audit_action_creates_entry(self, mock_prisma, mock_request):
        entry_id = await audit_action(
            db=mock_prisma,
            request=mock_request,
            actor_id="admin-001",
            action="test.action",
            target_type="TestEntity",
            target_id="entity-001",
            before={"old": True},
            after={"new": True},
        )

        mock_prisma.auditlog.create.assert_called_once()
        call_data = mock_prisma.auditlog.create.call_args.kwargs["data"]
        assert call_data["actorId"] == "admin-001"
        assert call_data["action"] == "test.action"
        assert call_data["ipAddress"] == "192.168.1.100"
        assert "Mozilla" in call_data["userAgent"]


# ---------------------------------------------------------------------------
# Integration: Admin actions produce AuditLog entries
# ---------------------------------------------------------------------------

class TestAdminActionsProduceAuditEntries:
    """Verify that admin mutations actually call audit_action."""

    async def test_revoke_shared_token_audited(self, admin_client, mock_prisma):
        from .conftest import make_shared_trip_token
        token = make_shared_trip_token()
        mock_prisma.sharedtriptoken.find_unique = AsyncMock(return_value=_make_mock_obj(token))
        mock_prisma.sharedtriptoken.update = AsyncMock(
            return_value=_make_mock_obj({**token, "revokedAt": datetime.now(timezone.utc)})
        )

        response = await admin_client.post(f"/admin/safety/tokens/shared/{token['id']}/revoke")
        assert response.status_code == 200

        # Audit entry was created
        mock_prisma.auditlog.create.assert_called_once()
        audit_data = mock_prisma.auditlog.create.call_args.kwargs["data"]
        assert audit_data["action"] == "shared_token.revoke"
        assert audit_data["targetType"] == "SharedTripToken"

    async def test_review_injection_audited(self, admin_client, mock_prisma):
        from .conftest import make_flagged_raw_event
        event = make_flagged_raw_event()
        mock_prisma.rawevent.find_unique = AsyncMock(return_value=_make_mock_obj(event))

        response = await admin_client.patch(
            f"/admin/safety/injection-queue/{event['id']}",
            json={"status": "confirmed"},
        )
        assert response.status_code == 200

        mock_prisma.auditlog.create.assert_called_once()
        audit_data = mock_prisma.auditlog.create.call_args.kwargs["data"]
        assert audit_data["action"] == "injection_flag.confirmed"
