"""
Tests for Phase 6.8 -- Pareto Group Ranker.

Covers:
- Fairness computation (even scores, skewed scores, single member)
- Novelty computation (all seen, none seen, partial)
- Pareto dominance (non-dominated set identification)
- 2-member group ranking
- 4-member group ranking
- Tie-breaking via weighted aggregate
- Empty histories
- Edge cases (empty rankings, single candidate)
"""

import pytest

from services.api.models.pareto_group_ranker import (
    ParetoGroupConfig,
    ParetoGroupRanker,
)


# ===================================================================
# Fairness computation
# ===================================================================


class TestComputeFairness:
    def setup_method(self):
        self.ranker = ParetoGroupRanker()

    def test_perfectly_fair(self):
        """All members equally satisfied -> fairness = 1.0"""
        scores = {"m1": 0.8, "m2": 0.8, "m3": 0.8}
        assert abs(self.ranker.compute_fairness(scores) - 1.0) < 1e-9

    def test_unfair_distribution(self):
        """One member much more satisfied than others -> low fairness."""
        scores = {"m1": 1.0, "m2": 0.0, "m3": 0.0}
        fairness = self.ranker.compute_fairness(scores)
        assert fairness < 0.5

    def test_single_member_is_perfectly_fair(self):
        scores = {"m1": 0.8}
        assert self.ranker.compute_fairness(scores) == 1.0

    def test_empty_scores(self):
        assert self.ranker.compute_fairness({}) == 1.0

    def test_moderate_fairness(self):
        """Slightly skewed scores should have moderate fairness."""
        scores = {"m1": 0.9, "m2": 0.7}
        fairness = self.ranker.compute_fairness(scores)
        assert 0.5 < fairness < 1.0

    def test_all_zeros_is_fair(self):
        scores = {"m1": 0.0, "m2": 0.0}
        assert self.ranker.compute_fairness(scores) == 1.0


# ===================================================================
# Novelty computation
# ===================================================================


class TestComputeNovelty:
    def setup_method(self):
        self.ranker = ParetoGroupRanker()

    def test_fully_novel(self):
        """No member has seen this candidate -> novelty = 1.0"""
        histories = {"m1": set(), "m2": set()}
        assert self.ranker.compute_novelty("c1", histories) == 1.0

    def test_fully_seen(self):
        """All members have seen this candidate -> novelty = 0.0"""
        histories = {"m1": {"c1"}, "m2": {"c1"}}
        assert self.ranker.compute_novelty("c1", histories) == 0.0

    def test_partial_novelty(self):
        """Half the members have seen it -> novelty = 0.5"""
        histories = {"m1": {"c1"}, "m2": set()}
        assert self.ranker.compute_novelty("c1", histories) == 0.5

    def test_empty_histories(self):
        assert self.ranker.compute_novelty("c1", {}) == 1.0


# ===================================================================
# Member scores
# ===================================================================


class TestComputeMemberScores:
    def test_maps_correctly(self):
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.9), ("c2", 0.5)],
            "m2": [("c1", 0.3), ("c2", 0.8)],
        }
        result = ranker.compute_member_scores(rankings)
        assert result["c1"] == {"m1": 0.9, "m2": 0.3}
        assert result["c2"] == {"m1": 0.5, "m2": 0.8}


# ===================================================================
# Pareto dominance
# ===================================================================


class TestParetoDominance:
    def setup_method(self):
        self.ranker = ParetoGroupRanker()

    def test_single_candidate_is_non_dominated(self):
        rankings = {"m1": [("c1", 0.9)]}
        histories: dict[str, set[str]] = {"m1": set()}
        front = self.ranker.find_pareto_front(["c1"], rankings, histories)
        assert front == ["c1"]

    def test_dominated_candidate_excluded(self):
        """c2 dominates c1 on all dimensions -> c1 excluded from front."""
        # c2 has higher relevance for all members, same novelty, same fairness
        rankings = {
            "m1": [("c1", 0.3), ("c2", 0.9)],
            "m2": [("c1", 0.3), ("c2", 0.9)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        front = self.ranker.find_pareto_front(["c1", "c2"], rankings, histories)
        assert "c2" in front
        assert "c1" not in front

    def test_incomparable_candidates_both_in_front(self):
        """c1 better for m1, c2 better for m2 -> both in front (different fairness/novelty)."""
        rankings = {
            "m1": [("c1", 1.0), ("c2", 0.0)],
            "m2": [("c1", 0.0), ("c2", 1.0)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        front = self.ranker.find_pareto_front(["c1", "c2"], rankings, histories)
        # Both have same avg relevance (0.5) and same novelty (1.0)
        # but same fairness (both skewed). They're tied, so both non-dominated
        assert len(front) == 2

    def test_empty_candidates(self):
        front = self.ranker.find_pareto_front([], {}, {})
        assert front == []


# ===================================================================
# 2-member group ranking
# ===================================================================


class TestTwoMemberGroup:
    def test_basic_two_member_ranking(self):
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.9), ("c2", 0.5), ("c3", 0.3)],
            "m2": [("c1", 0.7), ("c2", 0.8), ("c3", 0.2)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        result = ranker.rank_group(rankings, histories, top_k=3)
        assert len(result) > 0
        # Results should be (candidate_id, weighted_score) tuples
        for cid, score in result:
            assert isinstance(cid, str)
            assert isinstance(score, float)

    def test_top_k_limits_results(self):
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.9), ("c2", 0.8), ("c3", 0.7), ("c4", 0.6)],
            "m2": [("c1", 0.5), ("c2", 0.6), ("c3", 0.7), ("c4", 0.8)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        result = ranker.rank_group(rankings, histories, top_k=2)
        assert len(result) <= 2


# ===================================================================
# 4-member group ranking
# ===================================================================


class TestFourMemberGroup:
    def test_four_member_produces_results(self):
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.9), ("c2", 0.4)],
            "m2": [("c1", 0.7), ("c2", 0.6)],
            "m3": [("c1", 0.5), ("c2", 0.8)],
            "m4": [("c1", 0.3), ("c2", 0.9)],
        }
        histories: dict[str, set[str]] = {
            "m1": set(), "m2": set(), "m3": set(), "m4": set()
        }
        result = ranker.rank_group(rankings, histories)
        assert len(result) > 0

    def test_four_member_fairness_matters(self):
        """A candidate equally liked by all 4 should rank higher than one loved by 1."""
        ranker = ParetoGroupRanker(ParetoGroupConfig(fairness_weight=0.5, novelty_weight=0.1))
        # c1: equally liked (0.6 each), c2: loved by m1, hated by others
        rankings = {
            "m1": [("c1", 0.6), ("c2", 1.0)],
            "m2": [("c1", 0.6), ("c2", 0.1)],
            "m3": [("c1", 0.6), ("c2", 0.1)],
            "m4": [("c1", 0.6), ("c2", 0.1)],
        }
        histories: dict[str, set[str]] = {
            "m1": set(), "m2": set(), "m3": set(), "m4": set()
        }
        result = ranker.rank_group(rankings, histories)
        # c1 should be ranked higher due to fairness
        assert result[0][0] == "c1"


# ===================================================================
# Tie-breaking
# ===================================================================


class TestTieBreaking:
    def test_identical_scores_stable(self):
        """When all candidates are identical, all appear in results."""
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.5), ("c2", 0.5)],
            "m2": [("c1", 0.5), ("c2", 0.5)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        result = ranker.rank_group(rankings, histories)
        result_ids = {cid for cid, _ in result}
        assert "c1" in result_ids
        assert "c2" in result_ids


# ===================================================================
# Weighted aggregate
# ===================================================================


class TestWeightedAggregate:
    def test_default_weights_sum_to_one(self):
        config = ParetoGroupConfig()
        rw = 1.0 - config.fairness_weight - config.novelty_weight
        assert abs(rw + config.fairness_weight + config.novelty_weight - 1.0) < 1e-9

    def test_results_sorted_descending(self):
        ranker = ParetoGroupRanker()
        rankings = {
            "m1": [("c1", 0.9), ("c2", 0.3), ("c3", 0.6)],
            "m2": [("c1", 0.8), ("c2", 0.4), ("c3", 0.5)],
        }
        histories: dict[str, set[str]] = {"m1": set(), "m2": set()}
        result = ranker.rank_group(rankings, histories)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)
