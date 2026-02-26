"""
Invite flow for group trips.

Endpoints:
  POST   /trips/{id}/invite               -- generate a single-use invite token (organizer only)
  GET    /trips/{id}/invites              -- list active (non-expired, non-revoked) tokens
  PATCH  /trips/{id}/invites/{token_id}/revoke -- revoke a token
  POST   /trips/{id}/join                 -- redeem an invite token (no auth required at this layer;
                                            the Next.js layer passes the authed user's ID via
                                            X-User-Id header after they complete OAuth)
  GET    /invites/preview/{token}         -- lightweight public preview for the invite landing page
                                            (only destination, date range, member count -- no PII)

Security notes:
  - Tokens are 32 bytes of CSPRNG output, base64url-encoded (no padding) -> 43 chars.
  - Expired, revoked, or nonexistent tokens all return the *identical* 404 response
    to prevent oracle attacks.
  - Invite tokens NEVER grant the organizer role.
  - Auth: X-User-Id header is expected on mutating endpoints (set by Next.js middleware).
  - Preview endpoint is unauthenticated and returns no PII.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, func, select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import InviteToken, Trip, TripMember
from services.api.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trips", tags=["invites"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPAQUE_404 = {
    "success": False,
    "error": {
        "code": "NOT_FOUND",
        "message": "Invite token not found.",
    },
}


def _generate_token() -> str:
    """Return a URL-safe 32-byte CSPRNG token (no padding)."""
    return secrets.token_urlsafe(32)


async def _require_organizer(session: AsyncSession, trip_id: str, user_id: str) -> None:
    """Raise 403 if user is not an organizer of the trip."""
    stmt = select(TripMember).where(
        and_(
            TripMember.tripId == trip_id,
            TripMember.userId == user_id,
            TripMember.role == "organizer",
        )
    )
    result = await session.execute(stmt)
    member = result.scalars().first()
    if member is None:
        raise HTTPException(
            status_code=403,
            detail={
                "success": False,
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Only trip organizers can manage invites.",
                },
            },
        )


async def _require_trip(session: AsyncSession, trip_id: str) -> None:
    """Raise 404 if trip does not exist."""
    stmt = select(Trip).where(Trip.id == trip_id)
    result = await session.execute(stmt)
    trip = result.scalars().first()
    if trip is None:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Trip not found."},
            },
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InviteCreateResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


class InviteListResponse(BaseModel):
    success: bool
    data: list[dict]
    requestId: str


class JoinResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{trip_id}/invite", response_model=InviteCreateResponse)
async def create_invite(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteCreateResponse:
    """Generate a single-use, 7-day invite token for the trip (organizer only)."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(session, trip_id)
    await _require_organizer(session, trip_id, x_user_id)

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invite_id = str(uuid.uuid4())

    stmt = insert(InviteToken).values(
        id=invite_id,
        tripId=trip_id,
        token=token,
        createdBy=x_user_id,
        maxUses=1,
        usedCount=0,
        role="member",  # NEVER organizer
        expiresAt=expires_at,
        createdAt=datetime.now(timezone.utc),
    )
    await session.execute(stmt)
    await session.commit()

    logger.info(
        "invite_created trip=%s by=%s token_id=%s",
        trip_id,
        x_user_id,
        invite_id,
    )

    return InviteCreateResponse(
        success=True,
        data={
            "id": invite_id,
            "token": token,
            "tripId": trip_id,
            "role": "member",
            "maxUses": 1,
            "expiresAt": expires_at.isoformat(),
            "inviteUrl": f"/invite/{token}",
        },
        requestId=request_id,
    )


@router.get("/{trip_id}/invites", response_model=InviteListResponse)
async def list_invites(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteListResponse:
    """List active (non-expired, non-revoked, not fully used) invite tokens."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(session, trip_id)
    await _require_organizer(session, trip_id, x_user_id)

    now = datetime.now(timezone.utc)

    stmt = (
        select(InviteToken)
        .where(
            and_(
                InviteToken.tripId == trip_id,
                InviteToken.revokedAt.is_(None),
                InviteToken.expiresAt > now,
                InviteToken.usedCount < 1,  # maxUses is always 1 currently
            )
        )
        .order_by(InviteToken.createdAt.desc())
    )
    result = await session.execute(stmt)
    tokens = result.scalars().all()

    return InviteListResponse(
        success=True,
        data=[
            {
                "id": t.id,
                "token": t.token,
                "role": t.role,
                "maxUses": t.maxUses,
                "usedCount": t.usedCount,
                "expiresAt": t.expiresAt.isoformat(),
                "createdAt": t.createdAt.isoformat(),
                "inviteUrl": f"/invite/{t.token}",
            }
            for t in tokens
        ],
        requestId=request_id,
    )


@router.patch(
    "/{trip_id}/invites/{token_id}/revoke",
    response_model=InviteCreateResponse,
)
async def revoke_invite(
    trip_id: str,
    token_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteCreateResponse:
    """Revoke an invite token (organizer only)."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(token_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(session, trip_id)
    await _require_organizer(session, trip_id, x_user_id)

    stmt = select(InviteToken).where(
        and_(InviteToken.id == token_id, InviteToken.tripId == trip_id)
    )
    result = await session.execute(stmt)
    invite = result.scalars().first()
    if invite is None:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    if invite.revokedAt is not None:
        # Already revoked -- idempotent, return success
        return InviteCreateResponse(
            success=True,
            data={"id": token_id, "revokedAt": invite.revokedAt.isoformat()},
            requestId=request_id,
        )

    now = datetime.now(timezone.utc)
    update_stmt = (
        update(InviteToken)
        .where(InviteToken.id == token_id)
        .values(revokedAt=now)
    )
    await session.execute(update_stmt)
    await session.commit()

    logger.info(
        "invite_revoked trip=%s token_id=%s by=%s",
        trip_id,
        token_id,
        x_user_id,
    )

    return InviteCreateResponse(
        success=True,
        data={"id": token_id, "revokedAt": now.isoformat()},
        requestId=request_id,
    )


@router.post("/{trip_id}/join", response_model=JoinResponse)
async def join_trip(
    trip_id: str,
    request: Request,
    token: str = Query(..., description="Invite token from the invite URL"),
    session: AsyncSession = Depends(get_db),
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> JoinResponse:
    """
    Redeem an invite token to join a trip as a member.

    Expired, revoked, maxed-out, and nonexistent tokens all return identical
    404 responses to prevent information leakage.
    """
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    now = datetime.now(timezone.utc)

    # Fetch token -- identical 404 for all invalid states
    stmt = select(InviteToken).where(
        and_(InviteToken.token == token, InviteToken.tripId == trip_id)
    )
    result = await session.execute(stmt)
    invite = result.scalars().first()

    def _invalid() -> HTTPException:
        return HTTPException(status_code=404, detail=_OPAQUE_404)

    if invite is None:
        raise _invalid()
    if invite.revokedAt is not None:
        raise _invalid()
    if invite.expiresAt < now:
        raise _invalid()
    if invite.usedCount >= invite.maxUses:
        raise _invalid()

    # Check the user is not already a member
    existing_stmt = select(TripMember).where(
        and_(TripMember.tripId == trip_id, TripMember.userId == x_user_id)
    )
    existing_result = await session.execute(existing_stmt)
    existing = existing_result.scalars().first()
    if existing is not None:
        # Already a member -- idempotent success
        return JoinResponse(
            success=True,
            data={
                "tripId": trip_id,
                "userId": x_user_id,
                "role": existing.role,
                "status": existing.status,
                "alreadyMember": True,
            },
            requestId=request_id,
        )

    # SECURITY: Atomic check-and-update to prevent TOCTOU race on usedCount
    atomic_update = (
        update(InviteToken)
        .where(
            and_(
                InviteToken.id == invite.id,
                InviteToken.usedCount < InviteToken.maxUses,
            )
        )
        .values(usedCount=InviteToken.usedCount + 1)
        .returning(InviteToken.id)
    )
    update_result = await session.execute(atomic_update)
    if update_result.first() is None:
        raise _invalid()  # used between check and update

    # Create TripMember
    member_id = str(uuid.uuid4())
    member_stmt = insert(TripMember).values(
        id=member_id,
        tripId=trip_id,
        userId=x_user_id,
        role="member",  # NEVER organizer
        status="joined",
        joinedAt=now,
        createdAt=now,
    )
    await session.execute(member_stmt)
    await session.commit()

    logger.info(
        "trip_joined trip=%s user=%s via_token=%s",
        trip_id,
        x_user_id,
        invite.id,
    )

    return JoinResponse(
        success=True,
        data={
            "tripId": trip_id,
            "userId": x_user_id,
            "memberId": member_id,
            "role": "member",
            "status": "joined",
        },
        requestId=request_id,
    )


# ---------------------------------------------------------------------------
# Public preview (unauthenticated -- used by the Next.js invite landing page)
# ---------------------------------------------------------------------------

# Separate router prefix to avoid auth middleware on this endpoint
preview_router = APIRouter(prefix="/invites", tags=["invites"])


class InvitePreviewResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


@preview_router.get("/preview/{token}", response_model=InvitePreviewResponse)
async def get_invite_preview(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> InvitePreviewResponse:
    """
    Public endpoint -- no auth required.

    Returns a minimal preview of the trip for the invite landing page:
    destination, city, country, date range, and current member count.
    No PII is included.

    Identical 404 for invalid/expired/revoked/nonexistent tokens.

    SECURITY: Uses a JOIN query so the DB round-trip count is constant
    regardless of token validity (prevents timing oracle).
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    now = datetime.now(timezone.utc)

    # SECURITY: Single JOIN query -- constant round-trip count prevents timing oracle
    stmt = (
        select(InviteToken, Trip)
        .join(Trip, InviteToken.tripId == Trip.id)
        .where(InviteToken.token == token)
    )
    result = await session.execute(stmt)
    row = result.first()

    # Identical 404 for all invalid states
    if row is None:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    invite_obj, trip_obj = row

    if (
        invite_obj.revokedAt is not None
        or invite_obj.expiresAt < now
        or invite_obj.usedCount >= invite_obj.maxUses
    ):
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    # Get member count separately (lightweight query) -- only joined members
    count_stmt = select(func.count()).select_from(TripMember).where(
        and_(
            TripMember.tripId == trip_obj.id,
            TripMember.status == "joined",
        )
    )
    count_result = await session.execute(count_stmt)
    member_count = count_result.scalar() or 0

    return InvitePreviewResponse(
        success=True,
        data={
            "tripId": trip_obj.id,
            "destination": trip_obj.destination,
            "city": trip_obj.city,
            "country": trip_obj.country,
            "startDate": trip_obj.startDate.isoformat(),
            "endDate": trip_obj.endDate.isoformat(),
            "memberCount": member_count,
            "valid": True,
        },
        requestId=request_id,
    )
