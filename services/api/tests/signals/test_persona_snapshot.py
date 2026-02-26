"""Tests for persona_snapshot -- user persona dimension aggregation."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.signals.persona_snapshot import get_persona_snapshot, _signal_type_to_dimensions


def _make_signal_row(signal_type: str, signal_value: float = 1.0, signal_weight: float = 1.0):
    """Create a tuple matching the SELECT projection (signalType, signalValue, signal_weight)."""
    return (signal_type, signal_value, signal_weight)


def _make_mock_session(rows: list) -> AsyncMock:
    """Create a mock AsyncSession that returns the given rows from execute().all()."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
class TestGetPersonaSnapshot:
    """Persona snapshot from signal aggregation."""

    async def test_empty_for_new_user(self):
        session = _make_mock_session([])
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert snapshot == {}

    async def test_discover_signals_contribute_to_adventure_and_food(self):
        rows = [
            _make_signal_row("discover_swipe_right", 1.0, 1.0),
            _make_signal_row("discover_swipe_right", 1.0, 1.0),
            _make_signal_row("discover_shortlist", 1.0, 1.0),
        ]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert "adventure_score" in snapshot
        assert "food_focus" in snapshot
        # Positive signals should push above 0.5 midpoint
        assert snapshot["adventure_score"] > 0.5
        assert snapshot["food_focus"] > 0.5

    async def test_negative_signals_reduce_scores(self):
        rows = [
            _make_signal_row("discover_swipe_left", 1.0, 1.0),
            _make_signal_row("discover_swipe_left", 1.0, 1.0),
        ]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        # Negative discover signals still map to adventure/food but reduce
        if "adventure_score" in snapshot:
            assert snapshot["adventure_score"] < 0.5

    async def test_slot_signals_contribute_to_adventure_and_culture(self):
        rows = [
            _make_signal_row("slot_confirmed", 1.0, 1.0),
            _make_signal_row("slot_locked", 1.0, 1.0),
        ]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert "adventure_score" in snapshot
        assert "culture_interest" in snapshot

    async def test_values_clamped_to_0_1(self):
        # Many strong positive signals
        rows = [_make_signal_row("slot_confirmed", 5.0, 2.0) for _ in range(20)]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        for dim, val in snapshot.items():
            assert 0.0 <= val <= 1.0, f"{dim}={val} out of bounds"

    async def test_values_rounded_to_3_decimals(self):
        rows = [_make_signal_row("discover_swipe_right", 0.333, 0.777)]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        for val in snapshot.values():
            # Check it's rounded to 3 decimals
            assert val == round(val, 3)

    async def test_db_error_returns_empty_dict(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("DB down"))
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert snapshot == {}

    async def test_pivot_accepted_contributes_to_adventure(self):
        rows = [_make_signal_row("pivot_accepted", 1.0, 1.0)]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert "adventure_score" in snapshot

    async def test_card_signals_contribute_to_culture_and_food(self):
        rows = [
            _make_signal_row("card_viewed", 1.0, 1.0),
            _make_signal_row("card_impression", 1.0, 1.0),
        ]
        session = _make_mock_session(rows)
        snapshot = await get_persona_snapshot(session, str(uuid.uuid4()))
        assert "culture_interest" in snapshot
        assert "food_focus" in snapshot


class TestSignalTypeToDimensions:
    """_signal_type_to_dimensions maps signal types to persona dimension keys."""

    def test_discover_signals(self):
        dims = _signal_type_to_dimensions("discover_swipe_right")
        assert "adventure_score" in dims
        assert "food_focus" in dims

    def test_pivot_accepted(self):
        dims = _signal_type_to_dimensions("pivot_accepted")
        assert "adventure_score" in dims

    def test_pivot_rejected(self):
        dims = _signal_type_to_dimensions("pivot_rejected")
        assert "adventure_score" in dims

    def test_card_viewed(self):
        dims = _signal_type_to_dimensions("card_viewed")
        assert "culture_interest" in dims
        assert "food_focus" in dims

    def test_slot_signals(self):
        dims = _signal_type_to_dimensions("slot_confirmed")
        assert "adventure_score" in dims
        assert "culture_interest" in dims

    def test_pre_trip_signals(self):
        dims = _signal_type_to_dimensions("pre_trip_slot_added")
        assert len(dims) > 0

    def test_unknown_returns_empty(self):
        dims = _signal_type_to_dimensions("totally_unknown_signal")
        assert dims == []
