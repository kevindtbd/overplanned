"""
Admin Trust & Safety API.

Token management (SharedTripToken, InviteToken) and injection detection queue.
All mutations logged to AuditLog. Read-only queries for review queues.
"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db
from services.api.db.models import SharedTripToken, InviteToken, RawEvent, User, Trip

router = APIRouter(prefix="/admin/safety", tags=["admin-safety"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class SharedTokenRow(BaseModel):
    id: str
    tripId: str
    tripDestination: Optional[str]
    token: str
    createdBy: str
    creatorEmail: Optional[str]
    expiresAt: str
    revokedAt: Optional[str]
    viewCount: int
    importCount: int
    createdAt: str
    isExpired: bool
    isRevoked: bool


class InviteTokenRow(BaseModel):
    id: str
    tripId: str
    tripDestination: Optional[str]
    token: str
    createdBy: str
    creatorEmail: Optional[str]
    maxUses: int
    usedCount: int
    role: str
    expiresAt: str
    revokedAt: Optional[str]
    createdAt: str
    isExpired: bool
    isRevoked: bool


class FlaggedInputRow(BaseModel):
    id: str
    userId: str
    userEmail: Optional[str]
    sessionId: str
    tripId: Optional[str]
    eventType: str
    surface: Optional[str]
    payload: dict
    createdAt: str
    reviewStatus: str  # pending | dismissed | confirmed


class ReviewAction(BaseModel):
    status: str  # dismissed | confirmed


# ---------------------------------------------------------------------------
# SharedTripToken endpoints
# ---------------------------------------------------------------------------

@router.get("/tokens/shared")
async def list_shared_tokens(
    request: Request,
    status: Optional[str] = Query(None, description="active | revoked | expired | all"),
    trip_id: Optional[str] = Query(None, description="Filter by trip ID"),
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """List SharedTripTokens with status filtering."""
    now = datetime.now(timezone.utc)

    stmt = select(SharedTripToken)
    count_stmt = select(func.count()).select_from(SharedTripToken)

    if trip_id:
        stmt = stmt.where(SharedTripToken.tripId == trip_id)
        count_stmt = count_stmt.where(SharedTripToken.tripId == trip_id)

    if status == "active":
        stmt = stmt.where(SharedTripToken.revokedAt.is_(None)).where(SharedTripToken.expiresAt > now)
        count_stmt = count_stmt.where(SharedTripToken.revokedAt.is_(None)).where(SharedTripToken.expiresAt > now)
    elif status == "revoked":
        stmt = stmt.where(SharedTripToken.revokedAt.isnot(None))
        count_stmt = count_stmt.where(SharedTripToken.revokedAt.isnot(None))
    elif status == "expired":
        stmt = stmt.where(SharedTripToken.revokedAt.is_(None)).where(SharedTripToken.expiresAt <= now)
        count_stmt = count_stmt.where(SharedTripToken.revokedAt.is_(None)).where(SharedTripToken.expiresAt <= now)

    stmt = stmt.order_by(SharedTripToken.createdAt.desc()).offset(skip).limit(take)

    result = await db.execute(stmt)
    tokens = result.scalars().all()

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Batch-fetch creator emails
    creator_ids = list({t.createdBy for t in tokens})
    creator_map: dict[str, str] = {}
    if creator_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(creator_ids))
        )
        for u in users_result.scalars().all():
            creator_map[u.id] = u.email

    # Batch-fetch trip destinations
    trip_ids = list({t.tripId for t in tokens})
    trip_map: dict[str, str] = {}
    if trip_ids:
        trips_result = await db.execute(
            select(Trip).where(Trip.id.in_(trip_ids))
        )
        for trip in trips_result.scalars().all():
            trip_map[trip.id] = trip.destination or ""

    rows = []
    for t in tokens:
        is_expired = t.expiresAt <= now
        rows.append(SharedTokenRow(
            id=t.id,
            tripId=t.tripId,
            tripDestination=trip_map.get(t.tripId),
            token=t.token[:8] + "...",  # Truncate for display
            createdBy=t.createdBy,
            creatorEmail=creator_map.get(t.createdBy),
            expiresAt=t.expiresAt.isoformat(),
            revokedAt=t.revokedAt.isoformat() if t.revokedAt else None,
            viewCount=t.viewCount,
            importCount=t.importCount,
            createdAt=t.createdAt.isoformat(),
            isExpired=is_expired,
            isRevoked=t.revokedAt is not None,
        ).model_dump())

    return {"data": rows, "total": total, "skip": skip, "take": take}


@router.post("/tokens/shared/{token_id}/revoke")
async def revoke_shared_token(
    token_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """Revoke a SharedTripToken. Audit-logged."""
    token = await db.get(SharedTripToken, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="SharedTripToken not found")
    if token.revokedAt is not None:
        raise HTTPException(status_code=409, detail="Token already revoked")

    now = datetime.now(timezone.utc)

    await db.execute(
        update(SharedTripToken).where(SharedTripToken.id == token_id).values(revokedAt=now)
    )
    await db.commit()

    await audit_action(
        db=db,
        request=request,
        actor_id=admin,
        action="shared_token.revoke",
        target_type="SharedTripToken",
        target_id=token_id,
        before={"revokedAt": None},
        after={"revokedAt": now.isoformat()},
    )

    return {
        "data": {"id": token_id, "revokedAt": now.isoformat()},
        "auditAction": "shared_token.revoke",
    }


# ---------------------------------------------------------------------------
# InviteToken endpoints
# ---------------------------------------------------------------------------

@router.get("/tokens/invite")
async def list_invite_tokens(
    request: Request,
    status: Optional[str] = Query(None, description="active | revoked | expired | all"),
    trip_id: Optional[str] = Query(None, description="Filter by trip ID"),
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """List InviteTokens with status filtering."""
    now = datetime.now(timezone.utc)

    stmt = select(InviteToken)
    count_stmt = select(func.count()).select_from(InviteToken)

    if trip_id:
        stmt = stmt.where(InviteToken.tripId == trip_id)
        count_stmt = count_stmt.where(InviteToken.tripId == trip_id)

    if status == "active":
        stmt = stmt.where(InviteToken.revokedAt.is_(None)).where(InviteToken.expiresAt > now)
        count_stmt = count_stmt.where(InviteToken.revokedAt.is_(None)).where(InviteToken.expiresAt > now)
    elif status == "revoked":
        stmt = stmt.where(InviteToken.revokedAt.isnot(None))
        count_stmt = count_stmt.where(InviteToken.revokedAt.isnot(None))
    elif status == "expired":
        stmt = stmt.where(InviteToken.revokedAt.is_(None)).where(InviteToken.expiresAt <= now)
        count_stmt = count_stmt.where(InviteToken.revokedAt.is_(None)).where(InviteToken.expiresAt <= now)

    stmt = stmt.order_by(InviteToken.createdAt.desc()).offset(skip).limit(take)

    result = await db.execute(stmt)
    tokens = result.scalars().all()

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Batch-fetch creator emails
    creator_ids = list({t.createdBy for t in tokens})
    creator_map: dict[str, str] = {}
    if creator_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(creator_ids))
        )
        for u in users_result.scalars().all():
            creator_map[u.id] = u.email

    # Batch-fetch trip destinations
    trip_ids = list({t.tripId for t in tokens})
    trip_map: dict[str, str] = {}
    if trip_ids:
        trips_result = await db.execute(
            select(Trip).where(Trip.id.in_(trip_ids))
        )
        for trip in trips_result.scalars().all():
            trip_map[trip.id] = trip.destination or ""

    rows = []
    for t in tokens:
        is_expired = t.expiresAt <= now
        rows.append(InviteTokenRow(
            id=t.id,
            tripId=t.tripId,
            tripDestination=trip_map.get(t.tripId),
            token=t.token[:8] + "...",
            createdBy=t.createdBy,
            creatorEmail=creator_map.get(t.createdBy),
            maxUses=t.maxUses,
            usedCount=t.usedCount,
            role=t.role,
            expiresAt=t.expiresAt.isoformat(),
            revokedAt=t.revokedAt.isoformat() if t.revokedAt else None,
            createdAt=t.createdAt.isoformat(),
            isExpired=is_expired,
            isRevoked=t.revokedAt is not None,
        ).model_dump())

    return {"data": rows, "total": total, "skip": skip, "take": take}


@router.post("/tokens/invite/{token_id}/revoke")
async def revoke_invite_token(
    token_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """Revoke an InviteToken. Audit-logged."""
    token = await db.get(InviteToken, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="InviteToken not found")
    if token.revokedAt is not None:
        raise HTTPException(status_code=409, detail="Token already revoked")

    now = datetime.now(timezone.utc)

    await db.execute(
        update(InviteToken).where(InviteToken.id == token_id).values(revokedAt=now)
    )
    await db.commit()

    await audit_action(
        db=db,
        request=request,
        actor_id=admin,
        action="invite_token.revoke",
        target_type="InviteToken",
        target_id=token_id,
        before={"revokedAt": None},
        after={"revokedAt": now.isoformat()},
    )

    return {
        "data": {"id": token_id, "revokedAt": now.isoformat()},
        "auditAction": "invite_token.revoke",
    }


# ---------------------------------------------------------------------------
# Injection Detection Queue
# ---------------------------------------------------------------------------

@router.get("/injection-queue")
async def list_flagged_inputs(
    request: Request,
    review_status: Optional[str] = Query(None, description="pending | dismissed | confirmed"),
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    List RawEvents flagged as potential injection attempts.
    Flagged events have eventType = 'prompt_bar.injection_flagged'.
    The payload.reviewStatus field tracks review state.
    """
    from sqlalchemy import text as sa_text

    stmt = select(RawEvent).where(RawEvent.eventType == "prompt_bar.injection_flagged")
    count_stmt = (
        select(func.count())
        .select_from(RawEvent)
        .where(RawEvent.eventType == "prompt_bar.injection_flagged")
    )

    # Filter by review status stored in payload JSONB
    if review_status:
        json_filter = RawEvent.payload["reviewStatus"].as_string() == review_status
        stmt = stmt.where(json_filter)
        count_stmt = count_stmt.where(json_filter)

    stmt = stmt.order_by(RawEvent.createdAt.desc()).offset(skip).limit(take)

    result = await db.execute(stmt)
    events = result.scalars().all()

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Batch-fetch user emails
    user_ids = list({e.userId for e in events})
    user_map: dict[str, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for u in users_result.scalars().all():
            user_map[u.id] = u.email

    rows = []
    for e in events:
        payload = e.payload if isinstance(e.payload, dict) else {}
        rows.append(FlaggedInputRow(
            id=e.id,
            userId=e.userId,
            userEmail=user_map.get(e.userId),
            sessionId=e.sessionId,
            tripId=e.tripId,
            eventType=e.eventType,
            surface=e.surface,
            payload=payload,
            createdAt=e.createdAt.isoformat(),
            reviewStatus=payload.get("reviewStatus", "pending"),
        ).model_dump())

    return {"data": rows, "total": total, "skip": skip, "take": take}


@router.patch("/injection-queue/{event_id}")
async def review_flagged_input(
    event_id: str,
    body: ReviewAction,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    Mark a flagged injection event as dismissed or confirmed.
    Updates the payload.reviewStatus field. Audit-logged.
    """
    if body.status not in ("dismissed", "confirmed"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'dismissed' or 'confirmed'",
        )

    event = await db.get(RawEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Flagged event not found")
    if event.eventType != "prompt_bar.injection_flagged":
        raise HTTPException(status_code=400, detail="Event is not an injection flag")

    payload = event.payload if isinstance(event.payload, dict) else {}
    old_status = payload.get("reviewStatus", "pending")

    # Update payload with review status and reviewer info
    updated_payload = {
        **payload,
        "reviewStatus": body.status,
        "reviewedBy": admin,
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
    }

    await db.execute(
        update(RawEvent).where(RawEvent.id == event_id).values(payload=updated_payload)
    )
    await db.commit()

    await audit_action(
        db=db,
        request=request,
        actor_id=admin,
        action=f"injection_flag.{body.status}",
        target_type="RawEvent",
        target_id=event_id,
        before={"reviewStatus": old_status},
        after={"reviewStatus": body.status},
    )

    return {
        "data": {"id": event_id, "reviewStatus": body.status},
        "auditAction": f"injection_flag.{body.status}",
    }
