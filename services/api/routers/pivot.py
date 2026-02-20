"""
POST /pivot/cascade     — Re-solve same-day downstream slots after a pivot swap.
POST /microstops/suggest — Propose micro-stops for a trip day's transit windows.

Auth: expects X-User-Id header (set by Next.js middleware / API gateway).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from services.api.pivot.cascade import (
    CascadeResult,
    SlotSnapshot,
    apply_cascade,
    check_cross_day_impact,
    evaluate_cascade,
    fetch_same_day_slots,
)
from services.api.microstops.service import MicroStopService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pivot"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return user_id


def _validate_uuid(value: str, field: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must be a valid UUID")
    return value


# ---------------------------------------------------------------------------
# Cascade endpoint
# ---------------------------------------------------------------------------


class CascadeRequest(BaseModel):
    tripId: str = Field(..., min_length=36, max_length=36)
    slotId: str = Field(..., min_length=36, max_length=36)
    dayNumber: int = Field(..., ge=1)
    newDurationMinutes: int | None = Field(
        default=None,
        ge=5,
        le=480,
        description="Duration of the incoming ActivityNode. Omit if unknown.",
    )

    @field_validator("tripId", "slotId")
    @classmethod
    def must_be_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"Must be a valid UUID, got: {v!r}") from exc
        return v


class CascadeResponseData(BaseModel):
    pivotSlotId: str
    dayNumber: int
    affectedSlotCount: int
    slotsUpdated: int
    crossDayImpact: bool
    crossDayPivotRequired: bool
    warning: str | None


@router.post("/pivot/cascade")
async def run_cascade(body: CascadeRequest, request: Request) -> dict:
    """
    Evaluate and apply cascade time shifts to downstream slots on the same day.

    Only affects unlocked, non-terminal slots with sortOrder greater than
    the swapped slot. Cross-day impact is detected and flagged — it is NOT
    automatically cascaded.
    """
    _require_user_id(request)
    db = request.app.state.db

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Fetch the swapped slot
    row = await db.fetchrow(
        """
        SELECT
            id, "dayNumber", "sortOrder",
            "startTime", "endTime", "durationMinutes",
            "isLocked", "slotType", status
        FROM "ItinerarySlot"
        WHERE id = $1 AND "tripId" = $2
        """,
        body.slotId,
        body.tripId,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Slot not found")

    swapped_slot = SlotSnapshot(
        id=row["id"],
        day_number=row["dayNumber"],
        sort_order=row["sortOrder"],
        start_time=row["startTime"],
        end_time=row["endTime"],
        duration_minutes=row["durationMinutes"],
        is_locked=row["isLocked"],
        slot_type=row["slotType"],
        status=row["status"],
    )

    # Fetch trip timezone
    trip_row = await db.fetchrow(
        'SELECT timezone FROM "Trip" WHERE id = $1',
        body.tripId,
    )
    if not trip_row:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip_timezone: str = trip_row["timezone"]

    # Fetch same-day slots
    same_day = await fetch_same_day_slots(db, body.tripId, body.dayNumber)

    # Evaluate cascade (pure function — no DB writes yet)
    cascade_result: CascadeResult = evaluate_cascade(
        swapped_slot=swapped_slot,
        new_duration_minutes=body.newDurationMinutes,
        same_day_slots=same_day,
        trip_timezone=trip_timezone,
    )

    # Check cross-day impact before applying
    cross_day = False
    if cascade_result.updates and body.newDurationMinutes:
        delta = (body.newDurationMinutes or 0) - (swapped_slot.duration_minutes or 0)
        if delta > 0:
            cross_day = await check_cross_day_impact(
                db, body.tripId, body.dayNumber, delta
            )
        cascade_result.cross_day_impact = cross_day
        cascade_result.cross_day_pivot_required = cross_day

    # Apply cascade writes
    summary = await apply_cascade(db, cascade_result)

    return {
        "success": True,
        "data": CascadeResponseData(
            pivotSlotId=cascade_result.pivot_slot_id,
            dayNumber=cascade_result.day_number,
            affectedSlotCount=len(cascade_result.affected_slot_ids),
            slotsUpdated=summary.slots_updated,
            crossDayImpact=cascade_result.cross_day_impact,
            crossDayPivotRequired=cascade_result.cross_day_pivot_required,
            warning=cascade_result.warning,
        ).model_dump(),
        "requestId": request.state.request_id,
    }


# ---------------------------------------------------------------------------
# Micro-stops endpoint
# ---------------------------------------------------------------------------


class MicroStopRequest(BaseModel):
    tripId: str = Field(..., min_length=36, max_length=36)
    userId: str = Field(..., min_length=36, max_length=36)
    dayNumber: int = Field(..., ge=1)
    sessionId: str | None = None

    @field_validator("tripId", "userId")
    @classmethod
    def must_be_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"Must be a valid UUID, got: {v!r}") from exc
        return v


@router.post("/microstops/suggest")
async def suggest_microstops(body: MicroStopRequest, request: Request) -> dict:
    """
    Evaluate transit slots for a trip day and propose micro-stop suggestions.

    Inserts lightweight flex ItinerarySlot rows (status=proposed) immediately
    after eligible transit slots where interesting nodes are found within 200m
    of the transit path. Maximum one suggestion per transit segment.

    Requires PostGIS extension + idx_activity_nodes_location GIST index.
    """
    _require_user_id(request)
    db = request.app.state.db

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    service = MicroStopService(db=db)

    result = await service.suggest_for_day(
        trip_id=body.tripId,
        day_number=body.dayNumber,
        user_id=body.userId,
        session_id=body.sessionId,
    )

    return {
        "success": True,
        "data": {
            "tripId": result.trip_id,
            "dayNumber": result.day_number,
            "transitSegmentsEvaluated": result.transit_segments_evaluated,
            "insertedCount": result.inserted_count,
            "insertions": [
                {
                    "newSlotId": ins.new_slot_id,
                    "activityNodeId": ins.activity_node_id,
                    "activityName": ins.activity_name,
                    "insertedAfterSlotId": ins.inserted_after_slot_id,
                    "sortOrder": ins.sort_order,
                    "durationMinutes": ins.duration_minutes,
                    "convergenceScore": ins.convergence_score,
                }
                for ins in result.insertions
            ],
            "warnings": result.warnings,
        },
        "requestId": request.state.request_id,
    }
