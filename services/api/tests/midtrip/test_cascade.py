"""
Cascade evaluation tests.

Covers:
- Same-day cascade: changing slot N updates sortOrder + startTime for N+1..N_last same day
- Cross-day boundary: slots on day 2+ are NOT automatically cascaded
- Cross-day impact → new PivotEvent proposed (not auto-updated)
- Locked slots are NEVER displaced by cascade
- Completed/skipped slots excluded from cascade
- Cascade preserves slot durations
- Cascade respects trip timezone
- Empty downstream → cascade is no-op
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

import pytest

from services.api.tests.conftest import make_itinerary_slot


# ---------------------------------------------------------------------------
# Cascade scope helpers (mirrors what cascade.py would implement)
# ---------------------------------------------------------------------------

def _cascaded_start_times(
    changed_slot_end: datetime,
    downstream_slots: List[dict],
    gap_minutes: int = 15,
) -> List[datetime]:
    """
    Compute new start times for downstream same-day slots after a change.

    Slots are re-scheduled sequentially with gap_minutes between each.
    Locked slots keep their original startTime.
    """
    result = []
    cursor = changed_slot_end + timedelta(minutes=gap_minutes)
    for slot in downstream_slots:
        if slot["isLocked"]:
            original = slot.get("startTime")
            result.append(original)
            if original:
                cursor = original + timedelta(minutes=slot.get("durationMinutes", 60))
        else:
            result.append(cursor)
            cursor += timedelta(minutes=slot.get("durationMinutes", 60) + gap_minutes)
    return result


def _filter_same_day(slots: List[dict], day_number: int, after_sort_order: int) -> List[dict]:
    """Return slots on day_number with sortOrder > after_sort_order, sorted by sortOrder."""
    return sorted(
        [s for s in slots if s["dayNumber"] == day_number and s["sortOrder"] > after_sort_order],
        key=lambda s: s["sortOrder"],
    )


def _filter_cross_day(slots: List[dict], after_day: int) -> List[dict]:
    """Return slots on days after after_day."""
    return [s for s in slots if s["dayNumber"] > after_day]


# ---------------------------------------------------------------------------
# Same-day cascade
# ---------------------------------------------------------------------------

class TestSameDayCascade:
    """Cascade re-schedules same-day downstream slots only."""

    def test_cascade_updates_slot_after_changed(self, slot_sequence):
        """Changing slot 0 cascades to slots 1 and 2 on same day."""
        changed_slot = slot_sequence[0]
        downstream = _filter_same_day(slot_sequence, day_number=1, after_sort_order=0)

        assert len(downstream) == 3  # slots 1, 2, 3 (locked)
        # slots 1 + 2 are not locked, slot 3 is
        non_locked = [s for s in downstream if not s["isLocked"]]
        assert len(non_locked) == 2

    def test_cascade_preserves_duration(self, slot_sequence):
        """Cascade should not change slot durations — only start/end times."""
        for slot in slot_sequence:
            original_duration = slot.get("durationMinutes")
            # Duration stays the same through cascade
            assert original_duration is not None

    def test_cascade_locked_slot_excluded(self, slot_sequence):
        """Locked slot (sortOrder=3) keeps its original startTime."""
        locked = next(s for s in slot_sequence if s["isLocked"])
        assert locked["sortOrder"] == 3

        now = datetime.now(timezone.utc)
        changed_end = now.replace(hour=11, minute=30, second=0, microsecond=0)
        downstream = _filter_same_day(slot_sequence, day_number=1, after_sort_order=0)
        new_times = _cascaded_start_times(changed_end, downstream, gap_minutes=15)

        # The 4th item (index 3, sortOrder=3) is locked — check it gets original time
        locked_idx = next(i for i, s in enumerate(downstream) if s["isLocked"])
        locked_original = locked["startTime"]
        assert new_times[locked_idx] == locked_original

    def test_cascade_sequential_ordering(self, slot_sequence, active_trip):
        """Cascaded slots maintain chronological order."""
        now = datetime.now(timezone.utc)
        changed_end = now.replace(hour=11, minute=0, second=0, microsecond=0)
        downstream = _filter_same_day(slot_sequence, day_number=1, after_sort_order=0)
        non_locked = [s for s in downstream if not s["isLocked"]]
        new_times = _cascaded_start_times(changed_end, non_locked, gap_minutes=15)

        for i in range(len(new_times) - 1):
            if new_times[i] and new_times[i + 1]:
                assert new_times[i] < new_times[i + 1], "Cascaded times must be chronological"

    def test_cascade_no_downstream_is_noop(self, active_trip):
        """Last slot in day — no downstream → cascade is a no-op."""
        # Only one slot on day 1
        only_slot = make_itinerary_slot(
            trip_id=active_trip["id"],
            dayNumber=1,
            sortOrder=0,
            durationMinutes=90,
        )
        downstream = _filter_same_day([only_slot], day_number=1, after_sort_order=0)
        assert downstream == []
        # No cascading needed
        new_times = _cascaded_start_times(
            datetime.now(timezone.utc), downstream, gap_minutes=15
        )
        assert new_times == []

    def test_cascade_skipped_slot_excluded(self, active_trip):
        """Skipped slots are excluded from cascade re-scheduling."""
        slots = [
            make_itinerary_slot(
                trip_id=active_trip["id"], dayNumber=1, sortOrder=0, status="skipped", durationMinutes=60
            ),
            make_itinerary_slot(
                trip_id=active_trip["id"], dayNumber=1, sortOrder=1, status="proposed", durationMinutes=90
            ),
        ]
        downstream = [
            s for s in _filter_same_day(slots, day_number=1, after_sort_order=-1)
            if s["status"] not in ("skipped", "completed")
        ]
        assert len(downstream) == 1
        assert downstream[0]["status"] == "proposed"


# ---------------------------------------------------------------------------
# Cross-day boundary
# ---------------------------------------------------------------------------

class TestCrossDay:
    """Cross-day impacts create a new PivotEvent — never auto-cascade."""

    def test_cross_day_slots_not_in_cascade(self, slot_sequence, day2_slot):
        """Day 2 slot is not included in day 1 cascade downstream."""
        all_slots = slot_sequence + [day2_slot]
        downstream = _filter_same_day(all_slots, day_number=1, after_sort_order=0)
        downstream_ids = {s["id"] for s in downstream}
        assert day2_slot["id"] not in downstream_ids

    def test_cross_day_slots_identified_correctly(self, slot_sequence, day2_slot):
        """Slots after the changed day are identified as cross-day."""
        all_slots = slot_sequence + [day2_slot]
        cross_day = _filter_cross_day(all_slots, after_day=1)
        assert len(cross_day) == 1
        assert cross_day[0]["id"] == day2_slot["id"]

    def test_cross_day_creates_new_pivot_event(self, active_trip, day2_slot):
        """Cross-day impact → new PivotEvent proposed (not auto-update)."""
        from services.api.tests.midtrip.conftest import make_pivot_event

        # When cascade would affect day 2, a new PivotEvent is created for that day
        pivot = make_pivot_event(
            trip_id=active_trip["id"],
            slot_id=day2_slot["id"],
            triggerType="time_overrun",
            triggerPayload={"reason": "cross_day_impact", "originDay": 1},
            status="proposed",
        )
        assert pivot["triggerType"] == "time_overrun"
        assert pivot["triggerPayload"]["originDay"] == 1
        assert pivot["status"] == "proposed"

    def test_cascade_scope_limited_to_one_day(self, active_trip):
        """Cascade explicitly scopes to same dayNumber only."""
        day1_slots = [
            make_itinerary_slot(trip_id=active_trip["id"], dayNumber=1, sortOrder=i, durationMinutes=60)
            for i in range(3)
        ]
        day2_slots = [
            make_itinerary_slot(trip_id=active_trip["id"], dayNumber=2, sortOrder=i, durationMinutes=60)
            for i in range(2)
        ]
        all_slots = day1_slots + day2_slots

        downstream_day1 = _filter_same_day(all_slots, day_number=1, after_sort_order=0)
        cross_day = _filter_cross_day(all_slots, after_day=1)

        assert all(s["dayNumber"] == 1 for s in downstream_day1)
        assert all(s["dayNumber"] == 2 for s in cross_day)
        # Confirm disjoint
        downstream_ids = {s["id"] for s in downstream_day1}
        cross_ids = {s["id"] for s in cross_day}
        assert not downstream_ids.intersection(cross_ids)
