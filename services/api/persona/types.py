"""
PersonaSnapshot and DimensionValue dataclasses.

These are the canonical types for all persona reads in the system.
RankingOrchestrator and generation code consume PersonaSnapshot exclusively —
they never read PersonaDimension rows directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DimensionValue:
    """A single resolved persona dimension."""

    value: str
    """Categorical label, e.g. 'food_driven', 'slow_traveler'."""

    confidence: float
    """How certain we are about this value (0.0 - 1.0)."""

    source: str
    """Provenance: 'onboarding', 'behavioral_ema', 'destination_prior', 'cf_blend', 'trip_cache'."""


@dataclass
class PersonaSnapshot:
    """
    Fully resolved persona for a user/trip pair.

    Built by effective_persona() and consumed by RankingOrchestrator
    and all downstream generation code.
    """

    user_id: str
    """The user this snapshot belongs to."""

    trip_id: str | None
    """Trip context, or None for trip-agnostic reads."""

    dimensions: dict[str, DimensionValue]
    """dimension_name -> DimensionValue. Keyed by e.g. 'food_priority', 'pace_preference'."""

    negative_tag_affinities: dict[str, float]
    """tag_slug -> negative weight in range [-1.0, 0.0]. Used for Qdrant exclusion weighting."""

    source_breakdown: dict[str, str]
    """dimension -> source name (which layer provided this dimension's value)."""

    confidence: float
    """Overall persona confidence: mean of all dimension confidences (0.0 - 1.0)."""

    cache_hit: bool
    """True if this snapshot was served from TripPersonaCache (Redis), not DB."""

    resolved_at: str
    """ISO 8601 UTC timestamp of when this snapshot was resolved."""
