"""
Invite flow for group trips.

Endpoints:
  POST   /trips/{id}/invite               — generate a single-use invite token (organizer only)
  GET    /trips/{id}/invites              — list active (non-expired, non-revoked) tokens
  PATCH  /trips/{id}/invites/{token_id}/revoke — revoke a token
  POST   /trips/{id}/join                 — redeem an invite token (no auth required at this layer;
                                            the Next.js layer passes the authed user's ID via
                                            X-User-Id header after they complete OAuth)
  GET    /invites/preview/{token}         — lightweight public preview for the invite landing page
                                            (only destination, date range, member count — no PII)

Security notes:
  - Tokens are 32 bytes of CSPRNG output, base64url-encoded (no padding) → 43 chars.
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

from fastapi import APIRouter, Header, HTTPException, Query, Request
from prisma import Prisma
from pydantic import BaseModel

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


async def _get_prisma(request: Request) -> Prisma:
    db: Optional[Prisma] = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    return db


async def _require_organizer(db: Prisma, trip_id: str, user_id: str) -> None:
    """Raise 403 if user is not an organizer of the trip."""
    member = await db.tripmember.find_first(
        where={"tripId": trip_id, "userId": user_id, "role": "organizer"}
    )
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


async def _require_trip(db: Prisma, trip_id: str) -> None:
    """Raise 404 if trip does not exist."""
    trip = await db.trip.find_unique(where={"id": trip_id})
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
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteCreateResponse:
    """Generate a single-use, 7-day invite token for the trip (organizer only)."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    db = await _get_prisma(request)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(db, trip_id)
    await _require_organizer(db, trip_id, x_user_id)

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invite = await db.invitetoken.create(
        data={
            "tripId": trip_id,
            "token": token,
            "createdBy": x_user_id,
            "maxUses": 1,
            "usedCount": 0,
            "role": "member",  # NEVER organizer
            "expiresAt": expires_at,
        }
    )

    logger.info(
        "invite_created trip=%s by=%s token_id=%s",
        trip_id,
        x_user_id,
        invite.id,
    )

    return InviteCreateResponse(
        success=True,
        data={
            "id": invite.id,
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
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteListResponse:
    """List active (non-expired, non-revoked, not fully used) invite tokens."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    db = await _get_prisma(request)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(db, trip_id)
    await _require_organizer(db, trip_id, x_user_id)

    now = datetime.now(timezone.utc)

    tokens = await db.invitetoken.find_many(
        where={
            "tripId": trip_id,
            "revokedAt": None,
            "expiresAt": {"gt": now},
            # Only show tokens that still have remaining uses
            "usedCount": {"lt": 1},  # maxUses is always 1 currently
        },
        order={"createdAt": "desc"},
    )

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
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> InviteCreateResponse:
    """Revoke an invite token (organizer only)."""
    try:
        uuid.UUID(trip_id)
        uuid.UUID(token_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    db = await _get_prisma(request)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    await _require_trip(db, trip_id)
    await _require_organizer(db, trip_id, x_user_id)

    invite = await db.invitetoken.find_first(
        where={"id": token_id, "tripId": trip_id}
    )
    if invite is None:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    if invite.revokedAt is not None:
        # Already revoked — idempotent, return success
        return InviteCreateResponse(
            success=True,
            data={"id": token_id, "revokedAt": invite.revokedAt.isoformat()},
            requestId=request_id,
        )

    now = datetime.now(timezone.utc)
    updated = await db.invitetoken.update(
        where={"id": token_id},
        data={"revokedAt": now},
    )

    logger.info(
        "invite_revoked trip=%s token_id=%s by=%s",
        trip_id,
        token_id,
        x_user_id,
    )

    return InviteCreateResponse(
        success=True,
        data={"id": updated.id, "revokedAt": now.isoformat()},
        requestId=request_id,
    )


@router.post("/{trip_id}/join", response_model=JoinResponse)
async def join_trip(
    trip_id: str,
    request: Request,
    token: str = Query(..., description="Invite token from the invite URL"),
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

    db = await _get_prisma(request)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    now = datetime.now(timezone.utc)

    # Single query — fetch token and check all validity conditions at once.
    # We deliberately do NOT distinguish between nonexistent, expired, revoked,
    # or maxed-out tokens (identical 404 for each).
    invite = await db.invitetoken.find_first(
        where={"token": token, "tripId": trip_id}
    )

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
    existing = await db.tripmember.find_first(
        where={"tripId": trip_id, "userId": x_user_id}
    )
    if existing is not None:
        # Already a member — idempotent success
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

    # Create TripMember and increment usedCount atomically
    member = await db.tripmember.create(
        data={
            "tripId": trip_id,
            "userId": x_user_id,
            "role": "member",  # NEVER organizer
            "status": "joined",
            "joinedAt": now,
        }
    )

    await db.invitetoken.update(
        where={"id": invite.id},
        data={"usedCount": {"increment": 1}},
    )

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
            "memberId": member.id,
            "role": "member",
            "status": "joined",
        },
        requestId=request_id,
    )


# ---------------------------------------------------------------------------
# Public preview (unauthenticated — used by the Next.js invite landing page)
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
) -> InvitePreviewResponse:
    """
    Public endpoint — no auth required.

    Returns a minimal preview of the trip for the invite landing page:
    destination, city, country, date range, and current member count.
    No PII is included.

    Identical 404 for invalid/expired/revoked/nonexistent tokens.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db = await _get_prisma(request)

    now = datetime.now(timezone.utc)

    invite = await db.invitetoken.find_first(
        where={"token": token},
        include={
            "trip": {
                "include": {
                    "_count": {"select": {"members": True}},
                }
            }
        },
    )

    # Identical 404 for all invalid states
    if (
        invite is None
        or invite.revokedAt is not None
        or invite.expiresAt < now
        or invite.usedCount >= invite.maxUses
    ):
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    trip = invite.trip

    return InvitePreviewResponse(
        success=True,
        data={
            "tripId": trip.id,
            "destination": trip.destination,
            "city": trip.city,
            "country": trip.country,
            "startDate": trip.startDate.isoformat(),
            "endDate": trip.endDate.isoformat(),
            "memberCount": trip._count.members if trip._count else 0,
            "valid": True,
        },
        requestId=request_id,
    )
