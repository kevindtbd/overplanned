"""
Phase 6.8 -- Pareto Group Ranker

Individual ranking optimizes for one user's preferences. Group ranking has
multiple objective functions that conflict. You cannot just average persona scores.

For each candidate activity, compute:
  1. Per-member relevance score (from individual ranker / persona)
  2. Fairness score (how evenly does this candidate distribute satisfaction?)
  3. Novelty bonus (avoids repeating what one member has already done)

Then find the Pareto-optimal set: candidates where no other candidate is strictly
better on all three dimensions.

CPU-only: pure numpy, no PyTorch/TensorFlow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParetoGroupConfig:
    """Configuration for Pareto group ranking."""

    fairness_weight: float = 0.3
    novelty_weight: float = 0.2
    min_group_size: int = 2


class ParetoGroupRanker:
    """Multi-objective group ranker using Pareto dominance.

    Balances individual relevance, group fairness, and novelty to find
    non-dominated candidates for group trips.
    """

    def __init__(self, config: ParetoGroupConfig | None = None) -> None:
        self.config = config or ParetoGroupConfig()

    def compute_member_scores(
        self,
        member_rankings: dict[str, list[tuple[str, float]]],
    ) -> dict[str, dict[str, float]]:
        """Map candidate_id -> member_id -> score from per-member rankings.

        Args:
            member_rankings: member_id -> [(candidate_id, score), ...]

        Returns:
            candidate_id -> {member_id: score}
        """
        result: dict[str, dict[str, float]] = {}
        for member_id, rankings in member_rankings.items():
            for candidate_id, score in rankings:
                if candidate_id not in result:
                    result[candidate_id] = {}
                result[candidate_id][member_id] = score
        return result

    def compute_fairness(self, candidate_scores: dict[str, float]) -> float:
        """Compute fairness score for a candidate.

        Fairness = 1.0 - normalized_std_dev(scores).
        Perfectly fair when all members are equally satisfied (std = 0).
        Returns 1.0 for single-member or empty scores.

        Args:
            candidate_scores: member_id -> relevance score

        Returns:
            Float in [0.0, 1.0], higher = more fair.
        """
        if len(candidate_scores) <= 1:
            return 1.0

        scores = np.array(list(candidate_scores.values()), dtype=np.float64)
        mean = np.mean(scores)

        if mean == 0.0:
            # All zeros = perfectly "fair" in a degenerate sense
            return 1.0

        std = np.std(scores)
        # Normalize std by mean (coefficient of variation), clamp to [0, 1]
        normalized_std = min(float(std / abs(mean)), 1.0)
        return 1.0 - normalized_std

    def compute_novelty(
        self,
        candidate_id: str,
        member_histories: dict[str, set[str]],
    ) -> float:
        """Compute novelty score for a candidate.

        Novelty = fraction of members who have NOT seen this candidate before.

        Args:
            candidate_id: The candidate activity ID.
            member_histories: member_id -> set of previously seen candidate IDs.

        Returns:
            Float in [0.0, 1.0], higher = more novel.
        """
        if not member_histories:
            return 1.0

        n_members = len(member_histories)
        n_unseen = sum(
            1 for history in member_histories.values()
            if candidate_id not in history
        )
        return n_unseen / n_members

    def _compute_objective_vector(
        self,
        candidate_id: str,
        candidate_member_scores: dict[str, float],
        member_histories: dict[str, set[str]],
    ) -> np.ndarray:
        """Compute the 3D objective vector: [avg_relevance, fairness, novelty]."""
        scores = list(candidate_member_scores.values())
        avg_relevance = float(np.mean(scores)) if scores else 0.0
        fairness = self.compute_fairness(candidate_member_scores)
        novelty = self.compute_novelty(candidate_id, member_histories)
        return np.array([avg_relevance, fairness, novelty], dtype=np.float64)

    def _weighted_aggregate(self, obj_vector: np.ndarray) -> float:
        """Compute weighted aggregate of the objective vector.

        Weights: relevance = 1 - fairness_weight - novelty_weight,
                 fairness = fairness_weight, novelty = novelty_weight.
        """
        fw = self.config.fairness_weight
        nw = self.config.novelty_weight
        rw = 1.0 - fw - nw
        weights = np.array([rw, fw, nw], dtype=np.float64)
        return float(np.dot(obj_vector, weights))

    def find_pareto_front(
        self,
        candidates: list[str],
        member_rankings: dict[str, list[tuple[str, float]]],
        member_histories: dict[str, set[str]],
    ) -> list[str]:
        """Find the Pareto-optimal set of candidates.

        Pareto dominance: candidate A dominates B if A >= B on all dimensions
        and A > B on at least one.

        Returns:
            Non-dominated candidate IDs, sorted by weighted aggregate (descending).
        """
        if not candidates:
            return []

        all_scores = self.compute_member_scores(member_rankings)

        # Compute objective vectors for all candidates
        obj_vectors: dict[str, np.ndarray] = {}
        for cid in candidates:
            c_scores = all_scores.get(cid, {})
            obj_vectors[cid] = self._compute_objective_vector(
                cid, c_scores, member_histories
            )

        # Find non-dominated set
        non_dominated: list[str] = []
        for cid in candidates:
            dominated = False
            for other_cid in candidates:
                if cid == other_cid:
                    continue
                ov_other = obj_vectors[other_cid]
                ov_self = obj_vectors[cid]
                # other dominates self if all >= and at least one >
                if np.all(ov_other >= ov_self) and np.any(ov_other > ov_self):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(cid)

        # Sort by weighted aggregate, descending
        non_dominated.sort(
            key=lambda cid: self._weighted_aggregate(obj_vectors[cid]),
            reverse=True,
        )
        return non_dominated

    def rank_group(
        self,
        member_rankings: dict[str, list[tuple[str, float]]],
        member_histories: dict[str, set[str]],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Full group ranking pipeline.

        1. Collect all candidate IDs from member rankings.
        2. Find the Pareto front.
        3. Rank by weighted aggregate.
        4. Return top_k results.

        Args:
            member_rankings: member_id -> [(candidate_id, score), ...]
            member_histories: member_id -> set of previously seen candidate IDs
            top_k: Maximum number of results to return.

        Returns:
            List of (candidate_id, weighted_score) tuples, descending.
        """
        # Collect all unique candidate IDs
        all_candidates: set[str] = set()
        for rankings in member_rankings.values():
            for cid, _ in rankings:
                all_candidates.add(cid)

        candidates = list(all_candidates)
        pareto_front = self.find_pareto_front(
            candidates, member_rankings, member_histories
        )

        # Compute weighted scores for the Pareto front
        all_scores = self.compute_member_scores(member_rankings)
        results: list[tuple[str, float]] = []
        for cid in pareto_front:
            c_scores = all_scores.get(cid, {})
            obj_vec = self._compute_objective_vector(cid, c_scores, member_histories)
            weighted = self._weighted_aggregate(obj_vec)
            results.append((cid, weighted))

        # Already sorted by find_pareto_front, but re-sort to be safe
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
