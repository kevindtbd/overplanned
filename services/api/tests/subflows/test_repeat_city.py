"""
Tests for repeat_city.py — Phase 5.2.

Covers:
  - Hard exclusion: nodes with rejection signals or negative signal_weight
  - Soft exclusion: impression-only nodes removed by default
  - Soft exclusion bypass: revisit_favorites=True keeps soft-excluded nodes
  - Boost: 1.3x multiplier applied to accepted nodes
  - Boost applied to both "score" and "convergenceScore"
  - No prior trips: candidates returned unchanged
  - Empty candidate list: returns empty list
  - Mutual exclusivity: hard exclude beats soft exclude beats boost
  - DB query path: previous trip IDs are correctly fetched
  - signal_weight is never present in returned candidates
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from services.api.subflows.repeat_city import (
    apply_repeat_city_boost,
    BOOST_MULTIPLIER,
    _apply_boost,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candidate(
    node_id: str,
    score: float | None = 0.8,
    convergence: float | None = None,
    category: str = "dining",
) -> dict:
    """Build a minimal candidate dict."""
    c: dict = {"id": node_id, "category": category}
    if score is not None:
        c["score"] = score
    if convergence is not None:
        c["convergenceScore"] = convergence
    return c


def make_signal_row(node_id: str, signal_type: str, weight: float = 1.0) -> dict:
    """Build a fake asyncpg-style row dict."""
    return {
        "activityNodeId": node_id,
        "signalType": signal_type,
        "signal_weight": weight,
    }


def build_mock_pool(trip_rows: list, signal_rows: list) -> MagicMock:
    """
    Build a mock asyncpg pool where:
      - First acquire().fetch() -> trip_rows
      - Second acquire().fetch() -> signal_rows
    """
    pool = MagicMock()
    conn = AsyncMock()

    fetch_call_count = [0]

    async def fetch_side_effect(query, *args):
        fetch_call_count[0] += 1
        if fetch_call_count[0] == 1:
            return trip_rows
        return signal_rows

    conn.fetch = fetch_side_effect

    @asynccontextmanager
    async def acquire_ctx():
        yield conn

    pool.acquire = acquire_ctx
    return pool


# ---------------------------------------------------------------------------
# No prior trips
# ---------------------------------------------------------------------------

class TestNoPriorTrips:
    """When the user has no previous trips to this city, candidates pass through unchanged."""

    @pytest.mark.asyncio
    async def test_empty_trip_rows_returns_all_candidates(self):
        candidates = [make_candidate("n1"), make_candidate("n2")]
        pool = build_mock_pool(trip_rows=[], signal_rows=[])

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 2
        ids = {c["id"] for c in result}
        assert ids == {"n1", "n2"}

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        pool = build_mock_pool(trip_rows=[], signal_rows=[])

        result = await apply_repeat_city_boost(
            candidates=[],
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert result == []


# ---------------------------------------------------------------------------
# Hard exclusion
# ---------------------------------------------------------------------------

class TestHardExclusion:
    """Nodes with rejection signals or signal_weight < 0 are dropped."""

    @pytest.mark.asyncio
    async def test_rejected_node_hard_excluded(self):
        candidates = [make_candidate("n1"), make_candidate("n2")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [
            make_signal_row("n1", "slot_skip", weight=1.0),
        ]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        ids = {c["id"] for c in result}
        assert "n1" not in ids
        assert "n2" in ids

    @pytest.mark.asyncio
    async def test_negative_weight_node_hard_excluded(self):
        candidates = [make_candidate("n1"), make_candidate("n2")]
        trip_rows = [{"id": "trip-1"}]
        # signal_weight < 0 triggers hard exclude even without rejection type
        signal_rows = [
            make_signal_row("n1", "slot_view", weight=-0.5),
        ]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        ids = {c["id"] for c in result}
        assert "n1" not in ids

    @pytest.mark.asyncio
    async def test_dislike_signal_hard_excluded(self):
        candidates = [make_candidate("n1")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_dislike", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=True,  # even with revisit_favorites, hard exclude wins
            db_pool=pool,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_hard_exclude_overrides_revisit_favorites(self):
        """Hard-excluded nodes must stay excluded even when revisit_favorites=True."""
        candidates = [make_candidate("n1")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_reject", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=True,
            db_pool=pool,
        )

        assert result == []


# ---------------------------------------------------------------------------
# Soft exclusion
# ---------------------------------------------------------------------------

class TestSoftExclusion:
    """Impression-only nodes are soft-excluded by default."""

    @pytest.mark.asyncio
    async def test_impression_only_node_excluded_by_default(self):
        candidates = [make_candidate("n1"), make_candidate("n2")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_view", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        ids = {c["id"] for c in result}
        assert "n1" not in ids
        assert "n2" in ids

    @pytest.mark.asyncio
    async def test_revisit_favorites_keeps_soft_excluded(self):
        candidates = [make_candidate("n1"), make_candidate("n2")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_view", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=True,
            db_pool=pool,
        )

        ids = {c["id"] for c in result}
        assert "n1" in ids

    @pytest.mark.asyncio
    async def test_impression_then_acceptance_is_boosted_not_soft_excluded(self):
        """If a node has both impression and acceptance, it is boosted, not soft-excluded."""
        candidates = [make_candidate("n1", score=0.5)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [
            make_signal_row("n1", "slot_view", weight=1.0),
            make_signal_row("n1", "slot_accept", weight=1.0),
        ]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 1
        assert result[0]["id"] == "n1"
        # Should be boosted, not excluded
        assert result[0].get("score", 0) > 0.5


# ---------------------------------------------------------------------------
# Boost
# ---------------------------------------------------------------------------

class TestBoost:
    """Accepted/loved nodes receive a 1.3x score multiplier."""

    @pytest.mark.asyncio
    async def test_accepted_node_gets_score_boost(self):
        candidates = [make_candidate("n1", score=0.5)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_accept", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(0.5 * BOOST_MULTIPLIER, rel=1e-4)

    @pytest.mark.asyncio
    async def test_loved_node_gets_convergence_score_boost(self):
        candidates = [make_candidate("n1", score=None, convergence=0.6)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_love", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 1
        assert result[0]["convergenceScore"] == pytest.approx(0.6 * BOOST_MULTIPLIER, rel=1e-4)

    @pytest.mark.asyncio
    async def test_boost_applied_to_both_score_fields(self):
        candidates = [make_candidate("n1", score=0.4, convergence=0.6)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_confirm", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(0.4 * BOOST_MULTIPLIER, rel=1e-4)
        assert result[0]["convergenceScore"] == pytest.approx(0.6 * BOOST_MULTIPLIER, rel=1e-4)

    @pytest.mark.asyncio
    async def test_boost_multiplier_is_1_3(self):
        assert BOOST_MULTIPLIER == pytest.approx(1.3)

    def test_apply_boost_no_score_fields_unchanged(self):
        """Nodes without score fields are returned unchanged by _apply_boost."""
        candidate = {"id": "n1", "category": "dining"}
        result = _apply_boost(candidate)
        assert result["id"] == "n1"
        assert "score" not in result
        assert "convergenceScore" not in result

    @pytest.mark.asyncio
    async def test_non_boosted_node_score_unchanged(self):
        """Nodes with no prior signals are returned with original score."""
        candidates = [make_candidate("n1", score=0.7)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = []  # no signals for this node
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        assert len(result) == 1
        assert result[0]["score"] == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    """Original candidate list must not be mutated."""

    @pytest.mark.asyncio
    async def test_original_list_not_mutated(self):
        original_score = 0.5
        candidates = [make_candidate("n1", score=original_score)]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_accept", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        # Original must not have been boosted in-place
        assert candidates[0]["score"] == pytest.approx(original_score)

    @pytest.mark.asyncio
    async def test_signal_weight_not_in_returned_candidates(self):
        """signal_weight must never appear in returned candidate dicts."""
        candidates = [make_candidate("n1")]
        trip_rows = [{"id": "trip-1"}]
        signal_rows = [make_signal_row("n1", "slot_accept", weight=1.0)]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        for c in result:
            assert "signal_weight" not in c


# ---------------------------------------------------------------------------
# Multiple trips
# ---------------------------------------------------------------------------

class TestMultipleTrips:
    """Signals from multiple prior trips are all considered."""

    @pytest.mark.asyncio
    async def test_signals_from_two_trips_aggregated(self):
        """Node seen positively on trip 1 and negatively on trip 2 -> hard excluded."""
        candidates = [make_candidate("n1")]
        trip_rows = [{"id": "trip-1"}, {"id": "trip-2"}]
        signal_rows = [
            make_signal_row("n1", "slot_love", weight=1.0),   # trip-1: loved
            make_signal_row("n1", "slot_dislike", weight=1.0), # trip-2: disliked
        ]
        pool = build_mock_pool(trip_rows, signal_rows)

        result = await apply_repeat_city_boost(
            candidates=candidates,
            user_id="user-1",
            city_slug="tokyo",
            revisit_favorites=False,
            db_pool=pool,
        )

        # dislike signal -> hard excluded
        assert result == []
