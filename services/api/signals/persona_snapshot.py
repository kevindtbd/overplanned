"""
Persona dimension snapshot -- aggregates a user's BehavioralSignal history
into a lightweight persona dict for denormalization into RankingEvent or
generation context.

Each dimension is a float in [0, 1]:
  - adventure_score: preference for adventurous / off-beat activities
  - budget_sensitivity: preference for low-cost options
  - food_focus: how much the user engages with dining signals
  - culture_interest: engagement with cultural / museum / historic signals
  - nature_preference: engagement with outdoor / nature signals

Returns an empty dict for new users with no signal history.
"""

import logging
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import BehavioralSignal
from services.api.signals.taxonomy import get_training_weight, is_positive_signal

logger = logging.getLogger(__name__)

# Maps activity categories to persona dimensions.
# A signal on a slot/activity with category X contributes to dimension Y.
_CATEGORY_DIMENSION_MAP: dict[str, str] = {
    # adventure
    "adventure": "adventure_score",
    "outdoor": "adventure_score",
    "sport": "adventure_score",
    "nightlife": "adventure_score",
    # budget
    "street_food": "budget_sensitivity",
    "market": "budget_sensitivity",
    "free_attraction": "budget_sensitivity",
    # food
    "dining": "food_focus",
    "cafe": "food_focus",
    "bar": "food_focus",
    "street_food": "food_focus",
    "market": "food_focus",
    # culture
    "museum": "culture_interest",
    "temple": "culture_interest",
    "shrine": "culture_interest",
    "historic": "culture_interest",
    "gallery": "culture_interest",
    # nature
    "park": "nature_preference",
    "garden": "nature_preference",
    "hike": "nature_preference",
    "beach": "nature_preference",
    "outdoor": "nature_preference",
}

_ALL_DIMENSIONS = [
    "adventure_score",
    "budget_sensitivity",
    "food_focus",
    "culture_interest",
    "nature_preference",
]


async def get_persona_snapshot(session: AsyncSession, user_id: str) -> dict:
    """Build a persona snapshot from aggregated BehavioralSignal history.

    Strategy:
      1. Fetch all signals for the user (type + value + weight)
      2. For each signal, look at signalType to compute a weighted
         contribution per persona dimension
      3. Normalize each dimension to [0, 1]

    Returns empty dict if no signals exist.
    """
    try:
        stmt = (
            select(
                BehavioralSignal.signalType,
                BehavioralSignal.signalValue,
                BehavioralSignal.signal_weight,
            )
            .where(BehavioralSignal.userId == user_id)
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            return {}

        # Accumulate weighted scores per dimension
        dim_scores: dict[str, float] = defaultdict(float)
        dim_counts: dict[str, int] = defaultdict(int)

        for signal_type, signal_value, signal_weight in rows:
            training_weight = get_training_weight(signal_type)
            polarity = 1.0 if is_positive_signal(signal_type) else -0.5

            # Map signal types to dimensions heuristically
            dimensions = _signal_type_to_dimensions(signal_type)
            for dim in dimensions:
                contribution = signal_value * training_weight * signal_weight * polarity
                dim_scores[dim] += contribution
                dim_counts[dim] += 1

        # Normalize to [0, 1] using sigmoid-like clamping
        snapshot: dict[str, float] = {}
        for dim in _ALL_DIMENSIONS:
            count = dim_counts.get(dim, 0)
            if count == 0:
                continue
            raw = dim_scores[dim] / count
            # Clamp to [0, 1]
            normalized = max(0.0, min(1.0, (raw + 1.0) / 2.0))
            snapshot[dim] = round(normalized, 3)

        return snapshot

    except Exception:
        logger.exception("Failed to compute persona snapshot for user=%s", user_id)
        return {}


def _signal_type_to_dimensions(signal_type: str) -> list[str]:
    """Map a signal type to the persona dimensions it informs.

    - discover_* signals contribute to adventure + food (exploration behavior)
    - slot_confirmed / slot_locked contribute broadly
    - pivot_* contribute to adventure (willingness to change plans)
    """
    if signal_type.startswith("discover_"):
        return ["adventure_score", "food_focus"]
    if signal_type in ("pivot_accepted",):
        return ["adventure_score"]
    if signal_type in ("pivot_rejected",):
        return ["adventure_score"]  # negative polarity handled by caller
    if signal_type in ("card_viewed", "card_impression"):
        return ["culture_interest", "food_focus"]
    # Slot-level signals: broad contribution
    if "slot" in signal_type or "pre_trip" in signal_type:
        return ["adventure_score", "culture_interest"]
    return []
