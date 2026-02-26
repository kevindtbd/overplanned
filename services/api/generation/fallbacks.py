"""
Triple fallback cascade for itinerary generation.

Tier order:
  1. LLM ranking via claude-sonnet-4-6 (timeout: 5s)
  2. Deterministic ranking by convergenceScore * persona_match_score (LLM timeout)
  3. Postgres fallback query by category + city + priceLevel (Qdrant timeout, 3s)
  4. Cached template itinerary (both services down)

Sets Trip.generationMethod:
  "llm" | "deterministic_fallback" | "postgres_fallback" | "template_fallback"
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic

from services.api.generation.ranker import rank_candidates_with_llm

logger = logging.getLogger(__name__)

# Timeout for the Postgres category fallback query
PG_FALLBACK_TIMEOUT_S = 3

# Minimum nodes to attempt LLM ranking (below this, go straight to deterministic)
MIN_CANDIDATES_FOR_LLM = 3

# Template itinerary used when everything else is down.
# Generic enough to be city-agnostic. Slot types are "flex" so they're replaceable.
_TEMPLATE_ITINERARY: list[dict[str, Any]] = [
    {"templateSlot": True, "slotType": "flex",   "dayNumber": 1, "sortOrder": 1, "label": "Morning exploration"},
    {"templateSlot": True, "slotType": "meal",   "dayNumber": 1, "sortOrder": 2, "label": "Lunch"},
    {"templateSlot": True, "slotType": "anchor", "dayNumber": 1, "sortOrder": 3, "label": "Afternoon highlight"},
    {"templateSlot": True, "slotType": "flex",   "dayNumber": 1, "sortOrder": 4, "label": "Evening activity"},
    {"templateSlot": True, "slotType": "meal",   "dayNumber": 1, "sortOrder": 5, "label": "Dinner"},
]


# ---------------------------------------------------------------------------
# Persona match scoring (used in deterministic fallback)
# ---------------------------------------------------------------------------

def _persona_match_score(node: dict[str, Any], persona_seed: dict[str, Any]) -> float:
    """
    Score a node against persona vibes using tag overlap.
    Returns [0.0, 1.0].
    """
    persona_vibes: set[str] = set(persona_seed.get("vibes", []))
    if not persona_vibes:
        return 0.5  # neutral if no persona data

    node_vibe_slugs: set[str] = {
        v["slug"] for v in (node.get("vibeTags") or [])
        if isinstance(v, dict) and "slug" in v
    }

    if not node_vibe_slugs:
        return 0.2

    overlap = len(persona_vibes & node_vibe_slugs)
    return min(overlap / len(persona_vibes), 1.0)


def _price_penalty(node: dict[str, Any], persona_seed: dict[str, Any]) -> float:
    """
    Return a small penalty [0.0, 0.2] when price level mismatches persona budget.
    """
    budget = persona_seed.get("budget", "mid")
    price_level = node.get("priceLevel")
    if price_level is None:
        return 0.0
    budget_map = {"budget": 1, "mid": 2, "splurge": 3}
    target = budget_map.get(budget, 2)
    distance = abs(price_level - target)
    return min(distance * 0.1, 0.2)


def _deterministic_rank(
    candidates: list[dict[str, Any]],
    persona_seed: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Rank candidates deterministically: convergenceScore * persona_match_score - price_penalty.
    Returns list of {"id", "rank", "slotType", "reasoning"}.
    """
    scored = []
    for node in candidates:
        convergence = node.get("convergenceScore") or 0.0
        persona_match = _persona_match_score(node, persona_seed)
        penalty = _price_penalty(node, persona_seed)
        composite = (convergence * 0.6) + (persona_match * 0.4) - penalty
        scored.append((composite, node))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    for rank_idx, (score, node) in enumerate(scored, start=1):
        category = (node.get("category") or "").lower()
        if category in ("dining", "drinks"):
            slot_type = "meal"
        elif node.get("authorityScore", 0) >= 0.8:
            slot_type = "anchor"
        else:
            slot_type = "flex"

        result.append({
            "id": node["id"],
            "rank": rank_idx,
            "slotType": slot_type,
            "reasoning": f"deterministic: composite_score={score:.3f}",
        })

    return result


# ---------------------------------------------------------------------------
# Postgres category fallback
# ---------------------------------------------------------------------------

async def _pg_fallback(
    db,
    city: str,
    persona_seed: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Query Postgres directly by city + category + priceLevel when Qdrant is down.
    Returns list of raw ActivityNode dicts (subset of fields).
    """
    budget = persona_seed.get("budget", "mid")
    budget_to_price = {"budget": 1, "mid": 2, "splurge": 3}
    target_price = budget_to_price.get(budget, 2)

    # Prefer nodes whose priceLevel is within 1 of target, status=approved
    rows = await asyncio.wait_for(
        db.fetch(
            """
            SELECT
                id, name, slug, category, "priceLevel",
                "convergenceScore", "authorityScore",
                "descriptionShort", "primaryImageUrl"
            FROM activity_nodes
            WHERE city = $1
              AND status = 'approved'
              AND "isCanonical" = true
              AND ("priceLevel" IS NULL OR ABS("priceLevel" - $2) <= 1)
            ORDER BY "convergenceScore" DESC NULLS LAST
            LIMIT $3
            """,
            city.lower(),
            target_price,
            limit,
        ),
        timeout=PG_FALLBACK_TIMEOUT_S,
    )

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public cascade entry point
# ---------------------------------------------------------------------------

async def run_with_fallbacks(
    *,
    candidates: list[dict[str, Any]],
    persona_seed: dict[str, Any],
    city: str,
    anthropic_client: anthropic.AsyncAnthropic,
    db,
    qdrant_available: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, dict[str, Any]]:
    """
    Execute the full fallback cascade.

    Args:
        candidates:        Hydrated ActivityNode dicts from Qdrant/search.
        persona_seed:      Trip personaSeed JSON.
        city:              Trip city (lowercase).
        anthropic_client:  Anthropic async client instance.
        db:                asyncpg connection / pool.
        qdrant_available:  False if Qdrant was already known to be down.

    Returns:
        (ranked_meta, resolved_candidates, generation_method, log_meta)

        ranked_meta:          list of {"id", "rank", "slotType", "reasoning"}
        resolved_candidates:  ActivityNode dicts corresponding to ranked_meta IDs
        generation_method:    "llm" | "deterministic_fallback" | "postgres_fallback" | "template_fallback"
        log_meta:             dict with timing / model info for audit logging
    """
    log_meta: dict[str, Any] = {"promptVersion": None, "model": None, "latencyMs": None}

    # --- Tier 1: LLM ranking ---
    if qdrant_available and len(candidates) >= MIN_CANDIDATES_FOR_LLM:
        try:
            ranked_meta, llm_log = await rank_candidates_with_llm(
                persona_seed=persona_seed,
                candidates=candidates,
                anthropic_client=anthropic_client,
            )
            log_meta.update(llm_log)
            node_map = {n["id"]: n for n in candidates}
            resolved = [node_map[m["id"]] for m in ranked_meta if m["id"] in node_map]
            logger.info("Generation method: llm")
            return ranked_meta, resolved, "llm", log_meta

        except asyncio.TimeoutError:
            logger.warning("LLM ranker timed out after %ds — falling back to deterministic", 5)
        except (anthropic.APIError, anthropic.APIConnectionError, ValueError) as exc:
            logger.warning("LLM ranker failed (%s) — falling back to deterministic", exc)

    # --- Tier 2: Deterministic ranking (LLM timeout / error) ---
    if qdrant_available and candidates:
        ranked_meta = _deterministic_rank(candidates, persona_seed)
        node_map = {n["id"]: n for n in candidates}
        resolved = [node_map[m["id"]] for m in ranked_meta if m["id"] in node_map]
        log_meta["model"] = "deterministic"
        logger.info("Generation method: deterministic_fallback")
        return ranked_meta, resolved, "deterministic_fallback", log_meta

    # --- Tier 3: Postgres-only fallback (Qdrant down) ---
    if db is not None:
        try:
            pg_nodes = await _pg_fallback(db=db, city=city, persona_seed=persona_seed)
            if pg_nodes:
                ranked_meta = _deterministic_rank(pg_nodes, persona_seed)
                node_map = {n["id"]: n for n in pg_nodes}
                resolved = [node_map[m["id"]] for m in ranked_meta if m["id"] in node_map]
                log_meta["model"] = "postgres_fallback"
                logger.info("Generation method: postgres_fallback")
                return ranked_meta, resolved, "postgres_fallback", log_meta
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Postgres fallback failed (%s) — using template", exc)

    # --- Tier 4: Template itinerary (everything down) ---
    logger.warning("All generation tiers failed — returning template itinerary")
    log_meta["model"] = "template"
    return [], [], "template_fallback", log_meta


def get_template_itinerary() -> list[dict[str, Any]]:
    """Return the static template itinerary used as last-resort fallback."""
    return [dict(slot) for slot in _TEMPLATE_ITINERARY]
