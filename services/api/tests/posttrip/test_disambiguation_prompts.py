"""
Tests for services/api/posttrip/disambiguation_prompts.py

Covers:
- get_disambiguation_prompts: max_prompts cap, only no_show_ambiguous slots
- resolve_disambiguation: correct signals for each of the three response types
- signal_weight values match spec (server-side only — never returned to client)
- negative preference signal created only for confirmed_skipped_preference
- ValueError on unknown response_value
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.api.posttrip.disambiguation_prompts import (
    get_disambiguation_prompts,
    resolve_disambiguation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slot(
    slot_id: str,
    trip_id: str,
    day_number: int,
    activity_name: str = "Test Place",
    activity_node_id: str = "node-001",
) -> MagicMock:
    """Build a mock ItinerarySlot Prisma model."""
    slot = MagicMock()
    slot.id = slot_id
    slot.tripId = trip_id
    slot.dayNumber = day_number
    slot.activityNodeId = activity_node_id

    activity_node = MagicMock()
    activity_node.name = activity_name
    slot.activityNode = activity_node

    return slot


def _make_db(slots: list[MagicMock] | None = None) -> AsyncMock:
    """Build a minimal Prisma mock that returns the given slots."""
    db = AsyncMock()
    db.itineraryslot = AsyncMock()

    _slots = slots or []

    async def _find_many(**kwargs):
        take = kwargs.get("take")
        if take is not None:
            return _slots[:take]
        return _slots

    db.itineraryslot.find_many = AsyncMock(side_effect=_find_many)
    db.itineraryslot.find_unique = AsyncMock(return_value=None)
    db.itineraryslot.update = AsyncMock(return_value=None)
    db.behavioralsignal = AsyncMock()
    db.behavioralsignal.create = AsyncMock(return_value=None)
    return db


# ---------------------------------------------------------------------------
# 1. get_disambiguation_prompts — basic behavior
# ---------------------------------------------------------------------------

class TestGetDisambiguationPrompts:
    """Tests for the prompt retrieval function."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_ambiguous_slots(self):
        """No ambiguous slots -> empty prompt list."""
        db = _make_db(slots=[])
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_prompt_for_each_ambiguous_slot(self):
        """One prompt per ambiguous slot."""
        slots = [
            _make_slot("slot-1", "trip-001", 1, "Senso-ji"),
            _make_slot("slot-2", "trip-001", 2, "Shibuya Crossing"),
        ]
        db = _make_db(slots=slots)
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_max_prompts_cap_respected(self):
        """No more than max_prompts prompts returned."""
        slots = [_make_slot(f"slot-{i}", "trip-001", i, f"Place {i}") for i in range(10)]
        db = _make_db(slots=slots)
        result = await get_disambiguation_prompts(db, trip_id="trip-001", max_prompts=3)
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_default_max_prompts_is_three(self):
        """Default max_prompts cap is 3."""
        slots = [_make_slot(f"slot-{i}", "trip-001", i) for i in range(5)]
        db = _make_db(slots=slots)
        # DB is called with take=3 (default)
        await get_disambiguation_prompts(db, trip_id="trip-001")
        call_kwargs = db.itineraryslot.find_many.call_args[1]
        assert call_kwargs.get("take") == 3

    @pytest.mark.asyncio
    async def test_query_filters_by_no_show_ambiguous(self):
        """The query must filter completionSignal = 'no_show_ambiguous'."""
        db = _make_db()
        await get_disambiguation_prompts(db, trip_id="trip-123")
        call_kwargs = db.itineraryslot.find_many.call_args[1]
        where = call_kwargs.get("where", {})
        assert where.get("completionSignal") == "no_show_ambiguous"

    @pytest.mark.asyncio
    async def test_query_filters_by_trip_id(self):
        """The query must scope slots to the provided trip_id."""
        db = _make_db()
        await get_disambiguation_prompts(db, trip_id="trip-xyz")
        call_kwargs = db.itineraryslot.find_many.call_args[1]
        where = call_kwargs.get("where", {})
        assert where.get("tripId") == "trip-xyz"

    @pytest.mark.asyncio
    async def test_prompt_shape_is_correct(self):
        """Each prompt has slotId, activityName, dayNumber, question, options."""
        slots = [_make_slot("slot-1", "trip-001", 2, "Tsukiji Market")]
        db = _make_db(slots=slots)
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        prompt = result[0]
        assert prompt["slotId"] == "slot-1"
        assert prompt["activityName"] == "Tsukiji Market"
        assert prompt["dayNumber"] == 2
        assert "Tsukiji Market" in prompt["question"]
        assert isinstance(prompt["options"], list)
        assert len(prompt["options"]) == 3

    @pytest.mark.asyncio
    async def test_options_have_label_and_value_only(self):
        """Client-facing options must NOT contain signal_weight."""
        slots = [_make_slot("slot-1", "trip-001", 1)]
        db = _make_db(slots=slots)
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        for option in result[0]["options"]:
            assert "label" in option
            assert "value" in option
            assert "signal_weight" not in option, (
                "signal_weight must not be exposed to the client"
            )

    @pytest.mark.asyncio
    async def test_option_values_are_valid_response_keys(self):
        """Option values must be the three expected response keys."""
        slots = [_make_slot("slot-1", "trip-001", 1)]
        db = _make_db(slots=slots)
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        values = {opt["value"] for opt in result[0]["options"]}
        assert values == {
            "confirmed_attended",
            "confirmed_skipped_preference",
            "confirmed_skipped_timing",
        }

    @pytest.mark.asyncio
    async def test_fallback_name_when_no_activity_node(self):
        """If slot has no activityNode, use 'this activity' as the name."""
        slot = MagicMock()
        slot.id = "slot-no-node"
        slot.tripId = "trip-001"
        slot.dayNumber = 1
        slot.activityNodeId = None
        slot.activityNode = None

        db = _make_db(slots=[slot])
        result = await get_disambiguation_prompts(db, trip_id="trip-001")
        assert "this activity" in result[0]["question"]


# ---------------------------------------------------------------------------
# 2. resolve_disambiguation — signal_weight values and side effects
# ---------------------------------------------------------------------------

class TestResolveDisambiguation:
    """Tests for the resolution function."""

    def _make_slot_for_resolve(
        self,
        slot_id: str = "slot-001",
        trip_id: str = "trip-001",
        activity_node_id: str = "node-001",
    ) -> MagicMock:
        slot = MagicMock()
        slot.id = slot_id
        slot.tripId = trip_id
        slot.activityNodeId = activity_node_id
        return slot

    @pytest.mark.asyncio
    async def test_confirmed_attended_updates_slot_to_confirmed_attended(self):
        """confirmed_attended -> completionSignal = confirmed_attended."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        result = await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_attended"
        )

        assert result["completionSignal"] == "confirmed_attended"
        db.itineraryslot.update.assert_called_once()
        update_kwargs = db.itineraryslot.update.call_args[1]
        assert update_kwargs["data"]["completionSignal"] == "confirmed_attended"

    @pytest.mark.asyncio
    async def test_confirmed_attended_creates_signal_with_weight_0_7(self):
        """confirmed_attended -> signal_weight = 0.7."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_attended"
        )

        assert db.behavioralsignal.create.call_count == 1
        signal_data = db.behavioralsignal.create.call_args[1]["data"]
        assert signal_data["signal_weight"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_confirmed_skipped_preference_updates_slot_to_confirmed_skipped(self):
        """confirmed_skipped_preference -> completionSignal = confirmed_skipped."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        result = await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_preference"
        )

        assert result["completionSignal"] == "confirmed_skipped"

    @pytest.mark.asyncio
    async def test_confirmed_skipped_preference_signal_weight_is_negative_0_3(self):
        """confirmed_skipped_preference -> signal_weight = -0.3."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_preference"
        )

        first_signal = db.behavioralsignal.create.call_args_list[0][1]["data"]
        assert first_signal["signal_weight"] == pytest.approx(-0.3)

    @pytest.mark.asyncio
    async def test_confirmed_skipped_preference_creates_two_signals(self):
        """confirmed_skipped_preference creates a primary + a negative preference signal."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_preference"
        )

        assert db.behavioralsignal.create.call_count == 2
        signal_types = {
            call[1]["data"]["signalType"]
            for call in db.behavioralsignal.create.call_args_list
        }
        assert "negative_preference" in signal_types

    @pytest.mark.asyncio
    async def test_confirmed_skipped_timing_updates_slot_to_confirmed_skipped(self):
        """confirmed_skipped_timing -> completionSignal = confirmed_skipped."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        result = await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_timing"
        )

        assert result["completionSignal"] == "confirmed_skipped"

    @pytest.mark.asyncio
    async def test_confirmed_skipped_timing_signal_weight_is_zero(self):
        """confirmed_skipped_timing -> signal_weight = 0.0 (no persona update)."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_timing"
        )

        signal_data = db.behavioralsignal.create.call_args[1]["data"]
        assert signal_data["signal_weight"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_confirmed_skipped_timing_creates_only_one_signal(self):
        """confirmed_skipped_timing does NOT create a negative preference signal."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_timing"
        )

        assert db.behavioralsignal.create.call_count == 1

    @pytest.mark.asyncio
    async def test_confirmed_attended_creates_only_one_signal(self):
        """confirmed_attended does NOT create a negative preference signal."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_attended"
        )

        assert db.behavioralsignal.create.call_count == 1

    @pytest.mark.asyncio
    async def test_unknown_response_value_raises_value_error(self):
        """Unrecognised response_value must raise ValueError."""
        db = _make_db()
        with pytest.raises(ValueError, match="Unknown response_value"):
            await resolve_disambiguation(
                db, slot_id="slot-001", user_id="user-1",
                response_value="totally_invalid"
            )

    @pytest.mark.asyncio
    async def test_result_contains_slot_id(self):
        """Result dict must include slotId."""
        slot = self._make_slot_for_resolve(slot_id="slot-xyz")
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        result = await resolve_disambiguation(
            db, slot_id="slot-xyz", user_id="user-1",
            response_value="confirmed_attended"
        )

        assert result["slotId"] == "slot-xyz"

    @pytest.mark.asyncio
    async def test_result_signal_created_is_true(self):
        """signalCreated must be True on successful resolution."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        result = await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_attended"
        )

        assert result["signalCreated"] is True

    @pytest.mark.asyncio
    async def test_signal_source_is_explicit_feedback(self):
        """All created signals must have source='explicit_feedback'."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_skipped_preference"
        )

        for call in db.behavioralsignal.create.call_args_list:
            signal_data = call[1]["data"]
            assert signal_data["source"] == "explicit_feedback"

    @pytest.mark.asyncio
    async def test_signal_subflow_is_disambiguation_resolution(self):
        """All signals must carry subflow='disambiguation_resolution'."""
        slot = self._make_slot_for_resolve()
        db = _make_db()
        db.itineraryslot.find_unique = AsyncMock(return_value=slot)

        await resolve_disambiguation(
            db, slot_id="slot-001", user_id="user-1",
            response_value="confirmed_attended"
        )

        signal_data = db.behavioralsignal.create.call_args[1]["data"]
        assert signal_data["subflow"] == "disambiguation_resolution"

    @pytest.mark.asyncio
    async def test_all_signal_weights_within_db_check_range(self):
        """
        signal_weight must stay within [-1.0, 3.0] (DB CHECK constraint).
        Test all three response values.
        """
        for response_value in (
            "confirmed_attended",
            "confirmed_skipped_preference",
            "confirmed_skipped_timing",
        ):
            slot = self._make_slot_for_resolve()
            db = _make_db()
            db.itineraryslot.find_unique = AsyncMock(return_value=slot)

            await resolve_disambiguation(
                db, slot_id="slot-001", user_id="user-1",
                response_value=response_value,
            )

            for call in db.behavioralsignal.create.call_args_list:
                weight = call[1]["data"]["signal_weight"]
                assert -1.0 <= weight <= 3.0, (
                    f"signal_weight {weight} out of range for {response_value}"
                )
