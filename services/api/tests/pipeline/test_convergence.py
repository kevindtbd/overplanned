"""
Convergence scoring tests.

Covers:
- Multi-source nodes > single-source nodes (convergence formula)
- Vibe agreement bonus
- Authority score calculation
- Source authority resolution
"""

import pytest

from services.api.pipeline.convergence import (
    ConvergenceStats,
    SOURCE_AUTHORITY_DEFAULTS,
    compute_authority_score,
    compute_convergence_score,
    resolve_authority,
    _DEFAULT_AUTHORITY,
    _VIBE_AGREEMENT_BONUS,
    _CONVERGENCE_DENOMINATOR,
)


# ===================================================================
# Multi-source > single-source invariant
# ===================================================================


class TestMultiSourceHigherThanSingle:
    """Core invariant: nodes from multiple sources score higher than single-source nodes."""

    def test_two_sources_beats_one(self):
        single = compute_convergence_score(1, has_vibe_agreement=False)
        double = compute_convergence_score(2, has_vibe_agreement=False)
        assert double > single

    def test_three_sources_beats_two(self):
        double = compute_convergence_score(2, has_vibe_agreement=False)
        triple = compute_convergence_score(3, has_vibe_agreement=False)
        assert triple > double

    def test_four_sources_same_as_three(self):
        """Score caps at 1.0 with 3+ sources."""
        triple = compute_convergence_score(3, has_vibe_agreement=False)
        quad = compute_convergence_score(4, has_vibe_agreement=False)
        assert triple == 1.0
        assert quad == 1.0

    def test_zero_sources(self):
        score = compute_convergence_score(0, has_vibe_agreement=False)
        assert score == 0.0


# ===================================================================
# Convergence formula
# ===================================================================


class TestConvergenceFormula:
    def test_base_formula(self):
        """convergenceScore = min(unique_sources / 3.0, 1.0)."""
        assert compute_convergence_score(1, False) == pytest.approx(1 / 3.0, abs=0.001)
        assert compute_convergence_score(2, False) == pytest.approx(2 / 3.0, abs=0.001)
        assert compute_convergence_score(3, False) == 1.0

    def test_vibe_agreement_bonus(self):
        """Bonus of 0.1 when 3+ sources agree on same vibe tag."""
        base = compute_convergence_score(2, False)
        boosted = compute_convergence_score(2, True)
        diff = boosted - base
        assert diff == pytest.approx(_VIBE_AGREEMENT_BONUS, abs=0.001)

    def test_vibe_bonus_capped(self):
        """Score with vibe bonus should not exceed 1.0."""
        score = compute_convergence_score(3, True)
        assert score == 1.0

    def test_denominator_is_three(self):
        assert _CONVERGENCE_DENOMINATOR == 3.0


# ===================================================================
# Authority scoring
# ===================================================================


class TestAuthorityScore:
    def test_single_source_authority(self):
        sources = [("foursquare", 0.7)]
        score = compute_authority_score(sources)
        assert score == 0.7

    def test_multi_source_average(self):
        sources = [
            ("foursquare", 0.7),
            ("atlas_obscura", 0.85),
            ("the_infatuation", 0.9),
        ]
        score = compute_authority_score(sources)
        expected = round((0.7 + 0.85 + 0.9) / 3, 4)
        assert score == expected

    def test_empty_sources_zero(self):
        assert compute_authority_score([]) == 0.0

    def test_all_zero_authority(self):
        sources = [("a", 0.0), ("b", 0.0)]
        assert compute_authority_score(sources) == 0.0


# ===================================================================
# Authority resolution
# ===================================================================


class TestResolveAuthority:
    def test_db_value_used_when_positive(self):
        assert resolve_authority("anything", 0.85) == 0.85

    def test_db_zero_falls_back(self):
        result = resolve_authority("the_infatuation", 0.0)
        assert result == SOURCE_AUTHORITY_DEFAULTS["the_infatuation"]

    def test_db_none_falls_back(self):
        result = resolve_authority("atlas_obscura", None)
        assert result == SOURCE_AUTHORITY_DEFAULTS["atlas_obscura"]

    def test_unknown_source_default(self):
        result = resolve_authority("completely_unknown_xyz", None)
        assert result == _DEFAULT_AUTHORITY

    def test_fallback_registry_values(self):
        """Verify known sources have expected authority ranges."""
        for source, score in SOURCE_AUTHORITY_DEFAULTS.items():
            assert 0.0 < score <= 1.0, f"Invalid authority for {source}: {score}"


# ===================================================================
# ConvergenceStats
# ===================================================================


class TestConvergenceStats:
    def test_default_stats(self):
        stats = ConvergenceStats()
        assert stats.nodes_processed == 0
        assert stats.nodes_updated == 0
        assert stats.nodes_skipped == 0
        assert stats.vibe_boosts_applied == 0
        assert stats.errors == 0
        assert stats.started_at is None
        assert stats.finished_at is None

    def test_stats_tracking(self):
        stats = ConvergenceStats()
        stats.nodes_processed = 100
        stats.nodes_updated = 90
        stats.nodes_skipped = 10
        stats.vibe_boosts_applied = 5
        assert stats.nodes_processed == 100
        assert stats.nodes_skipped == 10
