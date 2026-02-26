"""
PostTrip completion logic.
Auto-transitions trips to completed status when endDate passes.

On completion, each ItinerarySlot is classified via the SlotOutcomeClassifier
(Phase 1.1) so the ``completionSignal`` column is populated for downstream ML.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import Trip, ItinerarySlot
from services.api.posttrip.slot_classifier import classify_slot_outcome

logger = logging.getLogger(__name__)


async def should_complete_trip(trip) -> bool:
    """
    Check if a trip should be auto-completed based on timezone-aware endDate.

    Args:
        trip: Trip instance (SA model or dict-like) with endDate and timezone

    Returns:
        True if trip.endDate has passed in the trip's timezone
    """
    end_date = trip.endDate if hasattr(trip, "endDate") else trip.get("endDate")
    tz = trip.timezone if hasattr(trip, "timezone") else trip.get("timezone")
    status = trip.status if hasattr(trip, "status") else trip.get("status")

    if not end_date or not tz:
        return False

    if status == "completed":
        return False

    # Convert endDate to trip's timezone
    trip_tz = ZoneInfo(tz)
    end_dt = end_date.replace(tzinfo=trip_tz)

    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Convert end_dt to UTC for comparison
    end_utc = end_dt.astimezone(timezone.utc)

    return now_utc > end_utc


async def mark_trip_completed(
    session: AsyncSession,
    trip_id: str,
    completed_at: Optional[datetime] = None,
) -> None:
    """
    Mark a trip as completed (manual or auto).

    Args:
        session: SA async session
        trip_id: Trip ID to complete
        completed_at: Optional completion timestamp (defaults to now)
    """
    if completed_at is None:
        completed_at = datetime.now(timezone.utc)

    stmt = (
        update(Trip)
        .where(Trip.id == trip_id)
        .values(status="completed", completedAt=completed_at)
    )
    await session.execute(stmt)
    await session.commit()

    # Phase 1.1: classify slot outcomes now that the trip is done
    await classify_trip_slots(session, trip_id)


async def classify_trip_slots(session: AsyncSession, trip_id: str) -> int:
    """
    Classify all ItinerarySlots for a completed trip and persist the result.

    Writes the ``completionSignal`` enum column on each slot so the training-
    data pipeline has a clean label without needing to re-derive it.
    """
    stmt = select(ItinerarySlot).where(ItinerarySlot.tripId == trip_id)
    result = await session.execute(stmt)
    slots = result.scalars().all()

    updated = 0
    for slot in slots:
        slot_dict = {
            "pivotEventId": slot.pivotEventId,
            "wasSwapped": slot.wasSwapped,
            "status": slot.status,
        }
        outcome = classify_slot_outcome(slot_dict)

        try:
            update_stmt = (
                update(ItinerarySlot)
                .where(ItinerarySlot.id == slot.id)
                .values(completionSignal=outcome)
            )
            await session.execute(update_stmt)
            updated += 1
        except Exception:
            logger.exception(
                "Failed to write completionSignal for slot %s (trip %s)",
                slot.id,
                trip_id,
            )

    await session.commit()

    logger.info(
        "classify_trip_slots: trip=%s classified %d/%d slots",
        trip_id,
        updated,
        len(slots),
    )
    return updated


async def auto_complete_trips(session: AsyncSession) -> list[str]:
    """
    Scheduled job: check all active trips and auto-complete those past endDate.

    Args:
        session: SA async session

    Returns:
        List of trip IDs that were auto-completed
    """
    # Fetch all non-completed trips with endDate set
    stmt = select(Trip).where(
        and_(
            Trip.status != "completed",
            Trip.endDate.isnot(None),
            Trip.timezone.isnot(None),
        )
    )
    result = await session.execute(stmt)
    trips = result.scalars().all()

    completed_ids = []

    for trip in trips:
        if await should_complete_trip(trip):
            await mark_trip_completed(session, trip.id)
            completed_ids.append(trip.id)

    return completed_ids


async def run_completion_check():
    """
    Hourly scheduled job entry point.
    Connects to DB, runs completion check, disconnects.
    """
    from services.api.db.engine import standalone_session

    async with standalone_session() as session:
        completed = await auto_complete_trips(session)
        print(f"Auto-completed {len(completed)} trips: {completed}")
