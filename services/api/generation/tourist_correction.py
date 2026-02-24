"""
Tourist correction post-filter for itinerary ranking.

Applies after rank_candidates_with_llm() to demote overly tourist-heavy
nodes when the city skews local. This is a Phase 1 band-aid — it gets
removed when U-SASRec + DLRM goes live.

Feature flag: TOURIST_CORRECTION_ENABLED (default off).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds — all three conditions must be true for a node to be demoted.
TOURIST_SCORE_THRESHOLD = 0.65       # tourist_score must be strictly > this
LOCAL_BIAS_THRESHOLD = 0.55          # city's local_vs_tourist_bias must be strictly > this
MIN_SOURCE_COUNT = 3                 # node's source_count must be >= this


def _flag_enabled() -> bool:
    """Return True when the tourist correction feature flag is on."""
    return os.environ.get("TOURIST_CORRECTION_ENABLED", "").lower() in ("1", "true", "yes")


def compute_local_vs_tourist_bias(candidates: list[dict[str, Any]]) -> float:
    """
    Calculate the proportion of high-tourist-score nodes in the candidate set.

    A node counts as "high tourist" when tourist_score > TOURIST_SCORE_THRESHOLD.
    Returns a float in [0.0, 1.0]. Returns 0.0 for an empty candidate list.

    Args:
        candidates: list of ActivityNode dicts, each may have a 'tourist_score' key.

    Returns:
        Proportion of candidates whose tourist_score exceeds the threshold.
    """
    if not candidates:
        return 0.0

    high_tourist_count = sum(
        1
        for c in candidates
        if (c.get("tourist_score") or 0.0) > TOURIST_SCORE_THRESHOLD
    )
    return high_tourist_count / len(candidates)


def apply_tourist_correction(
    candidates: list[dict[str, Any]],
    city: str,
) -> list[dict[str, Any]]:
    """
    Demote tourist-heavy nodes to the bottom of the ranked list.

    This is a pure post-filter — it does NOT remove any candidate, only
    re-orders them. The relative order of non-demoted nodes is preserved,
    and demoted nodes are appended at the end in their original relative order.

    Demotion criteria (all three must be true):
      1. candidate tourist_score > TOURIST_SCORE_THRESHOLD (0.65)
      2. city local_vs_tourist_bias > LOCAL_BIAS_THRESHOLD (0.55)
         (computed from the candidate set itself)
      3. candidate source_count >= MIN_SOURCE_COUNT (3)

    When the feature flag is off this function is a no-op.

    Args:
        candidates: Ranked list of ActivityNode dicts (as returned from the LLM
                    ranker or already sorted). The list order is treated as the
                    current ranking — index 0 = best.
        city:       City name (used in log messages for observability).

    Returns:
        Re-ordered candidate list with demoted nodes at the end.
    """
    if not _flag_enabled():
        logger.debug("tourist_correction: feature flag off, returning candidates unchanged")
        return candidates

    if not candidates:
        return candidates

    city_bias = compute_local_vs_tourist_bias(candidates)

    if city_bias <= LOCAL_BIAS_THRESHOLD:
        logger.debug(
            "tourist_correction: city=%s bias=%.3f <= threshold=%.2f, no correction applied",
            city,
            city_bias,
            LOCAL_BIAS_THRESHOLD,
        )
        return candidates

    kept: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []

    for candidate in candidates:
        tourist_score = candidate.get("tourist_score") or 0.0
        source_count = candidate.get("source_count") or candidate.get("sourceCount") or 0

        should_demote = (
            tourist_score > TOURIST_SCORE_THRESHOLD
            and source_count >= MIN_SOURCE_COUNT
        )

        if should_demote:
            demoted.append(candidate)
        else:
            kept.append(candidate)

    if demoted:
        logger.info(
            "tourist_correction: city=%s bias=%.3f demoted=%d/%d candidates",
            city,
            city_bias,
            len(demoted),
            len(candidates),
        )

    return kept + demoted
