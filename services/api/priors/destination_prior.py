"""
Phase 3.3 — Destination Prior.

Provides static baseline preference priors per city. When a user has
few behavioral signals, the destination prior fills gaps with city-level
defaults so that ranking does not degrade to a uniform distribution.

Design:
  - Static dict: city_slug -> {dimension: {direction, confidence}}
  - Weight blend factor: 0.15 (prior contributes 15% to blended output)
  - Confidence gate: priors only applied for dimensions where user's own
    signal confidence is < 0.3 (i.e. the user has not expressed a clear
    preference for that dimension)
  - Pure function: no I/O, no side effects

Cities covered (from city_configs.py):
  austin, new-orleans, seattle, asheville, portland, mexico-city, bend

Usage:
  blended = apply_destination_prior(user_signals, "austin")
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIOR_WEIGHT = 0.15         # fraction of final score contributed by prior
CONFIDENCE_GATE = 0.3       # only apply prior where user confidence < this

# ---------------------------------------------------------------------------
# Static city priors
# ---------------------------------------------------------------------------
#
# Each city maps to a dict of dimension -> dict(direction, confidence, weight).
# These are research-grounded defaults reflecting each city's character:
#   austin       — food/music forward, nightlife high, outdoors moderate
#   new-orleans  — food obsessed, nightlife very high, cultural depth high
#   seattle      — outdoors high, food-driven (coffee/tech), moderate pace
#   asheville    — outdoor affinity very high, artsy culture, slow pace
#   portland     — outdoor + food dual high, budget-friendly, alternative
#   mexico-city  — cultural depth very high, food high, adventure moderate
#   bend         — outdoor affinity very high, pace slow, adventure high

CITY_PRIORS: dict[str, dict[str, dict[str, Any]]] = {
    "austin": {
        "food_priority": {
            "direction": "high",
            "confidence": 0.78,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "high",
            "confidence": 0.75,
            "weight": PRIOR_WEIGHT,
        },
        "outdoor_affinity": {
            "direction": "high",
            "confidence": 0.60,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.62,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "neutral",
            "confidence": 0.45,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "high",
            "confidence": 0.65,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "neutral",
            "confidence": 0.48,
            "weight": PRIOR_WEIGHT,
        },
    },
    "new-orleans": {
        "food_priority": {
            "direction": "high",
            "confidence": 0.92,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "high",
            "confidence": 0.88,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.82,
            "weight": PRIOR_WEIGHT,
        },
        "outdoor_affinity": {
            "direction": "low",
            "confidence": 0.55,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "low",
            "confidence": 0.62,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "neutral",
            "confidence": 0.48,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "high",
            "confidence": 0.80,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
    },
    "seattle": {
        "food_priority": {
            "direction": "high",
            "confidence": 0.75,
            "weight": PRIOR_WEIGHT,
        },
        "outdoor_affinity": {
            "direction": "high",
            "confidence": 0.85,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.68,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "neutral",
            "confidence": 0.52,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "low",
            "confidence": 0.55,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "high",
            "confidence": 0.65,
            "weight": PRIOR_WEIGHT,
        },
    },
    "asheville": {
        "outdoor_affinity": {
            "direction": "high",
            "confidence": 0.88,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.75,
            "weight": PRIOR_WEIGHT,
        },
        "food_priority": {
            "direction": "high",
            "confidence": 0.70,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "low",
            "confidence": 0.72,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "neutral",
            "confidence": 0.48,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "neutral",
            "confidence": 0.52,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "high",
            "confidence": 0.70,
            "weight": PRIOR_WEIGHT,
        },
    },
    "portland": {
        "outdoor_affinity": {
            "direction": "high",
            "confidence": 0.82,
            "weight": PRIOR_WEIGHT,
        },
        "food_priority": {
            "direction": "high",
            "confidence": 0.80,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "high",
            "confidence": 0.65,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.70,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "low",
            "confidence": 0.65,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "neutral",
            "confidence": 0.52,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "neutral",
            "confidence": 0.55,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "high",
            "confidence": 0.68,
            "weight": PRIOR_WEIGHT,
        },
    },
    "mexico-city": {
        "cultural_depth": {
            "direction": "high",
            "confidence": 0.92,
            "weight": PRIOR_WEIGHT,
        },
        "food_priority": {
            "direction": "high",
            "confidence": 0.88,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "high",
            "confidence": 0.72,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "high",
            "confidence": 0.65,
            "weight": PRIOR_WEIGHT,
        },
        "outdoor_affinity": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "neutral",
            "confidence": 0.52,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "high",
            "confidence": 0.60,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "high",
            "confidence": 0.72,
            "weight": PRIOR_WEIGHT,
        },
    },
    "bend": {
        "outdoor_affinity": {
            "direction": "high",
            "confidence": 0.95,
            "weight": PRIOR_WEIGHT,
        },
        "adventure_tolerance": {
            "direction": "high",
            "confidence": 0.88,
            "weight": PRIOR_WEIGHT,
        },
        "pace_preference": {
            "direction": "low",
            "confidence": 0.78,
            "weight": PRIOR_WEIGHT,
        },
        "food_priority": {
            "direction": "neutral",
            "confidence": 0.52,
            "weight": PRIOR_WEIGHT,
        },
        "nightlife_interest": {
            "direction": "low",
            "confidence": 0.60,
            "weight": PRIOR_WEIGHT,
        },
        "cultural_depth": {
            "direction": "neutral",
            "confidence": 0.45,
            "weight": PRIOR_WEIGHT,
        },
        "budget_sensitivity": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
        "social_energy": {
            "direction": "neutral",
            "confidence": 0.50,
            "weight": PRIOR_WEIGHT,
        },
    },
}

# ---------------------------------------------------------------------------
# Prior application logic
# ---------------------------------------------------------------------------


def apply_destination_prior(
    user_signals: list[dict],
    city_slug: str,
) -> list[dict]:
    """
    Blend destination priors into user signals for dimensions with low confidence.

    For each dimension in the city's prior:
      - If the user has an existing signal for that dimension with
        confidence >= CONFIDENCE_GATE (0.3), skip — user's data wins.
      - Otherwise, inject the prior signal at the prior's confidence * PRIOR_WEIGHT.

    This is a pure function — the input list is not mutated.

    Args:
        user_signals: List of user preference signal dicts. Expected keys:
            dimension, direction, confidence (float), source (str).
            Any extra keys are passed through unchanged.
        city_slug: One of the 7 supported city slugs. Unknown slugs
            return user_signals unchanged (with a warning log).

    Returns:
        A new list of signal dicts combining user signals and any
        injected city priors for underconfident dimensions.
    """
    city_prior = CITY_PRIORS.get(city_slug)
    if city_prior is None:
        logger.warning(
            "destination_prior: unknown city_slug=%r, returning user_signals unchanged",
            city_slug,
        )
        return list(user_signals)

    # Build a map of dimension -> max user confidence for fast lookup
    user_confidence_by_dim: dict[str, float] = {}
    for sig in user_signals:
        dim = sig.get("dimension", "")
        conf = float(sig.get("confidence", 0.0))
        if dim not in user_confidence_by_dim or conf > user_confidence_by_dim[dim]:
            user_confidence_by_dim[dim] = conf

    # Deep-copy user signals to avoid mutation
    blended: list[dict] = [copy.deepcopy(s) for s in user_signals]

    # Inject priors for weak/missing dimensions
    injected_dims: list[str] = []
    for dimension, prior_spec in city_prior.items():
        user_conf = user_confidence_by_dim.get(dimension, 0.0)
        if user_conf >= CONFIDENCE_GATE:
            # User has a confident signal — skip
            continue

        # Inject prior with reduced confidence (prior_confidence * PRIOR_WEIGHT)
        effective_confidence = round(
            float(prior_spec["confidence"]) * PRIOR_WEIGHT, 4
        )

        blended.append(
            {
                "dimension": dimension,
                "direction": prior_spec["direction"],
                "confidence": effective_confidence,
                "source": "destination_prior",
                "city_slug": city_slug,
                "prior_weight": PRIOR_WEIGHT,
            }
        )
        injected_dims.append(dimension)

    if injected_dims:
        logger.debug(
            "destination_prior: city=%s injected %d prior dimensions: %s",
            city_slug,
            len(injected_dims),
            injected_dims,
        )

    return blended
