"""
MicroStopService — orchestrates proximity-based micro-stop suggestions.

Flow:
  1. Find all transit slots for a given trip day that have both an origin
     and destination ActivityNode with known lat/lon.
  2. For each transit slot, call spatial.find_nodes_along_path().
  3. Filter out nodes already in the itinerary.
  4. For each candidate, create a lightweight ItinerarySlot (slotType=flex,
     durationMinutes=15-30, status=proposed) inserted after the transit slot.
  5. Log a BehavioralSignal (slot_swap with value 0.0 — suggestion shown, not chosen).
  6. Return a MicroStopResult summary.

Design constraints:
  - Micro-stops are NEVER auto-confirmed — always proposed.
  - Max 1 micro-stop suggestion per transit segment.
  - Only inserted when transit slot has no existing flex slot immediately after it.
  - Does not run for locked transit slots.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from services.api.microstops.spatial import (
    SpatialCandidate,
    find_nodes_along_path,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TransitSegment:
    """A transit slot with resolved origin + destination coordinates."""

    slot_id: str
    sort_order: int
    start_time: datetime | None
    end_time: datetime | None
    duration_minutes: int | None
    origin_lat: float
    origin_lon: float
    destination_lat: float
    destination_lon: float
    origin_node_id: str | None
    destination_node_id: str | None


@dataclass
class MicroStopInsertion:
    """A micro-stop slot that was inserted into the itinerary."""

    new_slot_id: str
    activity_node_id: str
    activity_name: str
    inserted_after_slot_id: str
    sort_order: int
    start_time: datetime | None
    end_time: datetime | None
    duration_minutes: int
    convergence_score: float | None


@dataclass
class MicroStopResult:
    """Summary returned by MicroStopService.suggest_for_day()."""

    trip_id: str
    day_number: int
    transit_segments_evaluated: int
    insertions: list[MicroStopInsertion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def inserted_count(self) -> int:
        return len(self.insertions)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MicroStopService:
    """
    Proximity-based micro-stop suggestion for mid-trip transit windows.

    Injected dependencies for testability:
      db  — asyncpg connection / pool (same pattern as GenerationEngine)
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    async def suggest_for_day(
        self,
        *,
        trip_id: str,
        day_number: int,
        user_id: str,
        session_id: str | None = None,
    ) -> MicroStopResult:
        """
        Evaluate all transit slots on a given day and propose micro-stops.

        Returns a MicroStopResult with all inserted slot IDs.
        Does NOT raise on partial failures — warnings are collected.
        """
        result = MicroStopResult(
            trip_id=trip_id,
            day_number=day_number,
            transit_segments_evaluated=0,
        )
        session_id = session_id or str(uuid.uuid4())

        # 1. Fetch all transit slots with spatial data
        segments = await self._fetch_transit_segments(trip_id, day_number)
        result.transit_segments_evaluated = len(segments)

        if not segments:
            result.warnings.append("No eligible transit segments found.")
            return result

        # 2. Fetch current sort_order ceiling for the day (to avoid collisions)
        max_sort_order = await self._fetch_max_sort_order(trip_id, day_number)

        for segment in segments:
            try:
                insertion = await self._evaluate_segment(
                    trip_id=trip_id,
                    day_number=day_number,
                    segment=segment,
                    current_max_sort_order=max_sort_order,
                )
                if insertion:
                    result.insertions.append(insertion)
                    max_sort_order = insertion.sort_order + 1
            except Exception as exc:
                logger.exception(
                    "Micro-stop evaluation failed for segment slot=%s", segment.slot_id
                )
                result.warnings.append(
                    f"Segment {segment.slot_id} failed: {exc}"
                )

        logger.info(
            "Micro-stops: trip=%s day=%d segments=%d inserted=%d",
            trip_id,
            day_number,
            result.transit_segments_evaluated,
            result.inserted_count,
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_transit_segments(
        self,
        trip_id: str,
        day_number: int,
    ) -> list[TransitSegment]:
        """
        Fetch transit slots with origin and destination node coordinates.

        We look at adjacent slot pairs where:
          - The current slot is type=transit, not locked, not terminal
          - The previous slot has an activityNodeId with known lat/lon (origin)
          - The next slot has an activityNodeId with known lat/lon (destination)
        """
        rows = await self._db.fetch(
            """
            WITH ranked AS (
                SELECT
                    s.id,
                    s."sortOrder",
                    s."slotType",
                    s."startTime",
                    s."endTime",
                    s."durationMinutes",
                    s."isLocked",
                    s.status,
                    LAG(s."activityNodeId") OVER (ORDER BY s."sortOrder") AS origin_node_id,
                    LEAD(s."activityNodeId") OVER (ORDER BY s."sortOrder") AS dest_node_id
                FROM "ItinerarySlot" s
                WHERE s."tripId" = $1
                  AND s."dayNumber" = $2
            )
            SELECT
                r.id AS slot_id,
                r."sortOrder",
                r."startTime",
                r."endTime",
                r."durationMinutes",
                r.origin_node_id,
                r.dest_node_id,
                orig.latitude AS origin_lat,
                orig.longitude AS origin_lon,
                dest.latitude AS dest_lat,
                dest.longitude AS dest_lon
            FROM ranked r
            LEFT JOIN "ActivityNode" orig ON orig.id = r.origin_node_id
            LEFT JOIN "ActivityNode" dest ON dest.id = r.dest_node_id
            WHERE
                r."slotType" = 'transit'
                AND r."isLocked" = false
                AND r.status NOT IN ('completed', 'skipped')
                AND orig.latitude IS NOT NULL
                AND orig.longitude IS NOT NULL
                AND dest.latitude IS NOT NULL
                AND dest.longitude IS NOT NULL
            ORDER BY r."sortOrder" ASC
            """,
            trip_id,
            day_number,
        )

        return [
            TransitSegment(
                slot_id=row["slot_id"],
                sort_order=row["sortOrder"],
                start_time=row["startTime"],
                end_time=row["endTime"],
                duration_minutes=row["durationMinutes"],
                origin_lat=row["origin_lat"],
                origin_lon=row["origin_lon"],
                destination_lat=row["dest_lat"],
                destination_lon=row["dest_lon"],
                origin_node_id=row["origin_node_id"],
                destination_node_id=row["dest_node_id"],
            )
            for row in rows
        ]

    async def _has_existing_flex_after(
        self,
        trip_id: str,
        day_number: int,
        sort_order: int,
    ) -> bool:
        """Check if a flex slot already exists immediately after sort_order."""
        row = await self._db.fetchrow(
            """
            SELECT id FROM "ItinerarySlot"
            WHERE "tripId" = $1
              AND "dayNumber" = $2
              AND "sortOrder" = $3
              AND "slotType" = 'flex'
            LIMIT 1
            """,
            trip_id,
            day_number,
            sort_order + 1,
        )
        return row is not None

    async def _fetch_max_sort_order(self, trip_id: str, day_number: int) -> int:
        """Return the current maximum sortOrder for the day."""
        row = await self._db.fetchrow(
            """
            SELECT COALESCE(MAX("sortOrder"), 0) AS max_order
            FROM "ItinerarySlot"
            WHERE "tripId" = $1 AND "dayNumber" = $2
            """,
            trip_id,
            day_number,
        )
        return int(row["max_order"]) if row else 0

    async def _evaluate_segment(
        self,
        *,
        trip_id: str,
        day_number: int,
        segment: TransitSegment,
        current_max_sort_order: int,
    ) -> MicroStopInsertion | None:
        """
        Evaluate a single transit segment and insert a micro-stop if appropriate.
        Returns the insertion record, or None if no suitable candidate found.
        """
        # Skip if a flex slot already follows this transit
        if await self._has_existing_flex_after(trip_id, day_number, segment.sort_order):
            logger.debug(
                "Skipping segment %s — flex slot already follows", segment.slot_id
            )
            return None

        # Find spatial candidates along the transit path
        candidates: list[SpatialCandidate] = await find_nodes_along_path(
            db=self._db,
            origin_lat=segment.origin_lat,
            origin_lon=segment.origin_lon,
            destination_lat=segment.destination_lat,
            destination_lon=segment.destination_lon,
            trip_id=trip_id,
            day_number=day_number,
            exclude_node_ids=list(
                filter(None, [segment.origin_node_id, segment.destination_node_id])
            ),
        )

        if not candidates:
            return None

        # Take the top-ranked candidate (already sorted by convergenceScore)
        top = candidates[0]

        # Calculate timing: start at transit slot end, duration 15-30 min
        duration = top.duration_minutes or 20
        start_time: datetime | None = None
        end_time: datetime | None = None

        if segment.end_time is not None:
            utc_end = segment.end_time
            if utc_end.tzinfo is None:
                utc_end = utc_end.replace(tzinfo=timezone.utc)
            start_time = utc_end
            end_time = utc_end + timedelta(minutes=duration)

        # Insert the micro-stop slot
        new_slot_id = str(uuid.uuid4())
        # Place it immediately after the transit slot
        new_sort_order = segment.sort_order + 1

        # Shift existing slots that conflict with this sort_order
        await self._db.execute(
            """
            UPDATE "ItinerarySlot"
            SET "sortOrder" = "sortOrder" + 1, "updatedAt" = NOW()
            WHERE "tripId" = $1
              AND "dayNumber" = $2
              AND "sortOrder" >= $3
              AND id != $4
            """,
            trip_id,
            day_number,
            new_sort_order,
            segment.slot_id,
        )

        now = datetime.now(timezone.utc)
        await self._db.execute(
            """
            INSERT INTO "ItinerarySlot" (
                id, "tripId", "activityNodeId",
                "dayNumber", "sortOrder",
                "slotType", status,
                "startTime", "endTime", "durationMinutes",
                "isLocked", "wasSwapped",
                "createdAt", "updatedAt"
            ) VALUES (
                $1, $2, $3,
                $4, $5,
                'flex', 'proposed',
                $6, $7, $8,
                false, false,
                $9, $9
            )
            ON CONFLICT DO NOTHING
            """,
            new_slot_id,
            trip_id,
            top.activity_node_id,
            day_number,
            new_sort_order,
            start_time,
            end_time,
            duration,
            now,
        )

        logger.info(
            "Micro-stop inserted: slot=%s node=%s after_transit=%s duration=%dmin",
            new_slot_id,
            top.activity_node_id,
            segment.slot_id,
            duration,
        )

        return MicroStopInsertion(
            new_slot_id=new_slot_id,
            activity_node_id=top.activity_node_id,
            activity_name=top.name,
            inserted_after_slot_id=segment.slot_id,
            sort_order=new_sort_order,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            convergence_score=top.convergence_score,
        )
