"""
Cascade evaluation — re-solve downstream same-day slots after a pivot swap.

Rules:
  - Scope: same-day slots ONLY (same dayNumber as the swapped slot).
  - Affected: slots with sortOrder > swapped slot's sortOrder that are not locked.
  - Cross-day impact is a separate PivotEvent (not automatic cascade).
  - Update: sortOrder remains the same; startTime / endTime are shifted
    based on the new slot's duration delta.
  - Timezone-aware: all datetimes stored as UTC, converted for display using
    Trip.timezone (IANA). Duration delta calculation happens in UTC.

Output:
  CascadeResult listing affected slot IDs and their new start/end times.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SlotSnapshot:
    """Minimal snapshot of an ItinerarySlot for cascade math."""

    id: str
    day_number: int
    sort_order: int
    start_time: datetime | None
    end_time: datetime | None
    duration_minutes: int | None
    is_locked: bool
    slot_type: str
    status: str


@dataclass
class SlotUpdate:
    """Proposed update for a downstream slot after cascade."""

    slot_id: str
    new_start_time: datetime | None
    new_end_time: datetime | None
    sort_order: int


@dataclass
class CascadeResult:
    """Result of cascade evaluation for a single pivot."""

    pivot_slot_id: str
    day_number: int
    affected_slot_ids: list[str]
    updates: list[SlotUpdate]
    cross_day_impact: bool = False
    cross_day_pivot_required: bool = False
    warning: str | None = None


@dataclass
class CascadeSummary:
    """DB-persisted summary of which slots were updated."""

    slots_updated: int
    delta_minutes: int
    affected_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core cascade logic
# ---------------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duration_delta(
    old_duration: int | None,
    new_duration: int | None,
) -> int:
    """
    Return the signed difference in minutes between new and old duration.
    Positive = new slot takes longer, shifts downstream later.
    Negative = new slot is shorter, gives time back.
    Returns 0 if either duration is unknown.
    """
    if old_duration is None or new_duration is None:
        return 0
    return new_duration - old_duration


def evaluate_cascade(
    *,
    swapped_slot: SlotSnapshot,
    new_duration_minutes: int | None,
    same_day_slots: list[SlotSnapshot],
    trip_timezone: str,
) -> CascadeResult:
    """
    Evaluate cascade impact after a slot swap.

    Args:
        swapped_slot: The slot that was just pivoted/swapped.
        new_duration_minutes: Duration of the incoming ActivityNode. May be
            None if unknown — cascade aborts with a warning in that case.
        same_day_slots: All slots on the same day (including swapped_slot),
            fetched from DB before calling this function.
        trip_timezone: IANA timezone string for the trip (e.g. "Asia/Tokyo").

    Returns:
        CascadeResult with list of SlotUpdate objects to apply.
    """
    try:
        tz = pytz.timezone(trip_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone %r — falling back to UTC", trip_timezone)
        tz = pytz.utc

    delta_minutes = _duration_delta(swapped_slot.duration_minutes, new_duration_minutes)

    # Downstream = same day, higher sortOrder, not locked
    downstream = sorted(
        [
            s
            for s in same_day_slots
            if s.day_number == swapped_slot.day_number
            and s.sort_order > swapped_slot.sort_order
            and not s.is_locked
            and s.status not in ("completed", "skipped")
            and s.id != swapped_slot.id
        ],
        key=lambda s: s.sort_order,
    )

    if not downstream:
        return CascadeResult(
            pivot_slot_id=swapped_slot.id,
            day_number=swapped_slot.day_number,
            affected_slot_ids=[],
            updates=[],
            warning="No downstream slots to cascade.",
        )

    if delta_minutes == 0:
        # No time change — nothing to shift
        return CascadeResult(
            pivot_slot_id=swapped_slot.id,
            day_number=swapped_slot.day_number,
            affected_slot_ids=[],
            updates=[],
            warning="Duration unchanged — no cascade needed.",
        )

    delta = timedelta(minutes=delta_minutes)
    updates: list[SlotUpdate] = []
    affected_ids: list[str] = []

    for slot in downstream:
        new_start: datetime | None = None
        new_end: datetime | None = None

        if slot.start_time is not None:
            shifted_start = _to_utc(slot.start_time) + delta
            new_start = shifted_start

        if slot.end_time is not None:
            shifted_end = _to_utc(slot.end_time) + delta
            new_end = shifted_end

        updates.append(
            SlotUpdate(
                slot_id=slot.id,
                new_start_time=new_start,
                new_end_time=new_end,
                sort_order=slot.sort_order,  # sortOrder unchanged
            )
        )
        affected_ids.append(slot.id)

    logger.info(
        "Cascade: swapped=%s day=%d delta=%+dmin affected=%d",
        swapped_slot.id,
        swapped_slot.day_number,
        delta_minutes,
        len(affected_ids),
    )

    return CascadeResult(
        pivot_slot_id=swapped_slot.id,
        day_number=swapped_slot.day_number,
        affected_slot_ids=affected_ids,
        updates=updates,
    )


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


async def apply_cascade(
    db: Any,
    result: CascadeResult,
) -> CascadeSummary:
    """
    Persist cascade updates to ItinerarySlot rows.

    Runs in a single transaction. Each update only touches startTime and endTime —
    sortOrder, slotType, and all other fields are left intact.

    Args:
        db: asyncpg connection/pool.
        result: Output of evaluate_cascade().

    Returns:
        CascadeSummary with count of rows updated.
    """
    if not result.updates:
        return CascadeSummary(slots_updated=0, delta_minutes=0, affected_ids=[])

    updated_count = 0

    async with db.transaction():
        for update in result.updates:
            try:
                await db.execute(
                    """
                    UPDATE itinerary_slots
                    SET
                        "startTime" = $1,
                        "endTime"   = $2,
                        "updatedAt" = NOW()
                    WHERE id = $3
                      AND "isLocked" = false
                      AND status NOT IN ('completed', 'skipped')
                    """,
                    update.new_start_time,
                    update.new_end_time,
                    update.slot_id,
                )
                updated_count += 1
            except Exception:
                logger.exception(
                    "Cascade update failed for slot=%s", update.slot_id
                )

    return CascadeSummary(
        slots_updated=updated_count,
        delta_minutes=sum(
            int((u.new_start_time - _to_utc(result.updates[0].new_start_time)).total_seconds() / 60)
            if u.new_start_time and result.updates[0].new_start_time else 0
            for u in result.updates
        ),
        affected_ids=result.affected_slot_ids,
    )


# ---------------------------------------------------------------------------
# DB fetch helpers
# ---------------------------------------------------------------------------


async def fetch_same_day_slots(
    db: Any,
    trip_id: str,
    day_number: int,
) -> list[SlotSnapshot]:
    """
    Fetch all ItinerarySlot rows for a given trip day.
    Returns SlotSnapshot list sorted by sortOrder ascending.
    """
    rows = await db.fetch(
        """
        SELECT
            id,
            "dayNumber",
            "sortOrder",
            "startTime",
            "endTime",
            "durationMinutes",
            "isLocked",
            "slotType",
            status
        FROM itinerary_slots
        WHERE "tripId" = $1
          AND "dayNumber" = $2
        ORDER BY "sortOrder" ASC
        """,
        trip_id,
        day_number,
    )

    return [
        SlotSnapshot(
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
        for row in rows
    ]


async def check_cross_day_impact(
    db: Any,
    trip_id: str,
    day_number: int,
    delta_minutes: int,
) -> bool:
    """
    Determine if a time delta on day N spills into day N+1.

    Checks whether any slot on the next day starts before the last
    slot on day N ends after cascade. If so, returns True — a new
    PivotEvent should be created by the caller (not auto-cascaded).
    """
    if delta_minutes <= 0:
        return False

    # Find the last scheduled slot on this day
    last_slot = await db.fetchrow(
        """
        SELECT "endTime"
        FROM itinerary_slots
        WHERE "tripId" = $1
          AND "dayNumber" = $2
          AND "endTime" IS NOT NULL
          AND status NOT IN ('completed', 'skipped')
        ORDER BY "sortOrder" DESC
        LIMIT 1
        """,
        trip_id,
        day_number,
    )

    if not last_slot or not last_slot["endTime"]:
        return False

    new_last_end = _to_utc(last_slot["endTime"]) + timedelta(minutes=delta_minutes)

    # Check if any slot on the next day starts before our new end time
    next_day_conflict = await db.fetchrow(
        """
        SELECT id
        FROM itinerary_slots
        WHERE "tripId" = $1
          AND "dayNumber" = $2
          AND "startTime" IS NOT NULL
          AND "startTime" < $3
          AND status NOT IN ('completed', 'skipped')
        LIMIT 1
        """,
        trip_id,
        day_number + 1,
        new_last_end,
    )

    return next_day_conflict is not None
