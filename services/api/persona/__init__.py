"""
services.api.persona — unified persona read layer.

All persona reads in the system go through effective_persona().
RankingOrchestrator and generation code NEVER read PersonaDimension directly.

Usage:
    from services.api.persona import effective_persona, PersonaSnapshot

    snapshot = await effective_persona(
        user_id="user-123",
        trip_id="trip-456",
        pool=pool,
        redis_client=redis,
        city_slug="austin",
    )
"""

from __future__ import annotations

from services.api.persona.effective import effective_persona, get_persona_for_ranking
from services.api.persona.types import DimensionValue, PersonaSnapshot

__all__ = [
    "effective_persona",
    "get_persona_for_ranking",
    "PersonaSnapshot",
    "DimensionValue",
]
