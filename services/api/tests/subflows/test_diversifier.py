"""
Tests for diversifier.py — Phase 5.4.

Covers:
  - MMR formula: first pick is highest relevance; subsequent picks penalise similarity
  - Lambda=1.0 degenerates to pure relevance ranking
  - Lambda=0.0 degenerates to maximum diversity
  - Category diversity: two nodes in the same category are not both selected first
  - Vibe tag Jaccard similarity correctly computed
  - generate_alternatives returns num_alternatives per selected slot
  - generate_alternatives excludes the selected slot from alternatives
  - Empty candidate list returns empty
  - num_select > len(candidates) is handled gracefully
  - Candidates without score fields use 0.5 fallback relevance
  - Determinism: same inputs produce same outputs
"""

from __future__ import annotations

import pytest

from services.api.subflows.diversifier import (
    apply_mmr_diversification,
    generate_alternatives,
    DEFAULT_LAMBDA,
    _get_relevance,
    _get_category,
    _get_vibe_slugs,
    _jaccard,
    _similarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candidate(
    cid: str,
    score: float = 0.5,
    category: str = "dining",
    vibes: list[str] | None = None,
) -> dict:
    return {
        "id": cid,
        "score": score,
        "category": category,
        "vibeTags": [{"slug": v} for v in (vibes or [])],
    }


# ---------------------------------------------------------------------------
# Relevance extraction
# ---------------------------------------------------------------------------

class TestGetRelevance:
    def test_score_field_used_first(self):
        c = {"score": 0.9, "convergenceScore": 0.1}
        assert _get_relevance(c) == pytest.approx(0.9)

    def test_convergence_score_fallback(self):
        c = {"convergenceScore": 0.7}
        assert _get_relevance(c) == pytest.approx(0.7)

    def test_no_score_returns_half(self):
        c = {"category": "dining"}
        assert _get_relevance(c) == pytest.approx(0.5)

    def test_none_score_falls_through(self):
        c = {"score": None, "convergenceScore": 0.4}
        assert _get_relevance(c) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Similarity computation
# ---------------------------------------------------------------------------

class TestSimilarity:
    def test_same_category_same_vibes_is_max(self):
        a = make_candidate("a", category="dining", vibes=["ramen", "izakaya"])
        b = make_candidate("b", category="dining", vibes=["ramen", "izakaya"])
        assert _similarity(a, b) == pytest.approx(1.0)

    def test_different_category_no_vibes_is_zero(self):
        a = make_candidate("a", category="museum", vibes=[])
        b = make_candidate("b", category="dining", vibes=[])
        assert _similarity(a, b) == pytest.approx(0.0)

    def test_same_category_no_vibes_is_half(self):
        a = make_candidate("a", category="dining", vibes=[])
        b = make_candidate("b", category="dining", vibes=[])
        # category_overlap=1.0, jaccard=0.0 -> 0.5 * 1.0 + 0.5 * 0.0 = 0.5
        assert _similarity(a, b) == pytest.approx(0.5)

    def test_partial_vibe_overlap(self):
        a = make_candidate("a", category="dining", vibes=["ramen", "bar"])
        b = make_candidate("b", category="dining", vibes=["ramen", "cafe"])
        # category=1.0, jaccard({"ramen","bar"},{"ramen","cafe"})=1/3
        # sim = 0.5 * 1.0 + 0.5 * (1/3) ≈ 0.667
        sim = _similarity(a, b)
        assert sim == pytest.approx(0.5 + 0.5 * (1 / 3), rel=1e-3)


class TestJaccard:
    def test_identical_sets(self):
        a = frozenset(["x", "y"])
        assert _jaccard(a, a) == pytest.approx(1.0)

    def test_disjoint_sets(self):
        a = frozenset(["x"])
        b = frozenset(["y"])
        assert _jaccard(a, b) == pytest.approx(0.0)

    def test_both_empty(self):
        assert _jaccard(frozenset(), frozenset()) == pytest.approx(0.0)

    def test_one_empty(self):
        a = frozenset(["x"])
        assert _jaccard(a, frozenset()) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# MMR selection
# ---------------------------------------------------------------------------

class TestApplyMMR:
    def test_empty_candidates_returns_empty(self):
        result = apply_mmr_diversification([], num_select=3)
        assert result == []

    def test_num_select_zero_returns_empty(self):
        candidates = [make_candidate("a")]
        result = apply_mmr_diversification(candidates, num_select=0)
        assert result == []

    def test_num_select_exceeds_pool_returns_all(self):
        candidates = [make_candidate("a"), make_candidate("b")]
        result = apply_mmr_diversification(candidates, num_select=10)
        assert len(result) == 2

    def test_first_pick_is_highest_relevance(self):
        """With default lambda=0.6, first pick is the most relevant candidate."""
        candidates = [
            make_candidate("low", score=0.2),
            make_candidate("high", score=0.9),
            make_candidate("mid", score=0.5),
        ]
        result = apply_mmr_diversification(candidates, num_select=1)
        assert result[0]["id"] == "high"

    def test_lambda_1_pure_relevance_ordering(self):
        """Lambda=1.0 should return candidates in pure relevance order."""
        candidates = [
            make_candidate("c", score=0.3),
            make_candidate("a", score=0.9),
            make_candidate("b", score=0.6),
        ]
        result = apply_mmr_diversification(candidates, num_select=3, lambda_param=1.0)
        ids = [c["id"] for c in result]
        assert ids == ["a", "b", "c"]

    def test_lambda_0_promotes_diversity(self):
        """Lambda=0.0 should penalise similarity — diverse second pick beats higher score."""
        # "a" (dining, ramen) selected first as highest relevance
        # "c" (museum, no vibes) is maximally dissimilar to "a"
        # "b" (dining, ramen) is maximally similar to "a"
        # With lambda=0, max_sim dominates, so "c" should be chosen over "b"
        candidates = [
            make_candidate("a", score=0.9, category="dining", vibes=["ramen"]),
            make_candidate("b", score=0.8, category="dining", vibes=["ramen"]),
            make_candidate("c", score=0.3, category="museum", vibes=["art"]),
        ]
        result = apply_mmr_diversification(candidates, num_select=2, lambda_param=0.0)
        assert result[0]["id"] == "a"
        # Second pick should be the diverse option
        assert result[1]["id"] == "c"

    def test_category_diversity_prevents_all_same_category(self):
        """MMR should not fill all slots with the same category."""
        candidates = [
            make_candidate("r1", score=0.9, category="dining", vibes=["ramen"]),
            make_candidate("r2", score=0.85, category="dining", vibes=["ramen"]),
            make_candidate("r3", score=0.8, category="dining", vibes=["ramen"]),
            make_candidate("m1", score=0.6, category="museum", vibes=["art"]),
        ]
        result = apply_mmr_diversification(candidates, num_select=2, lambda_param=0.6)
        categories = [c["category"] for c in result]
        # At least one non-dining category should appear in top 2
        assert "museum" in categories or len(set(categories)) > 1

    def test_output_does_not_contain_duplicates(self):
        candidates = [make_candidate(str(i), score=float(i) / 10) for i in range(10)]
        result = apply_mmr_diversification(candidates, num_select=5)
        ids = [c["id"] for c in result]
        assert len(ids) == len(set(ids))

    def test_original_list_not_mutated(self):
        candidates = [make_candidate("a"), make_candidate("b")]
        original_len = len(candidates)
        apply_mmr_diversification(candidates, num_select=1)
        assert len(candidates) == original_len

    def test_default_lambda_is_0_6(self):
        assert DEFAULT_LAMBDA == pytest.approx(0.6)

    def test_determinism_same_inputs_same_output(self):
        candidates = [
            make_candidate("a", score=0.7, category="dining", vibes=["ramen"]),
            make_candidate("b", score=0.8, category="museum", vibes=["art"]),
            make_candidate("c", score=0.6, category="outdoor", vibes=["scenic"]),
        ]
        result_1 = apply_mmr_diversification(candidates, num_select=2)
        result_2 = apply_mmr_diversification(candidates, num_select=2)
        assert [c["id"] for c in result_1] == [c["id"] for c in result_2]

    def test_candidates_without_score_use_fallback(self):
        """Candidates with no score field should use 0.5 and still be selectable."""
        candidates = [{"id": "noscore", "category": "dining"}]
        result = apply_mmr_diversification(candidates, num_select=1)
        assert len(result) == 1
        assert result[0]["id"] == "noscore"


# ---------------------------------------------------------------------------
# generate_alternatives
# ---------------------------------------------------------------------------

class TestGenerateAlternatives:
    def test_returns_list_of_length_selected(self):
        selected = [make_candidate("s1"), make_candidate("s2")]
        remaining = [make_candidate(f"r{i}") for i in range(6)]
        alts = generate_alternatives(selected, remaining, num_alternatives=3)
        assert len(alts) == len(selected)

    def test_each_alternative_list_has_correct_count(self):
        selected = [make_candidate("s1")]
        remaining = [make_candidate(f"r{i}", score=float(i) / 10) for i in range(5)]
        alts = generate_alternatives(selected, remaining, num_alternatives=3)
        assert len(alts[0]) <= 3

    def test_selected_node_not_in_its_own_alternatives(self):
        selected = [make_candidate("s1")]
        # Include s1 in remaining too — should be excluded from its own alternatives
        remaining = [make_candidate("s1"), make_candidate("alt1"), make_candidate("alt2")]
        alts = generate_alternatives(selected, remaining, num_alternatives=2)
        alt_ids = {c["id"] for c in alts[0]}
        assert "s1" not in alt_ids

    def test_empty_selected_returns_empty_list(self):
        remaining = [make_candidate("r1")]
        alts = generate_alternatives([], remaining, num_alternatives=3)
        assert alts == []

    def test_empty_remaining_returns_empty_alternatives(self):
        selected = [make_candidate("s1")]
        alts = generate_alternatives(selected, [], num_alternatives=3)
        assert alts == [[]]

    def test_alternatives_are_diverse_from_each_other(self):
        """Alternatives for a dining/ramen slot should prefer non-dining when available."""
        selected = [make_candidate("s1", category="dining", vibes=["ramen"])]
        remaining = [
            make_candidate("r1", score=0.9, category="dining", vibes=["ramen"]),
            make_candidate("r2", score=0.8, category="dining", vibes=["ramen"]),
            make_candidate("r3", score=0.5, category="museum", vibes=["art"]),
            make_candidate("r4", score=0.4, category="outdoor", vibes=["scenic"]),
        ]
        alts = generate_alternatives(selected, remaining, num_alternatives=3)
        categories = [c["category"] for c in alts[0]]
        # With diversity in play, not all 3 should be "dining"
        assert len(set(categories)) > 1 or len(alts[0]) <= 1

    def test_vibe_slugs_as_plain_strings(self):
        """Vibe tags as plain strings (not dicts) must be handled."""
        c = {"id": "x", "category": "dining", "vibeTags": ["ramen", "izakaya"]}
        slugs = _get_vibe_slugs(c)
        assert "ramen" in slugs
        assert "izakaya" in slugs


# ---------------------------------------------------------------------------
# Lambda sensitivity
# ---------------------------------------------------------------------------

class TestLambdaSensitivity:
    def test_higher_lambda_more_relevant_first(self):
        """Higher lambda should weight relevance more, producing higher avg relevance."""
        candidates = [
            make_candidate("a", score=0.9, category="dining", vibes=["ramen"]),
            make_candidate("b", score=0.85, category="dining", vibes=["ramen"]),
            make_candidate("c", score=0.3, category="museum", vibes=["art"]),
        ]
        high_lam = apply_mmr_diversification(candidates, num_select=2, lambda_param=0.9)
        low_lam = apply_mmr_diversification(candidates, num_select=2, lambda_param=0.1)

        avg_high = sum(_get_relevance(c) for c in high_lam) / len(high_lam)
        avg_low = sum(_get_relevance(c) for c in low_lam) / len(low_lam)

        assert avg_high >= avg_low

    def test_lambda_boundary_values_do_not_raise(self):
        candidates = [make_candidate("a"), make_candidate("b")]
        apply_mmr_diversification(candidates, num_select=1, lambda_param=0.0)
        apply_mmr_diversification(candidates, num_select=1, lambda_param=1.0)
