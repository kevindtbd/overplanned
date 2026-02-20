"""
PostTrip completion logic.
Auto-transitions trips to completed status when endDate passes.
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from prisma import Prisma
from prisma.models import Trip


async def should_complete_trip(trip: Trip) -> bool:
    """
    Check if a trip should be auto-completed based on timezone-aware endDate.

    Args:
        trip: Trip instance with endDate and timezone

    Returns:
        True if trip.endDate has passed in the trip's timezone
    """
    if not trip.endDate or not trip.timezone:
        return False

    if trip.status == "completed":
        return False

    # Convert endDate to trip's timezone
    trip_tz = ZoneInfo(trip.timezone)
    end_dt = trip.endDate.replace(tzinfo=trip_tz)

    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Convert end_dt to UTC for comparison
    end_utc = end_dt.astimezone(timezone.utc)

    return now_utc > end_utc


async def mark_trip_completed(
    db: Prisma,
    trip_id: str,
    completed_at: Optional[datetime] = None
) -> Trip:
    """
    Mark a trip as completed (manual or auto).

    Args:
        db: Prisma client instance
        trip_id: Trip ID to complete
        completed_at: Optional completion timestamp (defaults to now)

    Returns:
        Updated Trip instance
    """
    if completed_at is None:
        completed_at = datetime.now(timezone.utc)

    trip = await db.trip.update(
        where={"id": trip_id},
        data={
            "status": "completed",
            "completedAt": completed_at,
        }
    )

    return trip


async def auto_complete_trips(db: Prisma) -> list[str]:
    """
    Scheduled job: check all active trips and auto-complete those past endDate.

    Args:
        db: Prisma client instance

    Returns:
        List of trip IDs that were auto-completed
    """
    # Fetch all non-completed trips with endDate set
    trips = await db.trip.find_many(
        where={
            "status": {"not": "completed"},
            "endDate": {"not": None},
            "timezone": {"not": None},
        }
    )

    completed_ids = []

    for trip in trips:
        if await should_complete_trip(trip):
            await mark_trip_completed(db, trip.id)
            completed_ids.append(trip.id)

    return completed_ids


async def run_completion_check():
    """
    Hourly scheduled job entry point.
    Connects to DB, runs completion check, disconnects.
    """
    db = Prisma()
    await db.connect()

    try:
        completed = await auto_complete_trips(db)
        print(f"Auto-completed {len(completed)} trips: {completed}")
    finally:
        await db.disconnect()
