"""
Shared trip links — public read-only itinerary access.

Endpoints:
  POST /trips/{id}/share   — generate a 90-day SharedTripToken (organizer only)
                             Rate limit: 30 req/min per IP (enforced in middleware
                             via the /share path prefix added to the IP bucket)
  GET  /shared/{token}     — fetch public trip data for the shared view
                             Returns identical 404 for nonexistent and revoked tokens.

Security:
  - 32-byte CSPRNG token, base64url-encoded, no padding.
  - Nonexistent and revoked tokens → identical 404 (no oracle).
  - No user PII exposed in the public response.
  - Slot/activity data only; behavioral signals are never included.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from prisma import Prisma
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shared-trips"])

_OPAQUE_404 = {
    "success": False,
    "error": {
        "code": "NOT_FOUND",
        "message": "Shared trip not found.",
    },
}

_SHARE_EXPIRY_DAYS = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


async def _get_prisma(request: Request) -> Prisma:
    db: Optional[Prisma] = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    return db


async def _require_organizer(db: Prisma, trip_id: str, user_id: str) -> None:
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
                    "message": "Only trip organizers can create share links.",
                },
            },
        )


async def _require_trip(db: Prisma, trip_id: str):
    trip = await db.trip.find_unique(where={"id": trip_id})
    if trip is None:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Trip not found."},
            },
        )
    return trip


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ShareCreateResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


class SharedTripResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/trips/{trip_id}/share", response_model=ShareCreateResponse)
async def create_share_link(
    trip_id: str,
    request: Request,
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> ShareCreateResponse:
    """
    Generate a 90-day read-only share link for the trip.

    Rate-limited to 30 req/min per IP via the middleware
    (the /trips/.../share path hits the standard auth bucket which is 60 req/min;
    a tighter 30/min bucket is enforced below using Redis directly when available).
    """
    try:
        uuid.UUID(trip_id)
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID format.")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # ---- Per-IP rate limit: 30/min ----------------------------------------
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        import time

        client_ip = "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host

        window_key = f"ratelimit:share:ip:{client_ip}"
        now_ts = time.time()
        window_start = now_ts - 60.0

        pipe = redis.pipeline()
        pipe.zremrangebyscore(window_key, 0, window_start)
        pipe.zcard(window_key)
        pipe.zadd(window_key, {f"{now_ts}:{id(request)}": now_ts})
        pipe.expire(window_key, 120)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= 30:
            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many share link requests. Max 30 per minute.",
                    },
                    "requestId": request_id,
                },
            )
    # -----------------------------------------------------------------------

    db = await _get_prisma(request)

    await _require_trip(db, trip_id)
    await _require_organizer(db, trip_id, x_user_id)

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=_SHARE_EXPIRY_DAYS)

    shared = await db.sharedtriptoken.create(
        data={
            "tripId": trip_id,
            "token": token,
            "createdBy": x_user_id,
            "expiresAt": expires_at,
        }
    )

    logger.info(
        "share_link_created trip=%s by=%s token_id=%s",
        trip_id,
        x_user_id,
        shared.id,
    )

    return ShareCreateResponse(
        success=True,
        data={
            "id": shared.id,
            "token": token,
            "tripId": trip_id,
            "expiresAt": expires_at.isoformat(),
            "shareUrl": f"/s/{token}",
        },
        requestId=request_id,
    )


@router.get("/shared/{token}", response_model=SharedTripResponse)
async def get_shared_trip(
    token: str,
    request: Request,
) -> SharedTripResponse:
    """
    Public endpoint — no auth required.

    Returns sanitized trip + itinerary data for the shared view.
    Identical 404 for nonexistent and revoked tokens.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db = await _get_prisma(request)

    now = datetime.now(timezone.utc)

    shared = await db.sharedtriptoken.find_unique(
        where={"token": token},
        include={
            "trip": {
                "include": {
                    "slots": {
                        "include": {"activityNode": True},
                        "order_by": [
                            {"dayNumber": "asc"},
                            {"sortOrder": "asc"},
                        ],
                    }
                }
            }
        },
    )

    # Identical 404 for nonexistent OR revoked tokens
    if shared is None or shared.revokedAt is not None or shared.expiresAt < now:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    # Increment view count (fire-and-forget; do not fail the response if this errors)
    try:
        await db.sharedtriptoken.update(
            where={"id": shared.id},
            data={"viewCount": {"increment": 1}},
        )
    except Exception:
        pass

    trip = shared.trip
    slots_by_day: dict[int, list[dict]] = {}

    for slot in trip.slots:
        day = slot.dayNumber
        if day not in slots_by_day:
            slots_by_day[day] = []

        node = slot.activityNode
        slot_data: dict = {
            "id": slot.id,
            "dayNumber": slot.dayNumber,
            "sortOrder": slot.sortOrder,
            "slotType": slot.slotType,
            "status": slot.status,
            "startTime": slot.startTime.isoformat() if slot.startTime else None,
            "endTime": slot.endTime.isoformat() if slot.endTime else None,
            "durationMinutes": slot.durationMinutes,
        }

        if node:
            slot_data["activity"] = {
                "id": node.id,
                "name": node.name,
                "canonicalName": node.canonicalName,
                "category": node.category,
                "subcategory": node.subcategory,
                "neighborhood": node.neighborhood,
                "priceLevel": node.priceLevel,
                "primaryImageUrl": node.primaryImageUrl,
                "descriptionShort": node.descriptionShort,
                "latitude": node.latitude,
                "longitude": node.longitude,
            }

        slots_by_day[day].append(slot_data)

    return SharedTripResponse(
        success=True,
        data={
            "trip": {
                "id": trip.id,
                "destination": trip.destination,
                "city": trip.city,
                "country": trip.country,
                "timezone": trip.timezone,
                "startDate": trip.startDate.isoformat(),
                "endDate": trip.endDate.isoformat(),
                "status": trip.status,
                "mode": trip.mode,
            },
            "slotsByDay": slots_by_day,
            "sharedAt": shared.createdAt.isoformat(),
        },
        requestId=request_id,
    )
