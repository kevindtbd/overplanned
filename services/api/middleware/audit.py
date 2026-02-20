"""
Audit logging middleware for admin actions.
Writes append-only AuditLog entries for every admin action.
"""

from datetime import datetime
from typing import Optional, Any
from prisma import Prisma
from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    """
    Model for creating audit log entries.
    Maps to AuditLog Prisma model.
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

    def __init__(self, db: Prisma):
        self.db = db

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
        entry = await self.db.auditlog.create(
            data={
                "actorId": actor_id,
                "action": action,
                "targetType": target_type,
                "targetId": target_id,
                "before": before,
                "after": after,
                "ipAddress": ip_address,
                "userAgent": user_agent,
            }
        )
        return entry.id

    async def log_batch(self, entries: list[AuditLogEntry]) -> int:
        """
        Write multiple audit log entries in a single transaction.

        Args:
            entries: List of audit log entries to write

        Returns:
            Number of entries written
        """
        await self.db.auditlog.create_many(
            data=[
                {
                    "actorId": e.actor_id,
                    "action": e.action,
                    "targetType": e.target_type,
                    "targetId": e.target_id,
                    "before": e.before,
                    "after": e.after,
                    "ipAddress": e.ip_address,
                    "userAgent": e.user_agent,
                }
                for e in entries
            ]
        )
        return len(entries)


def extract_client_info(request) -> tuple[str, str]:
    """
    Extract IP address and user agent from FastAPI request.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (ip_address, user_agent)
    """
    # Try X-Forwarded-For first (for proxy/load balancer scenarios)
    ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.client.host if request.client else "unknown"

    user_agent = request.headers.get("User-Agent", "unknown")

    return ip_address, user_agent


async def audit_action(
    db: Prisma,
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

    Example usage in FastAPI route:
        ```python
        from middleware.audit import audit_action

        @router.put("/admin/users/{user_id}")
        async def update_user(
            user_id: str,
            update: UserUpdate,
            request: Request,
            current_user: User = Depends(require_admin)
        ):
            # Capture before state
            before = await db.user.find_unique(where={"id": user_id})

            # Perform update
            updated_user = await db.user.update(
                where={"id": user_id},
                data=update.dict(exclude_unset=True)
            )

            # Log action
            await audit_action(
                db=db,
                request=request,
                actor_id=current_user.id,
                action="user.update",
                target_type="User",
                target_id=user_id,
                before=before.dict() if before else None,
                after=updated_user.dict()
            )

            return updated_user
        ```
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
