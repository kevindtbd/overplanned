"""
Tests for split_detector.py — Phase 5.5.

Covers:
  - Bimodal detection: high variance on 2+ dimensions triggers split
  - Low variance does NOT trigger split
  - Only 1 divergent dimension does NOT trigger split
  - Abilene mutual exclusivity: abilene_active=True -> None returned
  - Unanimous veto: any member in vetoed_by -> None returned
  - Daily rate limit: second suggestion same day returns None
  - Subgroups: correct two-group partition returned
  - Subgroups are non-empty and together contain all members
  - sync_back_slot is a non-empty string
  - divergent_dimensions listed in result
  - Only 1 member -> None (can't split a solo)
  - reset_suggestion_log allows re-triggering in tests
  - Determinism: same inputs produce same subgroup split
"""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock

from services.api.subflows.split_detector import (
    detect_group_split,
    reset_suggestion_log,
    VARIANCE_THRESHOLD,
    MIN_DIVERGENT_DIMENSIONS,
    MAX_SPLITS_PER_TRIP_PER_DAY,
    _cluster_members,
    _aggregate_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_signal(dimension: str, score: float, direction: str = "positive") -> dict:
    return {"dimension": dimension, "score": score, "direction": direction}


def make_pool() -> MagicMock:
    """A stub asyncpg pool — not used in current pure-logic implementation."""
    return MagicMock()


def high_variance_prefs() -> dict[str, list[dict]]:
    """
    4 members: 2 love food (score ~1.0) and hate nightlife (score ~0.0),
               2 hate food (score ~0.0) and love nightlife (score ~1.0).
    Guarantees variance >> VARIANCE_THRESHOLD on both dimensions.
    """
    return {
        "u1": [make_signal("food", 0.95), make_signal("nightlife", 0.05)],
        "u2": [make_signal("food", 0.90), make_signal("nightlife", 0.10)],
        "u3": [make_signal("food", 0.05), make_signal("nightlife", 0.95)],
        "u4": [make_signal("food", 0.10), make_signal("nightlife", 0.90)],
    }


def low_variance_prefs() -> dict[str, list[dict]]:
    """All members agree: moderate food score."""
    return {
        "u1": [make_signal("food", 0.5)],
        "u2": [make_signal("food", 0.52)],
        "u3": [make_signal("food", 0.48)],
    }


# ---------------------------------------------------------------------------
# Setup: clear rate limit log between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_suggestion_log():
    reset_suggestion_log()
    yield
    reset_suggestion_log()


# ---------------------------------------------------------------------------
# Bimodal detection
# ---------------------------------------------------------------------------

class TestBimodalDetection:
    @pytest.mark.asyncio
    async def test_high_variance_two_dimensions_triggers_split(self):
        result = await detect_group_split(
            trip_id="trip-split",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )

        assert result is not None
        assert result["split_suggested"] is True

    @pytest.mark.asyncio
    async def test_low_variance_does_not_trigger(self):
        result = await detect_group_split(
            trip_id="trip-agree",
            member_preferences=low_variance_prefs(),
            db_pool=make_pool(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_one_divergent_dimension_does_not_trigger(self):
        """Split requires MIN_DIVERGENT_DIMENSIONS (2), not just 1."""
        prefs = {
            "u1": [make_signal("food", 0.95), make_signal("pace", 0.5)],
            "u2": [make_signal("food", 0.05), make_signal("pace", 0.5)],
        }
        result = await detect_group_split(
            trip_id="trip-one-dim",
            member_preferences=prefs,
            db_pool=make_pool(),
        )

        # food variance is high, but pace variance is negligible -> only 1 divergent dim
        assert result is None

    @pytest.mark.asyncio
    async def test_variance_threshold_constant(self):
        assert VARIANCE_THRESHOLD == pytest.approx(0.08)

    @pytest.mark.asyncio
    async def test_min_divergent_dimensions_is_2(self):
        assert MIN_DIVERGENT_DIMENSIONS == 2

    @pytest.mark.asyncio
    async def test_single_member_returns_none(self):
        prefs = {
            "u1": [make_signal("food", 0.9), make_signal("pace", 0.9)],
        }
        result = await detect_group_split(
            trip_id="trip-solo",
            member_preferences=prefs,
            db_pool=make_pool(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_preferences_returns_none(self):
        result = await detect_group_split(
            trip_id="trip-empty",
            member_preferences={},
            db_pool=make_pool(),
        )
        assert result is None


# ---------------------------------------------------------------------------
# Abilene mutual exclusivity
# ---------------------------------------------------------------------------

class TestAbileneExclusivity:
    @pytest.mark.asyncio
    async def test_abilene_active_returns_none(self):
        result = await detect_group_split(
            trip_id="trip-abilene",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
            abilene_active=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_abilene_false_allows_detection(self):
        result = await detect_group_split(
            trip_id="trip-noabilene",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
            abilene_active=False,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------

class TestVeto:
    @pytest.mark.asyncio
    async def test_any_veto_suppresses_result(self):
        result = await detect_group_split(
            trip_id="trip-veto",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
            vetoed_by=["u1"],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_vetoes(self):
        result = await detect_group_split(
            trip_id="trip-multiveto",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
            vetoed_by=["u1", "u2"],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_veto_list_allows_detection(self):
        result = await detect_group_split(
            trip_id="trip-noveto",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
            vetoed_by=[],
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Daily rate limit
# ---------------------------------------------------------------------------

class TestDailyRateLimit:
    @pytest.mark.asyncio
    async def test_second_suggestion_same_day_is_suppressed(self):
        prefs = high_variance_prefs()
        pool = make_pool()

        result1 = await detect_group_split(
            trip_id="trip-daily",
            member_preferences=prefs,
            db_pool=pool,
        )

        result2 = await detect_group_split(
            trip_id="trip-daily",
            member_preferences=prefs,
            db_pool=pool,
        )

        assert result1 is not None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_different_trips_have_independent_limits(self):
        pool = make_pool()

        r1 = await detect_group_split(
            trip_id="trip-rate-A",
            member_preferences=high_variance_prefs(),
            db_pool=pool,
        )
        r2 = await detect_group_split(
            trip_id="trip-rate-B",
            member_preferences=high_variance_prefs(),
            db_pool=pool,
        )

        assert r1 is not None
        assert r2 is not None

    @pytest.mark.asyncio
    async def test_max_splits_per_trip_per_day_is_1(self):
        assert MAX_SPLITS_PER_TRIP_PER_DAY == 1

    @pytest.mark.asyncio
    async def test_reset_log_allows_retriggering(self):
        pool = make_pool()
        prefs = high_variance_prefs()

        r1 = await detect_group_split(
            trip_id="trip-resetlog",
            member_preferences=prefs,
            db_pool=pool,
        )
        assert r1 is not None

        reset_suggestion_log()

        r2 = await detect_group_split(
            trip_id="trip-resetlog",
            member_preferences=prefs,
            db_pool=pool,
        )
        assert r2 is not None


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    @pytest.mark.asyncio
    async def test_result_contains_required_keys(self):
        result = await detect_group_split(
            trip_id="trip-struct",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )

        assert result is not None
        assert "split_suggested" in result
        assert "divergent_dimensions" in result
        assert "subgroups" in result
        assert "sync_back_slot" in result

    @pytest.mark.asyncio
    async def test_split_suggested_is_true(self):
        result = await detect_group_split(
            trip_id="trip-flag",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        assert result["split_suggested"] is True

    @pytest.mark.asyncio
    async def test_divergent_dimensions_non_empty(self):
        result = await detect_group_split(
            trip_id="trip-dims",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        assert len(result["divergent_dimensions"]) >= MIN_DIVERGENT_DIMENSIONS

    @pytest.mark.asyncio
    async def test_subgroups_contains_two_groups(self):
        result = await detect_group_split(
            trip_id="trip-groups",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        assert len(result["subgroups"]) == 2

    @pytest.mark.asyncio
    async def test_subgroups_non_empty(self):
        result = await detect_group_split(
            trip_id="trip-nonempty",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        for group in result["subgroups"]:
            assert len(group) >= 1

    @pytest.mark.asyncio
    async def test_subgroups_cover_all_members(self):
        prefs = high_variance_prefs()
        result = await detect_group_split(
            trip_id="trip-cover",
            member_preferences=prefs,
            db_pool=make_pool(),
        )
        assert result is not None
        all_in_groups = set(result["subgroups"][0]) | set(result["subgroups"][1])
        assert all_in_groups == set(prefs.keys())

    @pytest.mark.asyncio
    async def test_subgroups_disjoint(self):
        result = await detect_group_split(
            trip_id="trip-disjoint",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        group_a = set(result["subgroups"][0])
        group_b = set(result["subgroups"][1])
        assert not group_a.intersection(group_b)

    @pytest.mark.asyncio
    async def test_sync_back_slot_is_non_empty_string(self):
        result = await detect_group_split(
            trip_id="trip-sync",
            member_preferences=high_variance_prefs(),
            db_pool=make_pool(),
        )
        assert result is not None
        assert isinstance(result["sync_back_slot"], str)
        assert len(result["sync_back_slot"]) > 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_preferences_same_subgroups(self):
        prefs = high_variance_prefs()

        reset_suggestion_log()
        r1 = await detect_group_split(
            trip_id="trip-det1",
            member_preferences=prefs,
            db_pool=make_pool(),
        )

        reset_suggestion_log()
        r2 = await detect_group_split(
            trip_id="trip-det2",
            member_preferences=prefs,
            db_pool=make_pool(),
        )

        assert r1 is not None
        assert r2 is not None
        # Subgroups must be identical (deterministic split)
        assert sorted([sorted(g) for g in r1["subgroups"]]) == sorted(
            [sorted(g) for g in r2["subgroups"]]
        )


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_aggregate_score_basic(self):
        signals = [
            make_signal("food", 0.8),
            make_signal("food", 0.6),
        ]
        score = _aggregate_score(signals, ["food"])
        assert score == pytest.approx(0.7, rel=1e-3)

    def test_aggregate_score_ignores_other_dimensions(self):
        signals = [
            make_signal("food", 0.9),
            make_signal("pace", 0.1),  # not in target dimensions
        ]
        score = _aggregate_score(signals, ["food"])
        assert score == pytest.approx(0.9)

    def test_aggregate_score_empty_signals_returns_neutral(self):
        score = _aggregate_score([], ["food"])
        assert score == pytest.approx(0.5)

    def test_cluster_members_two_groups(self):
        prefs = {
            "u1": [make_signal("food", 0.9)],
            "u2": [make_signal("food", 0.8)],
            "u3": [make_signal("food", 0.1)],
            "u4": [make_signal("food", 0.2)],
        }
        groups = _cluster_members(prefs, ["food"])
        assert len(groups) == 2
        assert len(groups[0]) >= 1
        assert len(groups[1]) >= 1

    def test_cluster_members_deterministic(self):
        prefs = {
            "u1": [make_signal("food", 0.9)],
            "u2": [make_signal("food", 0.1)],
        }
        g1 = _cluster_members(prefs, ["food"])
        g2 = _cluster_members(prefs, ["food"])
        assert sorted([sorted(g) for g in g1]) == sorted([sorted(g) for g in g2])

    def test_negative_direction_inverts_score(self):
        """Signal with direction='negative' at score=0.9 should be treated as 0.1."""
        signals = [make_signal("food", 0.9, direction="negative")]
        score = _aggregate_score(signals, ["food"])
        assert score == pytest.approx(0.1, rel=1e-3)
