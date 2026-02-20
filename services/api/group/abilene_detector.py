"""
Abilene Paradox Detector.

Detects when a group collectively votes for an option that nobody actually
wants — the "Abilene Paradox": a group reaches consensus on a choice no
individual member truly prefers.

Named after the management anecdote: a family drives to Abilene, Texas in
the summer heat, and none of them wanted to go — they each went along
assuming others wanted to.

Detection logic:
  Compute per-member "enthusiasm" for the current group choice:
    enthusiasm = 1.0 - (normalized_preference_rank / total_candidates)
                 where 1.0 = top choice, 0.0 = last choice

  If ALL members' enthusiasm scores fall below ENTHUSIASM_THRESHOLD (0.4),
  the group is in Abilene territory — everyone is just going along.

  This triggers a dissent prompt on the frontend inviting members to
  re-rank or propose an alternative without social pressure.

Determinism guarantee:
  Same inputs -> same output. No external calls. No randomness.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# If ALL member enthusiasm scores fall below this, trigger dissent prompt.
ENTHUSIASM_THRESHOLD = 0.4

# Minimum candidate count to run detection (too few candidates = not meaningful).
MIN_CANDIDATES_FOR_DETECTION = 3


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AbileneResult:
    """Result of Abilene paradox detection for a single slot vote."""
    is_abilene: bool
    """True if the group is in Abilene territory (all lukewarm)."""

    member_enthusiasm: dict[str, float]
    """Per-member enthusiasm scores [0.0, 1.0]."""

    group_avg_enthusiasm: float
    """Mean enthusiasm across all members."""

    min_enthusiasm: float
    """Lowest individual enthusiasm score."""

    threshold: float
    """Threshold used for detection."""

    recommendation: str | None
    """Human-readable message for the dissent prompt (None if not Abilene)."""


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class AbileneDetector:
    """
    Detects Abilene paradox in group votes.

    Usage:
        detector = AbileneDetector()
        result = detector.detect(
            chosen_node_id="node-abc",
            member_preference_ranks={"user-1": 3, "user-2": 5, "user-3": 4},
            total_candidates=10,
        )
        if result.is_abilene:
            # show dissent prompt
    """

    def __init__(self, enthusiasm_threshold: float = ENTHUSIASM_THRESHOLD) -> None:
        self._threshold = enthusiasm_threshold

    def detect(
        self,
        chosen_node_id: str,
        member_preference_ranks: dict[str, int],
        total_candidates: int,
    ) -> AbileneResult:
        """
        Run Abilene detection for a voted slot.

        Args:
            chosen_node_id:          ID of the ActivityNode chosen by the vote.
            member_preference_ranks: { memberId -> rank member gave to chosen_node }
                                     Rank 1 = top choice, higher = less preferred.
            total_candidates:        Total candidates available (used to normalize).

        Returns:
            AbileneResult with is_abilene flag and enthusiasm breakdown.
        """
        if not member_preference_ranks:
            return AbileneResult(
                is_abilene=False,
                member_enthusiasm={},
                group_avg_enthusiasm=1.0,
                min_enthusiasm=1.0,
                threshold=self._threshold,
                recommendation=None,
            )

        if total_candidates < MIN_CANDIDATES_FOR_DETECTION:
            # Too few candidates to meaningfully distinguish enthusiasm
            return AbileneResult(
                is_abilene=False,
                member_enthusiasm={
                    mid: 1.0 for mid in member_preference_ranks
                },
                group_avg_enthusiasm=1.0,
                min_enthusiasm=1.0,
                threshold=self._threshold,
                recommendation=None,
            )

        # Compute enthusiasm per member
        # enthusiasm = 1 - (rank - 1) / (total_candidates - 1)
        # Rank 1 -> enthusiasm 1.0 (their top choice)
        # Rank N -> enthusiasm 0.0 (their last choice)
        denom = max(total_candidates - 1, 1)
        enthusiasm: dict[str, float] = {}
        for mid, rank in member_preference_ranks.items():
            normalized_rank = max(0, min(rank - 1, denom))
            enthusiasm[mid] = 1.0 - (normalized_rank / denom)

        scores = list(enthusiasm.values())
        avg = sum(scores) / len(scores)
        min_score = min(scores)
        all_lukewarm = all(s < self._threshold for s in scores)

        recommendation = None
        if all_lukewarm:
            recommendation = (
                "It looks like nobody is particularly excited about this option. "
                "Does the group want to explore some alternatives?"
            )
            logger.info(
                "Abilene paradox detected: node=%s avg_enthusiasm=%.2f min=%.2f",
                chosen_node_id,
                avg,
                min_score,
            )

        return AbileneResult(
            is_abilene=all_lukewarm,
            member_enthusiasm=enthusiasm,
            group_avg_enthusiasm=round(avg, 4),
            min_enthusiasm=round(min_score, 4),
            threshold=self._threshold,
            recommendation=recommendation,
        )

    def score_enthusiasm(
        self,
        preference_rank: int,
        total_candidates: int,
    ) -> float:
        """
        Utility: compute enthusiasm score for a single rank/total pair.
        Exposed for use in frontend data prep.
        """
        denom = max(total_candidates - 1, 1)
        normalized = max(0, min(preference_rank - 1, denom))
        return 1.0 - (normalized / denom)
