"""
POST /generate — Solo itinerary generation endpoint.

Validates the request, pulls the Trip from Postgres, runs the generation
engine, and returns a summary of what was created.

Auth: expects X-User-Id header (set by Next.js middleware / API gateway).
Rate limit: uses the llm rate limit bucket (5 req/min per user).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import anthropic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from services.api.generation.engine import GenerationEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    tripId: str = Field(..., min_length=1, description="UUID of the Trip row")
    userId: str = Field(..., min_length=1, description="UUID of the requesting user")
    sessionId: str | None = Field(
        default=None,
        description="Client session ID for event correlation"
    )

    @field_validator("tripId", "userId")
    @classmethod
    def must_be_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"Must be a valid UUID, got: {v!r}") from exc
        return v


class GenerateResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=GenerateResponse)
async def generate_itinerary(body: GenerateRequest, request: Request) -> dict:
    """
    Trigger itinerary generation for a solo trip.

    Steps performed server-side:
    1. Fetch Trip from Postgres (validates existence + ownership)
    2. Ensure trip mode is 'solo'
    3. Run GenerationEngine pipeline
    4. Return summary (slots created, method used, warnings)

    HTTP errors:
    - 404 if Trip not found
    - 403 if userId does not match Trip owner
    - 409 if Trip already has generated slots (idempotency guard)
    - 422 if trip mode is not solo
    - 500 on pipeline failure (with structured error)
    """
    db = request.app.state.db
    search_service = request.app.state.search_service
    request_id: str = request.state.request_id

    # ------------------------------------------------------------------
    # Fetch Trip row
    # ------------------------------------------------------------------
    trip_row = await _fetch_trip(db, body.tripId)
    if trip_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TRIP_NOT_FOUND",
                "message": f"Trip {body.tripId!r} not found.",
            },
        )

    # ------------------------------------------------------------------
    # Ownership check
    # ------------------------------------------------------------------
    # TripMember organizer check — join via TripMember where role=organizer
    is_owner = await _is_trip_organizer(db, body.tripId, body.userId)
    if not is_owner:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "You do not have permission to generate this itinerary.",
            },
        )

    # ------------------------------------------------------------------
    # Mode guard — solo only
    # ------------------------------------------------------------------
    trip_mode = trip_row.get("mode") or ""
    if trip_mode != "solo":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_TRIP_MODE",
                "message": f"Generation endpoint only supports solo trips. Got mode={trip_mode!r}.",
            },
        )

    # ------------------------------------------------------------------
    # Idempotency guard — don't regenerate if slots already exist
    # ------------------------------------------------------------------
    existing_slot_count = await _count_existing_slots(db, body.tripId)
    if existing_slot_count > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ALREADY_GENERATED",
                "message": (
                    f"Trip already has {existing_slot_count} itinerary slots. "
                    "Delete existing slots before regenerating."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Build GenerationEngine dependencies
    # ------------------------------------------------------------------
    anthropic_client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    engine = GenerationEngine(
        search_service=search_service,
        anthropic_client=anthropic_client,
        db=db,
    )

    # ------------------------------------------------------------------
    # Parse trip fields
    # ------------------------------------------------------------------
    persona_seed: dict = trip_row.get("personaSeed") or {}
    city: str = trip_row["city"]
    start_date: datetime = _ensure_utc(trip_row["startDate"])
    end_date: datetime = _ensure_utc(trip_row["endDate"])

    # ------------------------------------------------------------------
    # Run generation pipeline
    # ------------------------------------------------------------------
    try:
        result = await engine.generate(
            trip_id=body.tripId,
            user_id=body.userId,
            city=city,
            persona_seed=persona_seed,
            start_date=start_date,
            end_date=end_date,
            session_id=body.sessionId,
        )
    except Exception as exc:
        logger.exception(
            "Generation pipeline failed: trip=%s user=%s",
            body.tripId,
            body.userId,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "GENERATION_FAILED",
                "message": "Itinerary generation encountered an unexpected error.",
            },
        ) from exc

    return {
        "success": True,
        "data": result,
        "requestId": request_id,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _fetch_trip(db, trip_id: str) -> dict | None:
    """Fetch a single Trip row. Returns None if not found."""
    row = await db.fetchrow(
        """
        SELECT id, mode, city, country, timezone,
               "startDate", "endDate", "personaSeed", status
        FROM trips
        WHERE id = $1
        """,
        trip_id,
    )
    return dict(row) if row else None


async def _is_trip_organizer(db, trip_id: str, user_id: str) -> bool:
    """Return True if user is an organizer TripMember of the trip."""
    row = await db.fetchrow(
        """
        SELECT 1
        FROM trip_members
        WHERE "tripId" = $1
          AND "userId" = $2
          AND role = 'organizer'
          AND status = 'joined'
        """,
        trip_id,
        user_id,
    )
    return row is not None


async def _count_existing_slots(db, trip_id: str) -> int:
    """Return the number of ItinerarySlots already created for this trip."""
    row = await db.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM itinerary_slots
        WHERE "tripId" = $1
        """,
        trip_id,
    )
    return int(row["cnt"]) if row else 0


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
