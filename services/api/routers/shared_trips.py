"""
Shared trip links -- public read-only itinerary access.

Endpoints:
  POST /trips/{id}/share   -- generate a 90-day SharedTripToken (organizer only)
  GET  /shared/{token}     -- fetch public trip data for the shared view

Security:
  - 32-byte CSPRNG token, base64url-encoded, no padding.
  - Nonexistent and revoked tokens -> identical 404 (no oracle).
  - No user PII exposed in the public response.
  - Slot/activity data only; behavioral signals are never included.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import and_, select, update, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import SharedTripToken, Trip, TripMember
from services.api.db.session import get_db

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


async def _require_organizer(session: AsyncSession, trip_id: str, user_id: str) -> None:
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
                    "message": "Only trip organizers can create share links.",
                },
            },
        )


async def _require_trip(session: AsyncSession, trip_id: str):
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
    session: AsyncSession = Depends(get_db),
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> ShareCreateResponse:
    """Generate a 90-day read-only share link for the trip."""
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

    await _require_trip(session, trip_id)
    await _require_organizer(session, trip_id, x_user_id)

    token = _generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=_SHARE_EXPIRY_DAYS)
    shared_id = str(uuid.uuid4())

    stmt = insert(SharedTripToken).values(
        id=shared_id,
        tripId=trip_id,
        token=token,
        createdBy=x_user_id,
        expiresAt=expires_at,
        createdAt=datetime.now(timezone.utc),
    )
    await session.execute(stmt)
    await session.commit()

    logger.info(
        "share_link_created trip=%s by=%s token_id=%s",
        trip_id,
        x_user_id,
        shared_id,
    )

    return ShareCreateResponse(
        success=True,
        data={
            "id": shared_id,
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
    session: AsyncSession = Depends(get_db),
) -> SharedTripResponse:
    """
    Public endpoint -- no auth required.

    Returns sanitized trip + itinerary data for the shared view.
    Identical 404 for nonexistent and revoked tokens.

    NOTE: The slot/activity data is fetched via raw SQL since the
    ItinerarySlot -> ActivityNode join requires columns beyond the
    SA models defined for this migration scope.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    now = datetime.now(timezone.utc)

    # Fetch shared token + trip in one JOIN
    stmt = (
        select(SharedTripToken, Trip)
        .join(Trip, SharedTripToken.tripId == Trip.id)
        .where(SharedTripToken.token == token)
    )
    result = await session.execute(stmt)
    row = result.first()

    if row is None:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    shared, trip = row

    # Identical 404 for nonexistent OR revoked tokens
    if shared.revokedAt is not None or shared.expiresAt < now:
        raise HTTPException(status_code=404, detail=_OPAQUE_404)

    # Increment view count (fire-and-forget)
    try:
        update_stmt = (
            update(SharedTripToken)
            .where(SharedTripToken.id == shared.id)
            .values(viewCount=SharedTripToken.viewCount + 1)
        )
        await session.execute(update_stmt)
        await session.commit()
    except Exception as exc:
        logger.warning("Failed to increment view count for token %s: %s", shared.id, exc)

    # Fetch slots + activity nodes via raw SQL
    # (ActivityNode is not in SA models scope -- using raw query)
    slots_query = text("""
        SELECT
            s.id, s."dayNumber", s."sortOrder", s."slotType", s.status,
            s."startTime", s."endTime", s."durationMinutes",
            a.id AS "activityId", a.name, a."canonicalName", a.category,
            a.subcategory, a.neighborhood, a."priceLevel",
            a."primaryImageUrl", a."descriptionShort",
            a.latitude, a.longitude
        FROM "ItinerarySlot" s
        LEFT JOIN "ActivityNode" a ON s."activityNodeId" = a.id
        WHERE s."tripId" = :trip_id
        ORDER BY s."dayNumber" ASC, s."sortOrder" ASC
    """)
    slots_result = await session.execute(slots_query, {"trip_id": trip.id})
    slot_rows = slots_result.mappings().all()

    slots_by_day: dict[int, list[dict]] = {}
    for row_data in slot_rows:
        day = row_data["dayNumber"]
        if day not in slots_by_day:
            slots_by_day[day] = []

        slot_data: dict = {
            "id": row_data["id"],
            "dayNumber": row_data["dayNumber"],
            "sortOrder": row_data["sortOrder"],
            "slotType": row_data["slotType"],
            "status": row_data["status"],
            "startTime": row_data["startTime"].isoformat() if row_data["startTime"] else None,
            "endTime": row_data["endTime"].isoformat() if row_data["endTime"] else None,
            "durationMinutes": row_data["durationMinutes"],
        }

        if row_data["activityId"]:
            slot_data["activity"] = {
                "id": row_data["activityId"],
                "name": row_data["name"],
                "canonicalName": row_data["canonicalName"],
                "category": row_data["category"],
                "subcategory": row_data["subcategory"],
                "neighborhood": row_data["neighborhood"],
                "priceLevel": row_data["priceLevel"],
                "primaryImageUrl": row_data["primaryImageUrl"],
                "descriptionShort": row_data["descriptionShort"],
                "latitude": row_data["latitude"],
                "longitude": row_data["longitude"],
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
