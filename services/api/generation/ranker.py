"""
LLM ranking logic for itinerary candidate nodes.

Uses claude-sonnet-4-6 to rank ActivityNode candidates against
a persona seed, returning an ordered list with reasoning.

Every call logs: model version, prompt version, latency, token usage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# Prompt version — bump whenever prompt text changes meaningfully
RANKER_PROMPT_VERSION = "ranker-v1.0"
RANKER_MODEL = "claude-sonnet-4-6"
LLM_TIMEOUT_S = 5

_SYSTEM_PROMPT = """You are a travel itinerary curator for Overplanned.
Your job is to rank a set of activity candidates for a solo traveler based on
their behavioral persona. Overplanned is local-first: recommendations come from
Reddit, local forums, and Tabelog-style sources — not TripAdvisor or Yelp.

You must return ONLY a valid JSON object in this exact shape:
{
  "ranked": [
    {
      "id": "<activityNodeId>",
      "rank": 1,
      "slotType": "anchor" | "flex" | "meal",
      "reasoning": "<one sentence why this fits>"
    },
    ...
  ]
}

Rules:
- Include ALL candidate IDs. Do not drop any.
- rank=1 is the best fit.
- slotType assignment: dining/drinks → "meal", culturally significant or time-anchored → "anchor", everything else → "flex".
- Meals should be flagged as slotType="meal" regardless of persona weight.
- Base decisions on convergenceScore, vibeTags alignment with personaVibes, and qualitySignal authority.
- Never invent activities not in the candidate list.
- No markdown, no explanation outside the JSON block."""


def _build_user_prompt(persona_seed: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    """Build the ranking prompt from persona + candidate set."""
    vibe_labels = persona_seed.get("vibes", [])
    pace = persona_seed.get("pace", "moderate")
    budget = persona_seed.get("budget", "mid")

    # Compact candidate representation to stay within token budget
    compact_candidates = []
    for c in candidates:
        vibe_slugs = [v["slug"] for v in (c.get("vibeTags") or [])]
        quality_sources = [q["sourceName"] for q in (c.get("qualitySignals") or [])][:3]
        compact_candidates.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "category": c.get("category", ""),
            "priceLevel": c.get("priceLevel"),
            "convergenceScore": c.get("convergenceScore"),
            "authorityScore": c.get("authorityScore"),
            "vibeTags": vibe_slugs,
            "qualitySources": quality_sources,
            "descriptionShort": (c.get("descriptionShort") or "")[:120],
        })

    return json.dumps({
        "persona": {
            "vibes": vibe_labels,
            "pace": pace,
            "budget": budget,
        },
        "candidates": compact_candidates,
    }, ensure_ascii=False)


async def rank_candidates_with_llm(
    persona_seed: dict[str, Any],
    candidates: list[dict[str, Any]],
    anthropic_client: anthropic.AsyncAnthropic,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Rank activity candidates against a persona using claude-sonnet-4-6.

    Returns:
        (ranked_list, log_meta)
        ranked_list: list of {"id", "rank", "slotType", "reasoning"}, sorted rank asc
        log_meta: {"model", "promptVersion", "latencyMs", "inputTokens", "outputTokens"}

    Raises:
        asyncio.TimeoutError if LLM exceeds LLM_TIMEOUT_S
        anthropic.APIError on Anthropic API errors
    """
    user_prompt = _build_user_prompt(persona_seed, candidates)
    start = time.monotonic()

    response = await asyncio.wait_for(
        anthropic_client.messages.create(
            model=RANKER_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        ),
        timeout=LLM_TIMEOUT_S,
    )

    latency_ms = int((time.monotonic() - start) * 1000)

    raw_text = response.content[0].text.strip()

    # Parse — LLM is instructed to return only JSON
    try:
        parsed = json.loads(raw_text)
        ranked = parsed["ranked"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error(
            "LLM ranker returned unparseable response: %s",
            raw_text[:300],
            exc_info=exc,
        )
        raise ValueError("LLM returned malformed ranking JSON") from exc

    # Sort ascending by rank defensively
    ranked.sort(key=lambda x: x.get("rank", 999))

    log_meta = {
        "model": RANKER_MODEL,
        "promptVersion": RANKER_PROMPT_VERSION,
        "latencyMs": latency_ms,
        "inputTokens": response.usage.input_tokens,
        "outputTokens": response.usage.output_tokens,
    }

    logger.info(
        "LLM ranking complete: %d candidates ranked in %dms (in=%d out=%d)",
        len(ranked),
        latency_ms,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    return ranked, log_meta
