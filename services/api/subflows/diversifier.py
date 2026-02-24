"""
MMR Diversifier — V2 ML Pipeline Phase 5.4.

Applies Maximal Marginal Relevance (MMR) post-processing to a ranked
candidate list to prevent homogeneous itineraries (all-ramen, all-museum
runs etc.).

MMR formula
-----------
    score_i = lambda * relevance_i - (1 - lambda) * max_sim(i, S)

where S is the set of already-selected candidates and max_sim is the
maximum similarity between candidate i and any selected candidate.

Similarity metric
-----------------
A combined score of:
  - Category overlap: 1.0 if same category, 0.0 otherwise
  - Vibe tag Jaccard similarity: |A ∩ B| / |A ∪ B|

    similarity = 0.5 * category_overlap + 0.5 * jaccard_vibes

Design notes
------------
- Pure functions — no I/O, no side effects.
- Lambda defaults to 0.6 (favours relevance slightly over diversity).
- "relevance" is taken from the candidate's "score" or "convergenceScore"
  field. If neither is present, 0.5 is assumed.
- Candidates must have an "id" field.
- The functions operate on plain dicts — no ORM types.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default trade-off weight (higher = more relevance, lower = more diversity)
DEFAULT_LAMBDA: float = 0.6

# Weights for category vs. vibe-tag similarity
_CATEGORY_WEIGHT: float = 0.5
_VIBE_WEIGHT: float = 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_mmr_diversification(
    candidates: list[dict],
    num_select: int,
    lambda_param: float = DEFAULT_LAMBDA,
) -> list[dict]:
    """
    Select top ``num_select`` candidates using Maximal Marginal Relevance.

    Args:
        candidates:   List of ActivityNode-like dicts. Each should carry
                      an "id", optional "category", optional "vibeTags"
                      (list of dicts with "slug" key or plain strings),
                      and a relevance score ("score" or "convergenceScore").
        num_select:   How many candidates to return.
        lambda_param: Trade-off parameter [0, 1].
                      1.0 = pure relevance ranking (no diversity).
                      0.0 = pure diversity (greedy farthest-point sampling).
                      Default: 0.6.

    Returns:
        A new list of up to ``num_select`` candidates in MMR-selected order.
        The original list is not mutated.
    """
    if not candidates:
        return []

    num_select = min(num_select, len(candidates))

    if num_select <= 0:
        return []

    # Work with copies to avoid mutating the caller's list
    pool: list[dict] = list(candidates)
    selected: list[dict] = []

    while len(selected) < num_select and pool:
        best_idx: int | None = None
        best_mmr: float = float("-inf")

        for i, candidate in enumerate(pool):
            relevance = _get_relevance(candidate)

            if not selected:
                # First selection: pure relevance
                mmr_score = relevance
            else:
                max_sim = max(
                    _similarity(candidate, s) for s in selected
                )
                mmr_score = (
                    lambda_param * relevance - (1 - lambda_param) * max_sim
                )

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        if best_idx is None:
            break

        chosen = pool.pop(best_idx)
        selected.append(chosen)

    logger.debug(
        "MMR selected %d/%d candidates (lambda=%.2f)",
        len(selected),
        len(candidates),
        lambda_param,
    )

    return selected


def generate_alternatives(
    selected: list[dict],
    remaining: list[dict],
    num_alternatives: int = 3,
) -> list[list[dict]]:
    """
    For each selected candidate, generate a list of diverse alternatives
    drawn from ``remaining``.

    Each alternative list is produced by MMR over ``remaining`` with
    the given selected candidate excluded from the similarity penalty
    baseline — so the alternatives are diverse relative to each other
    rather than relative to the selected slot.

    Args:
        selected:         Candidates that have already been chosen for slots.
        remaining:        Pool of candidates not yet placed in any slot.
        num_alternatives: How many alternatives to generate per slot.
                          Default: 3.

    Returns:
        A list of length ``len(selected)``. Each element is a list of up to
        ``num_alternatives`` alternative candidates for the corresponding
        selected slot.
    """
    if not selected or not remaining:
        return [[] for _ in selected]

    alternatives: list[list[dict]] = []

    for slot_candidate in selected:
        # Build a mini-pool: exclude the slot_candidate itself from remaining
        slot_id = slot_candidate.get("id")
        mini_pool = [c for c in remaining if c.get("id") != slot_id]

        # Score the mini-pool: maximize similarity to slot_candidate
        # (we want alternatives that are similar in purpose but different
        # enough from each other — MMR within the alternatives pool)
        alts = apply_mmr_diversification(
            candidates=mini_pool,
            num_select=num_alternatives,
            lambda_param=0.5,  # equal weight diversity vs relevance for alts
        )

        alternatives.append(alts)

    return alternatives


# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------


def _get_relevance(candidate: dict) -> float:
    """
    Extract a numeric relevance score from a candidate dict.

    Checks "score" first, then "convergenceScore".
    Falls back to 0.5 if neither is present or both are None.
    """
    score = candidate.get("score")
    if score is not None:
        try:
            return float(score)
        except (TypeError, ValueError):
            pass

    conv = candidate.get("convergenceScore")
    if conv is not None:
        try:
            return float(conv)
        except (TypeError, ValueError):
            pass

    return 0.5


def _get_category(candidate: dict) -> str:
    """Extract the category string, lower-cased. Empty string if absent."""
    cat = candidate.get("category")
    if cat and isinstance(cat, str):
        return cat.lower().strip()
    return ""


def _get_vibe_slugs(candidate: dict) -> frozenset[str]:
    """
    Extract vibe tag slugs from a candidate.

    Handles both:
      - list of dicts: [{"slug": "coffee-crawl"}, ...]
      - list of strings: ["coffee-crawl", ...]
    """
    raw = candidate.get("vibeTags") or []
    slugs: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            slug = item.get("slug") or item.get("name") or ""
        else:
            slug = str(item)
        slug = slug.lower().strip()
        if slug:
            slugs.add(slug)
    return frozenset(slugs)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two sets. Returns 0.0 for two empty sets."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _similarity(a: dict, b: dict) -> float:
    """
    Compute similarity between two candidates.

    similarity = 0.5 * category_overlap + 0.5 * jaccard_vibes

    Returns a value in [0.0, 1.0].
    """
    cat_a = _get_category(a)
    cat_b = _get_category(b)
    category_overlap = 1.0 if cat_a and cat_a == cat_b else 0.0

    vibes_a = _get_vibe_slugs(a)
    vibes_b = _get_vibe_slugs(b)
    vibe_similarity = _jaccard(vibes_a, vibes_b)

    return _CATEGORY_WEIGHT * category_overlap + _VIBE_WEIGHT * vibe_similarity
