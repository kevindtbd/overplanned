"""
Audit logging middleware for admin actions.
Writes append-only AuditLog entries for every admin action.
"""

from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from services.api.db.models import AuditLog


class AuditLogEntry(BaseModel):
    """
    Model for creating audit log entries.
    Maps to AuditLog SA model.
    """

    actor_id: str
    action: str
    target_type: str
    target_id: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    ip_address: str
    user_agent: str


class AuditLogger:
    """
    Append-only audit logger for admin actions.
    Thread-safe, async-compatible.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        ip_address: str,
        user_agent: str,
        before: Optional[dict[str, Any]] = None,
        after: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Write an audit log entry.

        Args:
            actor_id: ID of user performing the action
            action: Action performed (e.g., 'user.update', 'trip.delete')
            target_type: Type of entity affected (e.g., 'User', 'Trip', 'ActivityNode')
            target_id: ID of affected entity
            ip_address: IP address of request origin
            user_agent: User agent string from request
            before: State before action (optional, for updates/deletes)
            after: State after action (optional, for creates/updates)

        Returns:
            ID of created audit log entry

        Notes:
            - All writes are append-only; no updates or deletes allowed
            - Before/after snapshots should exclude sensitive fields (passwords, tokens)
            - Action naming convention: {entity}.{verb} (e.g., 'user.update', 'trip.archive')
        """
        entry_id = str(uuid4())
        stmt = insert(AuditLog).values(
            id=entry_id,
            actorId=actor_id,
            action=action,
            targetType=target_type,
            targetId=target_id,
            before=before,
            after=after,
            ipAddress=ip_address,
            userAgent=user_agent,
            createdAt=datetime.now(timezone.utc),
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return entry_id

    async def log_batch(self, entries: list[AuditLogEntry]) -> int:
        """
        Write multiple audit log entries in a single transaction.

        Args:
            entries: List of audit log entries to write

        Returns:
            Number of entries written
        """
        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": str(uuid4()),
                "actorId": e.actor_id,
                "action": e.action,
                "targetType": e.target_type,
                "targetId": e.target_id,
                "before": e.before,
                "after": e.after,
                "ipAddress": e.ip_address,
                "userAgent": e.user_agent,
                "createdAt": now,
            }
            for e in entries
        ]
        stmt = insert(AuditLog).values(rows)
        await self.session.execute(stmt)
        await self.session.commit()
        return len(entries)


def extract_client_info(request) -> tuple[str, str]:
    """
    Extract IP address and user agent from FastAPI request.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (ip_address, user_agent)
    """
    # Prefer X-Admin-Client-IP (set by HMAC-signed proxy, trusted)
    # Falls back to X-Forwarded-For then direct client IP
    ip_address = request.headers.get("X-Admin-Client-IP", "").strip()
    if not ip_address:
        ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.client.host if request.client else "unknown"

    user_agent = request.headers.get("User-Agent", "unknown")

    return ip_address, user_agent


async def audit_action(
    db: AsyncSession,
    request,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
) -> str:
    """
    Convenience function for logging admin actions.
    Automatically extracts IP and user agent from request.

    Args:
        db: SA AsyncSession (named 'db' for backward compat with admin routers)
    """
    logger = AuditLogger(db)
    ip_address, user_agent = extract_client_info(request)

    return await logger.log(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        user_agent=user_agent,
        before=before,
        after=after,
    )
