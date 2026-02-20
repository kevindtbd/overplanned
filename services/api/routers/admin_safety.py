"""
Admin Trust & Safety API.

Token management (SharedTripToken, InviteToken) and injection detection queue.
All mutations logged to AuditLog. Read-only queries for review queues.
"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from prisma import Prisma

from middleware.audit import audit_action

router = APIRouter(prefix="/admin/safety", tags=["admin-safety"])


# ---------------------------------------------------------------------------
# Dependencies (wired by app startup)
# ---------------------------------------------------------------------------

def _get_db() -> Prisma:
    """Placeholder dependency -- wired by app lifespan."""
    raise NotImplementedError("Wire Prisma via app lifespan")


def _require_admin_user():
    """Placeholder dependency -- returns admin user dict with 'id' field."""
    raise NotImplementedError("Wire admin auth dependency")


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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
) -> dict:
    """List SharedTripTokens with status filtering."""
    now = datetime.now(timezone.utc)

    where: dict = {}
    if trip_id:
        where["tripId"] = trip_id

    if status == "active":
        where["revokedAt"] = None
        where["expiresAt"] = {"gt": now}
    elif status == "revoked":
        where["revokedAt"] = {"not": None}
    elif status == "expired":
        where["revokedAt"] = None
        where["expiresAt"] = {"lte": now}
    # 'all' or None = no filter

    tokens = await db.sharedtriptoken.find_many(
        where=where,
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
        include={"trip": True},
    )

    total = await db.sharedtriptoken.count(where=where)

    # Batch-fetch creator emails
    creator_ids = list({t.createdBy for t in tokens})
    creators = await db.user.find_many(
        where={"id": {"in": creator_ids}},
    ) if creator_ids else []
    creator_map = {u.id: u.email for u in creators}

    rows = []
    for t in tokens:
        is_expired = t.expiresAt <= now
        rows.append(SharedTokenRow(
            id=t.id,
            tripId=t.tripId,
            tripDestination=t.trip.destination if t.trip else None,
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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
) -> dict:
    """Revoke a SharedTripToken. Audit-logged."""
    token = await db.sharedtriptoken.find_unique(where={"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="SharedTripToken not found")
    if token.revokedAt is not None:
        raise HTTPException(status_code=409, detail="Token already revoked")

    now = datetime.now(timezone.utc)

    updated = await db.sharedtriptoken.update(
        where={"id": token_id},
        data={"revokedAt": now},
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=admin["id"],
        action="shared_token.revoke",
        target_type="SharedTripToken",
        target_id=token_id,
        before={"revokedAt": None},
        after={"revokedAt": now.isoformat()},
    )

    return {
        "data": {"id": updated.id, "revokedAt": updated.revokedAt.isoformat()},
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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
) -> dict:
    """List InviteTokens with status filtering."""
    now = datetime.now(timezone.utc)

    where: dict = {}
    if trip_id:
        where["tripId"] = trip_id

    if status == "active":
        where["revokedAt"] = None
        where["expiresAt"] = {"gt": now}
    elif status == "revoked":
        where["revokedAt"] = {"not": None}
    elif status == "expired":
        where["revokedAt"] = None
        where["expiresAt"] = {"lte": now}

    tokens = await db.invitetoken.find_many(
        where=where,
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
        include={"trip": True},
    )

    total = await db.invitetoken.count(where=where)

    creator_ids = list({t.createdBy for t in tokens})
    creators = await db.user.find_many(
        where={"id": {"in": creator_ids}},
    ) if creator_ids else []
    creator_map = {u.id: u.email for u in creators}

    rows = []
    for t in tokens:
        is_expired = t.expiresAt <= now
        rows.append(InviteTokenRow(
            id=t.id,
            tripId=t.tripId,
            tripDestination=t.trip.destination if t.trip else None,
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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
) -> dict:
    """Revoke an InviteToken. Audit-logged."""
    token = await db.invitetoken.find_unique(where={"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="InviteToken not found")
    if token.revokedAt is not None:
        raise HTTPException(status_code=409, detail="Token already revoked")

    now = datetime.now(timezone.utc)

    updated = await db.invitetoken.update(
        where={"id": token_id},
        data={"revokedAt": now},
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=admin["id"],
        action="invite_token.revoke",
        target_type="InviteToken",
        target_id=token_id,
        before={"revokedAt": None},
        after={"revokedAt": now.isoformat()},
    )

    return {
        "data": {"id": updated.id, "revokedAt": updated.revokedAt.isoformat()},
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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
) -> dict:
    """
    List RawEvents flagged as potential injection attempts.
    Flagged events have eventType = 'prompt_bar.injection_flagged'.
    The payload.reviewStatus field tracks review state.
    """
    where: dict = {
        "eventType": "prompt_bar.injection_flagged",
    }

    # Filter by review status stored in payload
    if review_status:
        where["payload"] = {"path": ["reviewStatus"], "equals": review_status}

    events = await db.rawevent.find_many(
        where=where,
        order={"createdAt": "desc"},
        skip=skip,
        take=take,
    )

    total = await db.rawevent.count(where=where)

    # Batch-fetch user emails
    user_ids = list({e.userId for e in events})
    users = await db.user.find_many(
        where={"id": {"in": user_ids}},
    ) if user_ids else []
    user_map = {u.id: u.email for u in users}

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
    db: Prisma = Depends(_get_db),
    admin=Depends(_require_admin_user),
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

    event = await db.rawevent.find_unique(where={"id": event_id})
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
        "reviewedBy": admin["id"],
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
    }

    await db.rawevent.update(
        where={"id": event_id},
        data={"payload": updated_payload},
    )

    await audit_action(
        db=db,
        request=request,
        actor_id=admin["id"],
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
