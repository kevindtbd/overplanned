"""
Slot Fitter — V2 ML Pipeline Phase 5.3.

When a user adds an activity mid-trip, fit it into the itinerary after the
current active slot and handle cascade effects on downstream slots.

Rules
-----
- Insert-after-active: find the active slot (by current_slot_index), insert
  the new activity immediately after it (sortOrder + 1).
- Cascade limit: at most CASCADE_LIMIT downstream slots may be bumped.
  If more would be displaced, return a warning but do NOT insert.
- Meal protection: slots whose slotType is in MEAL_SLOT_TYPES cannot be
  bumped. If a meal slot would be in the cascade path, return a warning.
- Sub-100ms target: pure async DB logic, no LLM calls.

Output dict
-----------
{
    "inserted_at": int,        # sortOrder of the newly inserted slot
    "bumped_slots": list[str], # IDs of slots whose sortOrder was incremented
    "warnings": list[str],     # human-readable warnings (non-fatal)
}

On unrecoverable conflicts (too many bumps, meal in path), the function
returns a result with inserted_at=-1, an empty bumped list, and a warning
describing why insertion was not performed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Max number of downstream slots that can be bumped. If more would be
# affected, refuse the insertion and warn.
CASCADE_LIMIT: int = 3

# Slot types considered meal slots — time-sensitive, cannot be bumped.
MEAL_SLOT_TYPES: frozenset[str] = frozenset({"breakfast", "lunch", "dinner", "meal"})

# The Prisma model name used for ItinerarySlot queries
_SLOT_MODEL = "itineraryslot"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fit_slot(
    trip_id: str,
    new_activity: dict,
    current_slot_index: int,
    db: Any,  # Prisma client
) -> dict:
    """
    Fit a new activity into the itinerary after the current active slot.

    Args:
        trip_id:            The trip to insert into.
        new_activity:       Dict describing the activity to insert. Should
                            carry at minimum an "activityNodeId" and
                            "slotType". Other fields (durationMinutes, etc.)
                            are passed through to the created ItinerarySlot.
        current_slot_index: sortOrder of the currently active slot. The new
                            slot will be inserted at current_slot_index + 1.
        db:                 Prisma async client.

    Returns:
        {
            "inserted_at": int,        # sortOrder of new slot (-1 on failure)
            "bumped_slots": list[str], # slot IDs bumped to make room
            "warnings": list[str],     # warnings (may be non-empty even on success)
        }
    """
    insert_at: int = current_slot_index + 1
    warnings: list[str] = []

    # Fetch all slots on the same day that come after the insertion point.
    # We scope to dayNumber-agnostic here — the caller has already determined
    # which day the current_slot_index belongs to. We filter by sortOrder.
    existing_slots = await db.itineraryslot.find_many(
        where={
            "tripId": trip_id,
            "sortOrder": {"gte": insert_at},
            "status": {"not_in": ["completed", "skipped"]},
        },
        order={"sortOrder": "asc"},
    )

    # Separate meal and non-meal downstream slots
    meal_slots_in_path = [
        s for s in existing_slots
        if _slot_type(s) in MEAL_SLOT_TYPES
    ]
    non_meal_slots = [
        s for s in existing_slots
        if _slot_type(s) not in MEAL_SLOT_TYPES
    ]

    # Meal protection — cannot bump any meal slot
    if meal_slots_in_path:
        meal_names = [_slot_type(s) for s in meal_slots_in_path]
        msg = (
            f"Cannot insert here: would displace "
            f"{', '.join(meal_names)} slot(s). "
            f"Meal slots cannot be rescheduled."
        )
        logger.warning("slot_fitter: meal protection triggered for trip=%s", trip_id)
        return {
            "inserted_at": -1,
            "bumped_slots": [],
            "warnings": [msg],
        }

    # Cascade limit check
    if len(non_meal_slots) > CASCADE_LIMIT:
        msg = (
            f"Inserting here would bump {len(non_meal_slots)} slots "
            f"(limit is {CASCADE_LIMIT}). Consider swapping an existing slot instead."
        )
        logger.warning(
            "slot_fitter: cascade limit exceeded for trip=%s (would bump %d)",
            trip_id,
            len(non_meal_slots),
        )
        return {
            "inserted_at": -1,
            "bumped_slots": [],
            "warnings": [msg],
        }

    # Bump downstream slots by incrementing their sortOrder
    bumped_ids: list[str] = []
    for slot in non_meal_slots:
        slot_id = _slot_id(slot)
        new_sort_order = _slot_sort_order(slot) + 1
        await db.itineraryslot.update(
            where={"id": slot_id},
            data={"sortOrder": new_sort_order},
        )
        bumped_ids.append(slot_id)

    # Create the new slot at insert_at
    slot_data = _build_slot_data(
        trip_id=trip_id,
        new_activity=new_activity,
        sort_order=insert_at,
    )
    await db.itineraryslot.create(data=slot_data)

    logger.info(
        "slot_fitter: inserted slot at sortOrder=%d for trip=%s, bumped=%d slots",
        insert_at,
        trip_id,
        len(bumped_ids),
    )

    if bumped_ids:
        warnings.append(
            f"{len(bumped_ids)} subsequent slot(s) were rescheduled to make room."
        )

    return {
        "inserted_at": insert_at,
        "bumped_slots": bumped_ids,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slot_type(slot: Any) -> str:
    """Extract slotType from a Prisma model or dict, lowercased."""
    if hasattr(slot, "slotType"):
        return (slot.slotType or "").lower().strip()
    if isinstance(slot, dict):
        return (slot.get("slotType") or "").lower().strip()
    return ""


def _slot_id(slot: Any) -> str:
    """Extract id from a Prisma model or dict."""
    if hasattr(slot, "id"):
        return slot.id
    if isinstance(slot, dict):
        return slot.get("id", "")
    return ""


def _slot_sort_order(slot: Any) -> int:
    """Extract sortOrder from a Prisma model or dict."""
    if hasattr(slot, "sortOrder"):
        return int(slot.sortOrder or 0)
    if isinstance(slot, dict):
        return int(slot.get("sortOrder", 0))
    return 0


def _build_slot_data(
    trip_id: str,
    new_activity: dict,
    sort_order: int,
) -> dict:
    """
    Build the Prisma create-data dict for the new ItinerarySlot.

    Only maps fields that are safe to pass through. The caller is responsible
    for ensuring new_activity contains the required fields.
    """
    data: dict = {
        "tripId": trip_id,
        "sortOrder": sort_order,
        "status": "proposed",
        "isLocked": False,
    }

    passthrough_fields = (
        "activityNodeId",
        "dayNumber",
        "slotType",
        "durationMinutes",
        "startTime",
        "endTime",
        "ownerTip",
    )

    for field in passthrough_fields:
        if field in new_activity and new_activity[field] is not None:
            data[field] = new_activity[field]

    # Default slotType to "flex" for mid-trip additions
    data.setdefault("slotType", "flex")

    return data
