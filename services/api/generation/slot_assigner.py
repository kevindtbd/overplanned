"""
Time slot assignment for itinerary generation.

Anchor-first logic:
  1. Place anchor slots first — these are time-fixed or culturally significant.
  2. Fill meal windows: lunch 12:00-13:00, dinner 19:00-20:00.
  3. Fill remaining gaps with flex activities in rank order.

Produces a flat list of ItinerarySlotAssignment objects ready for DB insert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Daily schedule envelope (24h clock, local tz represented as UTC offsets applied externally)
DAY_START_HOUR = 9   # 09:00
DAY_END_HOUR = 22    # 22:00

# Meal windows (hour, minute) inclusive start / exclusive end
LUNCH_START = (12, 0)
LUNCH_END   = (13, 0)
DINNER_START = (19, 0)
DINNER_END   = (20, 0)

# Default activity durations by category (minutes)
_DEFAULT_DURATIONS: dict[str, int] = {
    "dining":          60,
    "drinks":          45,
    "culture":         90,
    "outdoors":       120,
    "active":          90,
    "entertainment":   90,
    "shopping":        60,
    "experience":      90,
    "nightlife":       90,
    "group_activity":  90,
    "wellness":        60,
}
_FALLBACK_DURATION = 60


@dataclass
class SlotAssignment:
    """Represents a single assigned itinerary slot, ready for DB insert."""
    activity_node_id: str
    day_number: int
    sort_order: int
    slot_type: str          # "anchor" | "flex" | "meal"
    start_time: datetime    # UTC
    end_time: datetime      # UTC
    duration_minutes: int
    ranking_meta: dict[str, Any] = field(default_factory=dict)


def _duration_for(node: dict[str, Any]) -> int:
    category = (node.get("category") or "").lower()
    return _DEFAULT_DURATIONS.get(category, _FALLBACK_DURATION)


def _make_dt(trip_start_date: datetime, day_number: int, hour: int, minute: int) -> datetime:
    """Build a UTC datetime for day_number (1-indexed) at hour:minute."""
    base = trip_start_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return base + timedelta(days=day_number - 1, hours=hour, minutes=minute)


def _overlaps(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    return start_a < end_b and end_a > start_b


def assign_slots(
    ranked_nodes: list[dict[str, Any]],     # ordered by rank (best first)
    ranked_meta: list[dict[str, Any]],      # parallel list with {"slotType", "rank", "reasoning"}
    trip_start_date: datetime,
    num_days: int,
) -> list[SlotAssignment]:
    """
    Assign time slots across trip days, anchor-first.

    Args:
        ranked_nodes:   Activity nodes in rank order (best=index 0).
        ranked_meta:    Parallel LLM meta per node (slotType, rank, reasoning).
        trip_start_date: First day of trip (UTC date, time ignored).
        num_days:       Number of itinerary days.

    Returns:
        Sorted list of SlotAssignment (by day, then start_time).
    """
    assignments: list[SlotAssignment] = []

    # Track occupied windows per day: list of (start, end) tuples
    occupied: dict[int, list[tuple[datetime, datetime]]] = {
        d: [] for d in range(1, num_days + 1)
    }

    def _is_free(day: int, start: datetime, end: datetime) -> bool:
        return all(not _overlaps(start, end, s, e) for s, e in occupied[day])

    def _reserve(day: int, start: datetime, end: datetime) -> None:
        occupied[day].append((start, end))

    # Build lookup: node id -> node dict
    node_map: dict[str, dict[str, Any]] = {n["id"]: n for n in ranked_nodes}

    # Separate into anchors, meals, flex in rank order
    anchors = []
    meals = []
    flexes = []
    for meta in ranked_meta:
        node_id = meta["id"]
        node = node_map.get(node_id)
        if node is None:
            continue
        slot_type = meta.get("slotType", "flex")
        entry = (node, meta)
        if slot_type == "anchor":
            anchors.append(entry)
        elif slot_type == "meal":
            meals.append(entry)
        else:
            flexes.append(entry)

    sort_counter = [0]  # mutable counter

    def _next_sort() -> int:
        sort_counter[0] += 1
        return sort_counter[0]

    # --- Pass 1: Place anchors ---
    # Distribute anchors evenly across days, starting at 10:00
    anchor_hour = 10
    for day in range(1, num_days + 1):
        day_anchors = anchors[(day - 1)::num_days] if anchors else []
        current_hour = anchor_hour
        for node, meta in day_anchors:
            duration = _duration_for(node)
            start = _make_dt(trip_start_date, day, current_hour, 0)
            end = start + timedelta(minutes=duration)
            # Skip lunch/dinner windows
            lunch_start_dt = _make_dt(trip_start_date, day, *LUNCH_START)
            dinner_start_dt = _make_dt(trip_start_date, day, *DINNER_START)
            if _overlaps(start, end, lunch_start_dt, lunch_start_dt + timedelta(hours=1)):
                current_hour += 2
                start = _make_dt(trip_start_date, day, current_hour, 0)
                end = start + timedelta(minutes=duration)
            if end.hour > DAY_END_HOUR:
                break
            if _is_free(day, start, end):
                _reserve(day, start, end)
                assignments.append(SlotAssignment(
                    activity_node_id=node["id"],
                    day_number=day,
                    sort_order=_next_sort(),
                    slot_type="anchor",
                    start_time=start,
                    end_time=end,
                    duration_minutes=duration,
                    ranking_meta=meta,
                ))
                current_hour = end.hour + (1 if end.minute > 0 else 0)

    # --- Pass 2: Place meals (lunch then dinner per day) ---
    meal_iter = iter(meals)
    for day in range(1, num_days + 1):
        for window_start_h, window_start_m, window_end_h, window_end_m in [
            (*LUNCH_START, *LUNCH_END),
            (*DINNER_START, *DINNER_END),
        ]:
            node_meta = next(meal_iter, None)
            if node_meta is None:
                break
            node, meta = node_meta
            duration = min(_duration_for(node), 60)  # cap meals at 60 min
            start = _make_dt(trip_start_date, day, window_start_h, window_start_m)
            end = start + timedelta(minutes=duration)
            if _is_free(day, start, end):
                _reserve(day, start, end)
                assignments.append(SlotAssignment(
                    activity_node_id=node["id"],
                    day_number=day,
                    sort_order=_next_sort(),
                    slot_type="meal",
                    start_time=start,
                    end_time=end,
                    duration_minutes=duration,
                    ranking_meta=meta,
                ))

    # --- Pass 3: Fill flex slots in remaining gaps ---
    # Target ~2-3 flex activities per day depending on density
    TARGET_FLEX_PER_DAY = 2
    flex_iter = iter(flexes)
    exhausted = False

    for day in range(1, num_days + 1):
        if exhausted:
            break
        placed = 0
        # Scan from DAY_START_HOUR in 1-hour increments for free windows
        probe_hour = DAY_START_HOUR
        while placed < TARGET_FLEX_PER_DAY and probe_hour < DAY_END_HOUR:
            node_meta = next(flex_iter, None)
            if node_meta is None:
                exhausted = True
                break
            node, meta = node_meta
            duration = _duration_for(node)
            start = _make_dt(trip_start_date, day, probe_hour, 0)
            end = start + timedelta(minutes=duration)
            # Skip if window is busy — advance probe by 1 hour
            if not _is_free(day, start, end):
                probe_hour += 1
                # Put the candidate back by re-wrapping the iterator
                flex_iter = _prepend(node_meta, flex_iter)
                continue
            _reserve(day, start, end)
            assignments.append(SlotAssignment(
                activity_node_id=node["id"],
                day_number=day,
                sort_order=_next_sort(),
                slot_type="flex",
                start_time=start,
                end_time=end,
                duration_minutes=duration,
                ranking_meta=meta,
            ))
            placed += 1
            probe_hour = end.hour + (1 if end.minute > 0 else 0)

    # Sort final list by day, then chronologically
    assignments.sort(key=lambda s: (s.day_number, s.start_time))

    # Re-assign sort_order to reflect chronological order within day
    day_counters: dict[int, int] = {}
    for assignment in assignments:
        d = assignment.day_number
        day_counters[d] = day_counters.get(d, 0) + 1
        assignment.sort_order = day_counters[d]

    logger.info(
        "Slot assignment complete: %d slots across %d days",
        len(assignments),
        num_days,
    )

    return assignments


def _prepend(item: Any, iterator):
    """Yield item then the rest of the iterator."""
    yield item
    yield from iterator
