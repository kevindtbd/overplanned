"""
RawEvent batch ingestion endpoint.

POST /events/batch
- Accepts array of RawEvent payloads (max 1000 per batch)
- clientEventId-based dedup: ON CONFLICT (userId, clientEventId) DO NOTHING
- Request body size limit enforced at middleware level (1MB)
- Returns count of inserted vs skipped
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, field_validator

from services.api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


class RawEventPayload(BaseModel):
    """Single raw event in a batch submission."""

    userId: str
    sessionId: str
    tripId: str | None = None
    activityNodeId: str | None = None
    clientEventId: str | None = None
    eventType: str
    intentClass: str = Field(pattern=r"^(explicit|implicit|contextual)$")
    surface: str | None = None
    payload: dict = Field(default_factory=dict)
    platform: str | None = None
    screenWidth: int | None = None
    networkType: str | None = None

    @field_validator("eventType")
    @classmethod
    def event_type_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("eventType must not be empty")
        return v


class BatchRequest(BaseModel):
    events: list[RawEventPayload] = Field(max_length=settings.events_batch_max_size)


class BatchResponse(BaseModel):
    inserted: int
    skipped: int
    total: int


@router.post("/batch")
async def ingest_events(body: BatchRequest, request: Request) -> dict:
    if not body.events:
        return {
            "success": True,
            "data": {"inserted": 0, "skipped": 0, "total": 0},
            "requestId": request.state.request_id,
        }

    db = request.app.state.db
    now = datetime.now(timezone.utc)

    # Build values for bulk insert with ON CONFLICT DO NOTHING
    inserted = 0
    skipped = 0

    # Process in a single transaction
    async with db.transaction():
        for i, event in enumerate(body.events):
            event_id = str(uuid4())
            try:
                await db.execute(
                    """
                    INSERT INTO "RawEvent" (
                        id, "userId", "sessionId", "tripId", "activityNodeId",
                        "clientEventId", "eventType", "intentClass", surface,
                        payload, platform, "screenWidth", "networkType", "createdAt"
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                    )
                    ON CONFLICT ("userId", "clientEventId") DO NOTHING
                    """,
                    event_id,
                    event.userId,
                    event.sessionId,
                    event.tripId,
                    event.activityNodeId,
                    event.clientEventId,
                    event.eventType,
                    event.intentClass,
                    event.surface,
                    event.payload,
                    event.platform,
                    event.screenWidth,
                    event.networkType,
                    now,
                )
                inserted += 1
            except Exception as exc:
                logger.warning("Event insert failed for event %d: %s", i, exc)
                skipped += 1

    # Dedup count: events with clientEventId that were skipped
    total = len(body.events)
    actual_skipped = total - inserted

    return {
        "success": True,
        "data": {
            "inserted": inserted,
            "skipped": actual_skipped,
            "total": total,
        },
        "requestId": request.state.request_id,
    }
