"""
Tests for slot_fitter.py — Phase 5.3.

Covers:
  - Insert-after-active: new slot gets sortOrder = current_slot_index + 1
  - Downstream slots have their sortOrder bumped by 1
  - Cascade limit: >3 downstream slots -> refused, warning returned
  - Meal protection: any meal slot in path -> refused, warning returned
  - Meal protection applies regardless of revisit/cascade count
  - Success with 0 bumps (no downstream slots): warning list empty
  - Success with 1-3 bumps: warning list contains bump count message
  - inserted_at = -1 on failure cases
  - bumped_slots empty on failure
  - Slot data is created with correct tripId and sortOrder
  - Non-meal downstream slots with slotType variations
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, call

from services.api.subflows.slot_fitter import (
    fit_slot,
    CASCADE_LIMIT,
    MEAL_SLOT_TYPES,
    _slot_type,
    _slot_id,
    _slot_sort_order,
    _build_slot_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_slot_obj(
    slot_id: str,
    sort_order: int,
    slot_type: str = "anchor",
    status: str = "proposed",
) -> MagicMock:
    """Build a Prisma-model-like MagicMock for an ItinerarySlot."""
    obj = MagicMock()
    obj.id = slot_id
    obj.sortOrder = sort_order
    obj.slotType = slot_type
    obj.status = status
    return obj


def make_db(downstream_slots: list) -> AsyncMock:
    """Build a mock Prisma client returning the given downstream slots."""
    db = AsyncMock()
    db.itineraryslot = AsyncMock()
    db.itineraryslot.find_many = AsyncMock(return_value=downstream_slots)
    db.itineraryslot.update = AsyncMock(return_value=None)
    db.itineraryslot.create = AsyncMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# Insert-after-active
# ---------------------------------------------------------------------------

class TestInsertAfterActive:
    @pytest.mark.asyncio
    async def test_inserted_at_is_current_plus_one(self):
        db = make_db(downstream_slots=[])

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex", "dayNumber": 1},
            current_slot_index=2,
            db=db,
        )

        assert result["inserted_at"] == 3

    @pytest.mark.asyncio
    async def test_insert_at_zero_when_current_is_minus_one(self):
        """Inserting before all slots: current_slot_index=-1 -> insert at 0."""
        db = make_db(downstream_slots=[])

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex", "dayNumber": 1},
            current_slot_index=-1,
            db=db,
        )

        assert result["inserted_at"] == 0

    @pytest.mark.asyncio
    async def test_create_called_with_correct_sort_order(self):
        db = make_db(downstream_slots=[])

        await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex", "dayNumber": 1},
            current_slot_index=4,
            db=db,
        )

        db.itineraryslot.create.assert_called_once()
        create_kwargs = db.itineraryslot.create.call_args
        data = create_kwargs.kwargs.get("data") or create_kwargs.args[0].get("data", {})
        assert data.get("sortOrder") == 5

    @pytest.mark.asyncio
    async def test_trip_id_set_on_created_slot(self):
        db = make_db(downstream_slots=[])

        await fit_slot(
            trip_id="trip-abc",
            new_activity={"activityNodeId": "node-X", "slotType": "flex", "dayNumber": 1},
            current_slot_index=0,
            db=db,
        )

        create_kwargs = db.itineraryslot.create.call_args
        data = create_kwargs.kwargs.get("data") or create_kwargs.args[0].get("data", {})
        assert data.get("tripId") == "trip-abc"


# ---------------------------------------------------------------------------
# Downstream bumping
# ---------------------------------------------------------------------------

class TestDownstreamBumping:
    @pytest.mark.asyncio
    async def test_downstream_slots_bumped_by_one(self):
        downstream = [
            make_slot_obj("s1", sort_order=3),
            make_slot_obj("s2", sort_order=4),
        ]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=2,
            db=db,
        )

        assert result["inserted_at"] == 3
        assert set(result["bumped_slots"]) == {"s1", "s2"}

        # Verify update was called for each downstream slot
        calls = db.itineraryslot.update.call_args_list
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_bumped_slot_ids_in_result(self):
        downstream = [make_slot_obj("s1", sort_order=1)]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert "s1" in result["bumped_slots"]

    @pytest.mark.asyncio
    async def test_no_downstream_no_bump_no_warning(self):
        db = make_db(downstream_slots=[])

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=5,
            db=db,
        )

        assert result["inserted_at"] == 6
        assert result["bumped_slots"] == []
        assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_bump_warning_present_when_slots_bumped(self):
        downstream = [make_slot_obj("s1", sort_order=1)]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert len(result["warnings"]) == 1
        assert "rescheduled" in result["warnings"][0].lower()


# ---------------------------------------------------------------------------
# Cascade limit
# ---------------------------------------------------------------------------

class TestCascadeLimit:
    @pytest.mark.asyncio
    async def test_exactly_cascade_limit_succeeds(self):
        """Exactly CASCADE_LIMIT downstream slots is allowed."""
        downstream = [
            make_slot_obj(f"s{i}", sort_order=i + 1)
            for i in range(CASCADE_LIMIT)
        ]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert result["inserted_at"] == 1

    @pytest.mark.asyncio
    async def test_one_over_limit_refused(self):
        """CASCADE_LIMIT + 1 non-meal downstream slots -> refusal."""
        downstream = [
            make_slot_obj(f"s{i}", sort_order=i + 1)
            for i in range(CASCADE_LIMIT + 1)
        ]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert result["inserted_at"] == -1
        assert result["bumped_slots"] == []
        assert len(result["warnings"]) == 1
        assert str(CASCADE_LIMIT) in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_cascade_limit_is_3(self):
        assert CASCADE_LIMIT == 3

    @pytest.mark.asyncio
    async def test_refused_does_not_call_update_or_create(self):
        """On refusal, no DB writes should occur."""
        downstream = [
            make_slot_obj(f"s{i}", sort_order=i + 1)
            for i in range(CASCADE_LIMIT + 1)
        ]
        db = make_db(downstream_slots=downstream)

        await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        db.itineraryslot.update.assert_not_called()
        db.itineraryslot.create.assert_not_called()


# ---------------------------------------------------------------------------
# Meal protection
# ---------------------------------------------------------------------------

class TestMealProtection:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("meal_type", list(MEAL_SLOT_TYPES))
    async def test_meal_slot_in_path_refuses(self, meal_type: str):
        """Any meal slot type in downstream path causes refusal."""
        downstream = [
            make_slot_obj("meal-1", sort_order=1, slot_type=meal_type),
        ]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert result["inserted_at"] == -1
        assert result["bumped_slots"] == []
        assert any("meal" in w.lower() or meal_type in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_meal_protection_overrides_cascade_limit(self):
        """Meal in path is checked before cascade limit — meal wins."""
        # Only 1 meal slot — below cascade limit, but meal protection should fire first
        downstream = [make_slot_obj("meal-1", sort_order=1, slot_type="lunch")]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert result["inserted_at"] == -1

    @pytest.mark.asyncio
    async def test_no_meal_in_path_allows_insert(self):
        """If there are non-meal slots only (within limit), insertion proceeds."""
        downstream = [make_slot_obj("s1", sort_order=1, slot_type="anchor")]
        db = make_db(downstream_slots=downstream)

        result = await fit_slot(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "slotType": "flex"},
            current_slot_index=0,
            db=db,
        )

        assert result["inserted_at"] == 1

    @pytest.mark.asyncio
    async def test_meal_slot_types_set(self):
        """Verify the expected slot types are included in MEAL_SLOT_TYPES."""
        assert "breakfast" in MEAL_SLOT_TYPES
        assert "lunch" in MEAL_SLOT_TYPES
        assert "dinner" in MEAL_SLOT_TYPES
        assert "meal" in MEAL_SLOT_TYPES


# ---------------------------------------------------------------------------
# Slot data helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_slot_type_from_mock_obj(self):
        obj = make_slot_obj("x", 0, slot_type="Lunch")
        assert _slot_type(obj) == "lunch"  # lowercased

    def test_slot_type_from_dict(self):
        assert _slot_type({"slotType": "Dinner"}) == "dinner"

    def test_slot_id_from_obj(self):
        obj = make_slot_obj("my-id", 0)
        assert _slot_id(obj) == "my-id"

    def test_slot_sort_order_from_dict(self):
        assert _slot_sort_order({"sortOrder": 7}) == 7

    def test_build_slot_data_contains_required_fields(self):
        data = _build_slot_data(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X", "dayNumber": 2, "slotType": "flex"},
            sort_order=3,
        )
        assert data["tripId"] == "trip-1"
        assert data["sortOrder"] == 3
        assert data["status"] == "proposed"
        assert data["activityNodeId"] == "node-X"

    def test_build_slot_data_defaults_slot_type_to_flex(self):
        data = _build_slot_data(
            trip_id="trip-1",
            new_activity={"activityNodeId": "node-X"},
            sort_order=0,
        )
        assert data["slotType"] == "flex"
