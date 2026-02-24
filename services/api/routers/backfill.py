"""
POST /backfill/submit — Free-form trip diary ingestion.

Auth model: service-to-service.
  - X-Service-Token header validated against BACKFILL_SERVICE_TOKEN env var
  - X-User-Id header carries the authenticated user's UUID

Request:
  { "text": "<diary>", "city_hint": "Tokyo", "date_range_hint": "March 2025" }

Response:
  { "backfill_trip_id": "<uuid>", "status": "processing" }

Rate limits (checked before touching LLM pipeline):
  - 5 submissions per user per hour
  - 20 submissions per user per 24 hours

Idempotency:
  - SHA-256 hash of (userId + rawSubmission) stored on BackfillTrip
  - Duplicate submission returns existing backfill_trip_id with 200

Security:
  - confidenceTier, resolutionScore, quarantineReason NEVER returned to caller
  - Raw submission text is never echoed back in API responses
  - User text always processed server-side via pipeline (not reflected in API)
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from services.api.pipeline.backfill_pipeline import process_backfill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backfill", tags=["backfill"])

# ---------------------------------------------------------------------------
# Rate limit config
# ---------------------------------------------------------------------------

RATE_LIMIT_PER_HOUR = 5
RATE_LIMIT_PER_DAY = 20

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class BackfillSubmitRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="Free-form travel diary text",
    )
    city_hint: str | None = Field(
        default=None,
        max_length=200,
        alias="cityHint",
        description="Optional city name hint to scope extraction",
    )
    date_range_hint: str | None = Field(
        default=None,
        max_length=200,
        alias="dateRangeHint",
        description="Optional date range hint (e.g. 'March 2025')",
    )
    context_tag: str | None = Field(
        default=None,
        alias="contextTag",
        description="Travel context: solo, partner, family, friends, work",
    )

    model_config = {"populate_by_name": True}

    @field_validator("text")
    @classmethod
    def text_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must contain non-whitespace content")
        return v

    @field_validator("context_tag")
    @classmethod
    def valid_context(cls, v: str | None) -> str | None:
        if v is not None and v not in ("solo", "partner", "family", "friends", "work"):
            raise ValueError("context_tag must be one of: solo, partner, family, friends, work")
        return v


class BackfillSubmitResponse(BaseModel):
    backfill_trip_id: str
    status: str


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _verify_service_token(request: Request) -> str:
    """
    Validate X-Service-Token header against BACKFILL_SERVICE_TOKEN env var.
    Returns the authenticated user_id from X-User-Id header.
    Raises 401 on missing/invalid token, 400 on missing user ID.
    """
    expected_token = os.environ.get("BACKFILL_SERVICE_TOKEN", "")
    if not expected_token:
        # In development, skip token check but log a warning
        if os.environ.get("ENVIRONMENT", "development") != "development":
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "MISCONFIGURED",
                    "message": "Service token not configured.",
                },
            )
        logger.warning("BACKFILL_SERVICE_TOKEN not set — skipping auth (dev mode)")
    else:
        provided = request.headers.get("X-Service-Token", "")
        # Constant-time comparison to prevent timing attacks
        if not _constant_time_eq(provided, expected_token):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing service token.",
                },
            )

    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_USER_ID",
                "message": "X-User-Id header is required.",
            },
        )
    return user_id


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing side-channels."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0


# ---------------------------------------------------------------------------
# Dedup hash
# ---------------------------------------------------------------------------


def _submission_hash(user_id: str, text: str) -> str:
    """SHA-256 hash of userId + rawSubmission for idempotency dedup."""
    payload = f"{user_id}:{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Rate limit check
# ---------------------------------------------------------------------------


async def _check_rate_limits(db, user_id: str) -> None:
    """
    Check hourly + daily submission counts for the user.
    Raises 429 if either limit is exceeded.
    """
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)

    hourly_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM "BackfillTrip"
        WHERE "userId" = $1
          AND "createdAt" >= $2
        """,
        user_id,
        one_hour_ago,
    )

    if hourly_count >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": (
                    f"Maximum {RATE_LIMIT_PER_HOUR} backfill submissions per hour. "
                    "Please try again later."
                ),
            },
        )

    daily_count = await db.fetchval(
        """
        SELECT COUNT(*) FROM "BackfillTrip"
        WHERE "userId" = $1
          AND "createdAt" >= $2
        """,
        user_id,
        one_day_ago,
    )

    if daily_count >= RATE_LIMIT_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": (
                    f"Maximum {RATE_LIMIT_PER_DAY} backfill submissions per 24 hours. "
                    "Please try again later."
                ),
            },
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/submit",
    response_model=BackfillSubmitResponse,
    status_code=202,
    summary="Submit a free-form trip diary for backfill processing",
)
async def submit_backfill(
    body: BackfillSubmitRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Accepts a free-form travel diary, creates a BackfillTrip row, and
    kicks off the 5-stage async pipeline via FastAPI BackgroundTasks.

    Returns immediately with { backfill_trip_id, status: "processing" }.
    The pipeline runs in the background; poll the trip status separately.

    HTTP errors:
    - 400 if text is empty or X-User-Id header is missing
    - 401 if X-Service-Token is invalid
    - 422 if text exceeds 10,000 characters
    - 429 if rate limit exceeded (5/hour or 20/day)
    """
    db = request.app.state.db

    # Auth
    user_id = _verify_service_token(request)

    # Rate limits
    await _check_rate_limits(db, user_id)

    # Idempotency check: hash of (userId + rawSubmission)
    dedup_hash = _submission_hash(user_id, body.text)
    existing = await db.fetchrow(
        """
        SELECT id, status FROM "BackfillTrip"
        WHERE "userId" = $1
          AND "tripNote" = $2
        LIMIT 1
        """,
        user_id,
        dedup_hash,  # we store hash in tripNote as a lightweight dedup field
    )
    if existing:
        logger.info(
            "backfill/submit: duplicate submission from user=%s existing=%s",
            user_id,
            existing["id"],
        )
        return {
            "backfill_trip_id": str(existing["id"]),
            "status": str(existing["status"]),
        }

    # Derive city from hint — stored on BackfillLeg, not BackfillTrip
    city = (body.city_hint or "unknown").strip()
    country = "unknown"  # enriched by pipeline if needed

    now = datetime.now(timezone.utc)
    backfill_trip_id = str(uuid4())
    backfill_leg_id = str(uuid4())

    # Create BackfillTrip row — status=processing immediately
    await db.execute(
        """
        INSERT INTO "BackfillTrip" (
            id, "userId",
            "rawSubmission", "confidenceTier",
            source, "tripNote", "contextTag", status,
            "createdAt", "updatedAt"
        ) VALUES (
            $1, $2, $3, 'tier_4',
            'freeform', $4, $5, 'processing',
            $6, $6
        )
        """,
        backfill_trip_id,
        user_id,
        body.text,
        dedup_hash,  # stored in tripNote for dedup lookup
        body.context_tag,
        now,
    )

    # Create the primary leg (position=0) carrying city/country for this submission
    await db.execute(
        """
        INSERT INTO "BackfillLeg" (
            id, "backfillTripId", position, city, country, "createdAt"
        ) VALUES (
            $1, $2, 0, $3, $4, $5
        )
        """,
        backfill_leg_id,
        backfill_trip_id,
        city,
        country,
        now,
    )

    logger.info(
        "backfill/submit: created trip=%s leg=%s user=%s city=%s",
        backfill_trip_id,
        backfill_leg_id,
        user_id,
        city,
    )

    # Kick off background pipeline — returns immediately to caller
    background_tasks.add_task(
        _run_pipeline_safe,
        pool=db,
        backfill_trip_id=backfill_trip_id,
    )

    return {
        "backfill_trip_id": backfill_trip_id,
        "status": "processing",
    }


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------


async def _run_pipeline_safe(pool, backfill_trip_id: str) -> None:
    """
    Wraps process_backfill in a try/except so background task failures
    don't crash the worker — they're logged and the trip status stays
    as whatever stage it last wrote.
    """
    try:
        await process_backfill(pool, backfill_trip_id)
    except Exception as exc:
        logger.exception(
            "backfill pipeline uncaught exception trip=%s: %s",
            backfill_trip_id,
            exc,
        )
        # Best-effort: mark the trip as rejected so it doesn't stay in limbo
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE "BackfillTrip"
                    SET status = 'rejected',
                        "rejectionReason" = $1,
                        "updatedAt" = NOW()
                    WHERE id = $2
                      AND status NOT IN ('complete', 'rejected')
                    """,
                    "pipeline_error: unexpected exception",
                    backfill_trip_id,
                )
        except Exception as inner:
            logger.error(
                "backfill: failed to mark trip %s as rejected after pipeline crash: %s",
                backfill_trip_id,
                inner,
            )
