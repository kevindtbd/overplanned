"""
Preference merger — combine N persona vectors with fairness weighting.

Merges multiple members' personaSeeds into a single weighted query
vector (natural language form) suitable for Qdrant search.

Weighting strategy:
  - Base weight: 1/N (equal split across members)
  - Fairness adjustment: members with high cumulative debt get their
    preferences boosted so the search vector leans toward under-served tastes
  - Result: a single string query that blends all members proportionally

The merger is purely functional (no DB access). The group_engine feeds
it fairnessState from the Trip record.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class MergedPreference:
    """Weighted merge result for N member persona seeds."""

    __slots__ = (
        "query",
        "member_weights",
        "dominant_vibes",
        "blended_pace",
        "blended_budget",
        "merger_meta",
    )

    def __init__(
        self,
        query: str,
        member_weights: dict[str, float],
        dominant_vibes: list[str],
        blended_pace: str,
        blended_budget: str,
        merger_meta: dict[str, Any],
    ) -> None:
        self.query = query
        self.member_weights = member_weights
        self.dominant_vibes = dominant_vibes
        self.blended_pace = blended_pace
        self.blended_budget = blended_budget
        self.merger_meta = merger_meta


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PACE_RANK: dict[str, int] = {"slow": 0, "moderate": 1, "fast": 2}
_BUDGET_RANK: dict[str, int] = {"budget": 0, "mid": 1, "splurge": 2}

_RANK_TO_PACE: dict[int, str] = {v: k for k, v in _PACE_RANK.items()}
_RANK_TO_BUDGET: dict[int, str] = {v: k for k, v in _BUDGET_RANK.items()}


def _compute_member_weights(
    member_ids: list[str],
    fairness_state: dict[str, Any] | None,
) -> dict[str, float]:
    """
    Compute per-member weights for preference blending.

    Base: 1/N equal split.
    Adjustment: members with cumulative_debt > 0 get a boost proportional
    to their debt (the more they have compromised, the more their preferences
    matter in the next search).

    Weights are normalized to sum to 1.0.
    """
    n = len(member_ids)
    if n == 0:
        return {}

    base = 1.0 / n
    weights: dict[str, float] = {mid: base for mid in member_ids}

    if not fairness_state:
        return weights

    # fairness_state["members"] = { memberId: { "cumulativeDebt": float, ... } }
    member_debts = fairness_state.get("members", {})

    max_debt = max(
        (abs(member_debts.get(mid, {}).get("cumulativeDebt", 0.0)) for mid in member_ids),
        default=0.0,
    )

    if max_debt == 0.0:
        return weights

    # Boost weight proportionally to cumulative debt
    # Scale boost so the most-compromised member gets up to +0.2 extra weight
    MAX_BOOST = 0.20
    for mid in member_ids:
        debt = abs(member_debts.get(mid, {}).get("cumulativeDebt", 0.0))
        boost = (debt / max_debt) * MAX_BOOST
        weights[mid] = base + boost

    # Normalize so weights sum to 1.0
    total = sum(weights.values())
    return {mid: w / total for mid, w in weights.items()}


def _weighted_pace(
    member_seeds: list[dict[str, Any]],
    weights: list[float],
) -> str:
    """Weighted average pace across members. Ties go moderate."""
    if not member_seeds:
        return "moderate"
    total_rank = sum(
        weights[i] * _PACE_RANK.get(s.get("pace", "moderate"), 1)
        for i, s in enumerate(member_seeds)
    )
    rounded = round(total_rank)
    return _RANK_TO_PACE.get(rounded, "moderate")


def _weighted_budget(
    member_seeds: list[dict[str, Any]],
    weights: list[float],
) -> str:
    """Weighted average budget tier. Ties go mid."""
    if not member_seeds:
        return "mid"
    total_rank = sum(
        weights[i] * _BUDGET_RANK.get(s.get("budget", "mid"), 1)
        for i, s in enumerate(member_seeds)
    )
    rounded = round(total_rank)
    return _RANK_TO_BUDGET.get(rounded, "mid")


def _weighted_vibes(
    member_seeds: list[dict[str, Any]],
    weights: list[float],
    top_n: int = 6,
) -> list[str]:
    """
    Aggregate vibes across members by weighted frequency.

    Each vibe earns weight proportional to the sum of weights of members
    who listed it. Returns top_n vibes by weighted score.
    """
    vibe_scores: dict[str, float] = {}
    for i, seed in enumerate(member_seeds):
        for vibe in seed.get("vibes", []):
            vibe_scores[vibe] = vibe_scores.get(vibe, 0.0) + weights[i]

    sorted_vibes = sorted(vibe_scores.items(), key=lambda x: x[1], reverse=True)
    return [v for v, _ in sorted_vibes[:top_n]]


def _build_group_query(
    vibes: list[str],
    pace: str,
    budget: str,
    city: str,
    member_count: int,
) -> str:
    """Build a natural-language Qdrant search query for the group."""
    vibe_str = ", ".join(vibes) if vibes else "diverse local experiences"
    pace_desc = {
        "slow": "relaxed and unhurried",
        "moderate": "well-paced",
        "fast": "packed and energetic",
    }.get(pace, "well-paced")
    budget_desc = {
        "budget": "affordable and local",
        "mid": "mid-range quality",
        "splurge": "premium and special",
    }.get(budget, "mid-range quality")

    return (
        f"Group of {member_count} in {city} seeking {vibe_str} experiences. "
        f"{pace_desc.capitalize()} day, {budget_desc} options. "
        f"Local recommendations preferred, accessible to the whole group."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_preferences(
    member_ids: list[str],
    member_seeds: list[dict[str, Any]],
    city: str,
    fairness_state: dict[str, Any] | None = None,
) -> MergedPreference:
    """
    Merge N member persona seeds into a single weighted preference query.

    Args:
        member_ids:     Ordered list of member IDs (must match member_seeds order).
        member_seeds:   Parallel list of personaSeed dicts per member.
        city:           Trip destination city (for query construction).
        fairness_state: Trip.fairnessState JSON (adjusts weights by debt).

    Returns:
        MergedPreference with query string, per-member weights, and blend metadata.

    Raises:
        ValueError if member_ids and member_seeds have different lengths.
    """
    if len(member_ids) != len(member_seeds):
        raise ValueError(
            f"member_ids ({len(member_ids)}) and member_seeds ({len(member_seeds)}) "
            "must have equal length"
        )

    if not member_ids:
        raise ValueError("Cannot merge preferences for empty member list")

    n = len(member_ids)

    # 1. Compute per-member weights
    weight_map = _compute_member_weights(member_ids, fairness_state)
    weight_list = [weight_map[mid] for mid in member_ids]

    # 2. Blend pace, budget, vibes
    blended_pace = _weighted_pace(member_seeds, weight_list)
    blended_budget = _weighted_budget(member_seeds, weight_list)
    dominant_vibes = _weighted_vibes(member_seeds, weight_list)

    # 3. Build search query
    query = _build_group_query(
        vibes=dominant_vibes,
        pace=blended_pace,
        budget=blended_budget,
        city=city,
        member_count=n,
    )

    merger_meta = {
        "memberCount": n,
        "weightMap": weight_map,
        "dominantVibes": dominant_vibes,
        "blendedPace": blended_pace,
        "blendedBudget": blended_budget,
        "fairnessAdjusted": fairness_state is not None,
    }

    logger.debug(
        "Preference merge complete: city=%s members=%d vibes=%s pace=%s budget=%s",
        city,
        n,
        dominant_vibes,
        blended_pace,
        blended_budget,
    )

    return MergedPreference(
        query=query,
        member_weights=weight_map,
        dominant_vibes=dominant_vibes,
        blended_pace=blended_pace,
        blended_budget=blended_budget,
        merger_meta=merger_meta,
    )


def score_candidate_per_member(
    candidate: dict[str, Any],
    member_seeds: list[dict[str, Any]],
    member_ids: list[str],
) -> dict[str, float]:
    """
    Score a single ActivityNode candidate against each member's persona.

    Returns a dict of { memberId -> preference_score [0.0, 1.0] }

    Score = vibe_overlap_ratio (using member's vibes vs node's vibeTags)
    adjusted by price distance from member's budget preference.
    """
    budget_to_price = {"budget": 1, "mid": 2, "splurge": 3}

    scores: dict[str, float] = {}
    node_vibe_slugs: set[str] = {
        v["slug"]
        for v in (candidate.get("vibeTags") or [])
        if isinstance(v, dict) and "slug" in v
    }
    node_price = candidate.get("priceLevel")

    for mid, seed in zip(member_ids, member_seeds):
        persona_vibes: set[str] = set(seed.get("vibes", []))

        # Vibe overlap
        if persona_vibes and node_vibe_slugs:
            overlap = len(persona_vibes & node_vibe_slugs)
            vibe_score = min(overlap / len(persona_vibes), 1.0)
        elif not persona_vibes:
            vibe_score = 0.5
        else:
            vibe_score = 0.1

        # Price penalty
        budget = seed.get("budget", "mid")
        target_price = budget_to_price.get(budget, 2)
        if node_price is not None:
            price_distance = abs(node_price - target_price)
            price_penalty = min(price_distance * 0.1, 0.2)
        else:
            price_penalty = 0.0

        scores[mid] = max(0.0, vibe_score - price_penalty)

    return scores
