"""
POST /prompt — Natural language mid-trip change processing.

Accepts a user's free-text intent, parses it via Haiku (with keyword fallback),
and returns a structured PivotTrigger classification.

Auth: X-User-Id header required (set by Next.js middleware).
Rate limit: LLM bucket (5 req/min per user).

Security:
- Input capped at 200 characters server-side (client also enforces this).
- PromptParser screens for injection patterns before any Haiku call.
- No ActivityNode data or user persona enters the LLM context.
- All calls logged for security audit.
"""

from __future__ import annotations

import logging
import uuid

import anthropic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from services.api.pivot.prompt_parser import PromptParser, MAX_INPUT_LENGTH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompt", tags=["prompt"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class PromptRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_INPUT_LENGTH,
        description="Natural language mid-trip change request (200 char max)",
    )
    tripId: str = Field(..., min_length=1, description="UUID of the active Trip")
    userId: str = Field(..., min_length=1, description="UUID of the requesting user")
    sessionId: str | None = Field(default=None, description="Client session ID for audit trail")

    @field_validator("tripId", "userId")
    @classmethod
    def must_be_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"Must be a valid UUID, got: {v!r}") from exc
        return v

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must not be empty or whitespace-only")
        # Hard-cap server-side regardless of what Pydantic max_length allows
        return stripped[:MAX_INPUT_LENGTH]


class PromptResponse(BaseModel):
    success: bool
    data: dict
    requestId: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=PromptResponse)
async def process_prompt(body: PromptRequest, request: Request) -> dict:
    """
    Parse a natural language mid-trip request into a structured PivotTrigger intent.

    Returns:
        classification: one of weather_change | venue_closure | time_overrun | mood_shift | custom
        confidence: float 0.0-1.0
        entities: extracted location / time / activity_type
        method: haiku | keyword | default | rejected

    HTTP errors:
    - 422 on validation failure (empty text, bad UUIDs)
    - 500 on unexpected parser failure (should not happen — parser is designed to never raise)
    """
    db = request.app.state.db
    request_id: str = request.state.request_id

    # Build parser — one per request
    anthropic_client = anthropic.AsyncAnthropic()

    parser = PromptParser(
        anthropic_client=anthropic_client,
        db=db,
    )

    try:
        result = await parser.parse(
            raw_text=body.text,
            user_id=body.userId,
            trip_id=body.tripId,
            session_id=body.sessionId,
        )
    except Exception as exc:
        logger.exception(
            "PromptParser raised unexpectedly: trip=%s user=%s",
            body.tripId,
            body.userId,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PROMPT_PARSE_FAILED",
                "message": "Failed to parse prompt. Please try again.",
            },
        ) from exc

    return {
        "success": True,
        "data": result.to_dict(),
        "requestId": request_id,
    }
