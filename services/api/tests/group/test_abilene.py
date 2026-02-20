"""
Abilene detector tests — M-005.

Validates:
  - Lukewarm-all-members detection
  - Individual enthusiasm score computation
  - Threshold boundary: scores at exactly threshold are NOT Abilene
  - One enthusiastic member breaks Abilene condition
  - Too-few-candidates bypass
  - Determinism guarantee
"""

from __future__ import annotations

import pytest

from services.api.group.abilene_detector import (
    AbileneDetector,
    ENTHUSIASM_THRESHOLD,
    MIN_CANDIDATES_FOR_DETECTION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector() -> AbileneDetector:
    return AbileneDetector()


# ---------------------------------------------------------------------------
# Enthusiasm score computation
# ---------------------------------------------------------------------------

class TestEnthusiasmScore:
    """score_enthusiasm maps rank to [0.0, 1.0]."""

    def test_rank_1_gives_max_enthusiasm(self, detector):
        score = detector.score_enthusiasm(preference_rank=1, total_candidates=10)
        assert score == pytest.approx(1.0)

    def test_rank_equals_total_gives_zero(self, detector):
        score = detector.score_enthusiasm(preference_rank=10, total_candidates=10)
        assert score == pytest.approx(0.0)

    def test_rank_midpoint_gives_half(self, detector):
        # rank 5 out of 9 -> normalized = 4/8 = 0.5 -> enthusiasm = 0.5
        score = detector.score_enthusiasm(preference_rank=5, total_candidates=9)
        assert score == pytest.approx(0.5)

    def test_score_clamps_at_boundaries(self, detector):
        """Out-of-range ranks are clamped."""
        score_low = detector.score_enthusiasm(preference_rank=0, total_candidates=10)
        score_high = detector.score_enthusiasm(preference_rank=100, total_candidates=10)
        assert 0.0 <= score_low <= 1.0
        assert 0.0 <= score_high <= 1.0


# ---------------------------------------------------------------------------
# Abilene detection
# ---------------------------------------------------------------------------

class TestAbileneDetection:
    """detect() identifies when all members are lukewarm."""

    def test_all_lukewarm_triggers_abilene(self, detector):
        """All members with low enthusiasm -> is_abilene=True."""
        # With 10 candidates, rank 8 -> enthusiasm = 1 - 7/9 ≈ 0.22 < 0.4
        result = detector.detect(
            chosen_node_id="node-X",
            member_preference_ranks={
                "u1": 8,
                "u2": 9,
                "u3": 7,
            },
            total_candidates=10,
        )
        assert result.is_abilene is True

    def test_one_enthusiastic_member_breaks_abilene(self, detector):
        """A single enthusiastic member prevents Abilene detection."""
        # u1 has rank=1 -> enthusiasm=1.0, breaks the all-lukewarm condition
        result = detector.detect(
            chosen_node_id="node-Y",
            member_preference_ranks={
                "u1": 1,   # enthusiastic
                "u2": 9,   # lukewarm
                "u3": 8,   # lukewarm
            },
            total_candidates=10,
        )
        assert result.is_abilene is False

    def test_exactly_at_threshold_is_not_abilene(self, detector):
        """Enthusiasm exactly at threshold is NOT Abilene (strict <)."""
        # ENTHUSIASM_THRESHOLD = 0.4
        # 10 candidates: rank R such that 1 - (R-1)/9 = 0.4 => R = 6.4 -> R=6
        # enthusiasm at rank 6 = 1 - 5/9 ≈ 0.444 > 0.4 -> NOT Abilene
        result = detector.detect(
            chosen_node_id="node-Z",
            member_preference_ranks={"u1": 6, "u2": 6, "u3": 6},
            total_candidates=10,
        )
        # At rank 6 with 10 candidates, enthusiasm ≈ 0.44, above threshold
        assert result.is_abilene is False

    def test_two_candidates_bypasses_detection(self, detector):
        """Too few candidates -> always returns is_abilene=False."""
        result = detector.detect(
            chosen_node_id="node-A",
            member_preference_ranks={"u1": 2, "u2": 2},
            total_candidates=MIN_CANDIDATES_FOR_DETECTION - 1,
        )
        assert result.is_abilene is False

    def test_empty_members_returns_not_abilene(self, detector):
        """No member votes -> not Abilene."""
        result = detector.detect(
            chosen_node_id="node-B",
            member_preference_ranks={},
            total_candidates=10,
        )
        assert result.is_abilene is False

    def test_recommendation_set_when_abilene(self, detector):
        """Abilene result includes a recommendation message."""
        result = detector.detect(
            chosen_node_id="node-C",
            member_preference_ranks={"u1": 9, "u2": 10},
            total_candidates=10,
        )
        if result.is_abilene:
            assert result.recommendation is not None
            assert len(result.recommendation) > 0

    def test_recommendation_none_when_not_abilene(self, detector):
        """Non-Abilene result has no recommendation."""
        result = detector.detect(
            chosen_node_id="node-D",
            member_preference_ranks={"u1": 1},
            total_candidates=10,
        )
        assert result.recommendation is None


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestAbileneResult:
    """AbileneResult contains all expected fields."""

    def test_result_contains_member_enthusiasm(self, detector):
        result = detector.detect(
            chosen_node_id="node-E",
            member_preference_ranks={"u1": 2, "u2": 5},
            total_candidates=10,
        )
        assert "u1" in result.member_enthusiasm
        assert "u2" in result.member_enthusiasm

    def test_enthusiasm_values_in_range(self, detector):
        result = detector.detect(
            chosen_node_id="node-F",
            member_preference_ranks={"u1": 3, "u2": 7, "u3": 1},
            total_candidates=10,
        )
        for mid, score in result.member_enthusiasm.items():
            assert 0.0 <= score <= 1.0, f"enthusiasm[{mid}] = {score} out of range"

    def test_group_avg_is_mean_of_member_enthusiasm(self, detector):
        result = detector.detect(
            chosen_node_id="node-G",
            member_preference_ranks={"u1": 1, "u2": 10},
            total_candidates=10,
        )
        # u1: 1.0, u2: 0.0 -> avg = 0.5
        expected_avg = sum(result.member_enthusiasm.values()) / len(result.member_enthusiasm)
        assert result.group_avg_enthusiasm == pytest.approx(expected_avg, abs=0.01)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestAbileneDeterminism:
    """Same inputs always produce same detection result."""

    def test_same_inputs_same_output(self, detector):
        kwargs = dict(
            chosen_node_id="node-H",
            member_preference_ranks={"u1": 8, "u2": 9, "u3": 7},
            total_candidates=10,
        )
        result_a = detector.detect(**kwargs)
        result_b = detector.detect(**kwargs)
        assert result_a.is_abilene == result_b.is_abilene
        assert result_a.group_avg_enthusiasm == pytest.approx(result_b.group_avg_enthusiasm)

    def test_custom_threshold_respected(self):
        """Custom threshold changes detection boundary."""
        strict = AbileneDetector(enthusiasm_threshold=0.8)
        result = strict.detect(
            chosen_node_id="node-I",
            member_preference_ranks={"u1": 3},  # enthusiasm ≈ 0.78 with 10 candidates
            total_candidates=10,
        )
        # With threshold=0.8, rank 3 of 10 -> enthusiasm = 1 - 2/9 ≈ 0.78 < 0.8
        assert result.is_abilene is True
