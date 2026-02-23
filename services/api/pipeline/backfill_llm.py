"""
LLM helpers for the backfill ingestion pipeline.

Three functions, two models:
  - classify_submission()  — Haiku: tier classification (tier_3 vs tier_4)
  - extract_venues()       — Sonnet with tool use: structured venue extraction
  - validate_venues()      — Haiku: plausibility validation per venue

All calls:
  - Use anthropic.AsyncAnthropic (reads ANTHROPIC_API_KEY from env)
  - Log model version, latency, and cost estimate at INFO level
  - Raise on unrecoverable errors; caller decides retry/abort policy

Prompt injection defense:
  - System/user separation enforced everywhere
  - Raw user text always wrapped in <user_diary>...</user_diary> delimiters
  - Tool use (not raw JSON output) enforced for extraction to lock schema
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# Haiku pricing (per 1M tokens, Feb 2026)
HAIKU_INPUT_CPM = 0.80
HAIKU_OUTPUT_CPM = 4.00

# Sonnet pricing (per 1M tokens, Feb 2026)
SONNET_INPUT_CPM = 3.00
SONNET_OUTPUT_CPM = 15.00

# Prompt version tags — bump when prompts change so model registry stays clean
CLASSIFY_PROMPT_VERSION = "backfill-classify-v1"
EXTRACT_PROMPT_VERSION = "backfill-extract-v1"
VALIDATE_PROMPT_VERSION = "backfill-validate-v1"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExtractedVenue:
    """
    A single venue extracted from user diary text.

    All fields except `name` are nullable — Sonnet is instructed to
    prefer null over guessing.
    """
    name: str
    category: Optional[str]       # maps to ActivityCategory values
    date_or_range: Optional[str]  # free-form string, e.g. "Day 2" or "March 3"
    city: Optional[str]
    sentiment: Optional[str]      # "positive" | "neutral" | "negative"


# ---------------------------------------------------------------------------
# Cost logging helper
# ---------------------------------------------------------------------------

def _log_llm_call(
    model: str,
    prompt_version: str,
    latency_s: float,
    input_tokens: int,
    output_tokens: int,
    input_cpm: float,
    output_cpm: float,
    context: str = "",
) -> None:
    cost_usd = (
        (input_tokens / 1_000_000) * input_cpm
        + (output_tokens / 1_000_000) * output_cpm
    )
    logger.info(
        "llm_call model=%s prompt_version=%s latency_s=%.3f "
        "input_tokens=%d output_tokens=%d cost_usd=%.6f context=%s",
        model,
        prompt_version,
        latency_s,
        input_tokens,
        output_tokens,
        cost_usd,
        context,
    )


# ---------------------------------------------------------------------------
# Stage 1: Source classification
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """\
You are a travel diary classifier for a trip intelligence system.

Your job: determine whether user-submitted text contains annotations, \
ratings, or sentiment (tier_3) versus bare factual text with no evaluative \
content (tier_4).

Criteria for tier_3 (annotated):
- Explicit ratings (stars, scores, numbered reviews)
- Opinion words: "loved", "hated", "amazing", "disappointing", "overrated"
- Comparative statements: "better than", "not worth it"
- Emotional reactions: "mind-blowing", "underwhelming"
- Recommendations: "must-visit", "skip it", "highly recommend"

Criteria for tier_4 (bare):
- Itinerary-style lists with only names and dates
- Pure factual logs: "went to X, then Y"
- No evaluative language whatsoever

Respond with exactly one word: tier_3 or tier_4"""

_CLASSIFY_USER_TEMPLATE = """\
Classify the following travel diary entry:

<user_diary>
{text}
</user_diary>"""


async def classify_submission(
    client: anthropic.AsyncAnthropic,
    text: str,
) -> str:
    """
    Classify submission as 'tier_3' or 'tier_4' using Haiku.

    Returns the enum value string matching ConfidenceTier in the schema.
    Defaults to 'tier_4' if the model response is unparseable.
    """
    user_msg = _CLASSIFY_USER_TEMPLATE.format(text=text[:8000])  # cap context

    t0 = time.monotonic()
    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=16,  # one word answer
        system=_CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    latency = time.monotonic() - t0

    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens

    _log_llm_call(
        model=HAIKU_MODEL,
        prompt_version=CLASSIFY_PROMPT_VERSION,
        latency_s=latency,
        input_tokens=input_tok,
        output_tokens=output_tok,
        input_cpm=HAIKU_INPUT_CPM,
        output_cpm=HAIKU_OUTPUT_CPM,
        context="classify_submission",
    )

    raw = ""
    for block in response.content:
        if block.type == "text":
            raw += block.text

    tier = raw.strip().lower()
    if tier in ("tier_3", "tier_4"):
        return tier

    logger.warning(
        "Unexpected classify response %r — defaulting to tier_4", raw[:40]
    )
    return "tier_4"


# ---------------------------------------------------------------------------
# Stage 2: Venue extraction (Sonnet + tool use)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
You are a venue extraction engine for a travel intelligence system.

Extract venue visits from the user's travel diary. Use the extract_venues \
tool to return structured data.

Rules:
- Extract only venues you have HIGH confidence about (8 high-confidence > 15 guesses)
- Prefer null over guessing for any field you are not sure of
- name: required — the venue name as written or a clean version of it
- category: one of: dining, drinks, culture, outdoors, active, entertainment, \
  shopping, experience, nightlife, group_activity, wellness — or null
- date_or_range: any temporal reference (day number, date, "Day 2", "March 3-4") or null
- city: explicit city mentioned near this venue, or null
- sentiment: "positive", "neutral", or "negative" based on clear evaluative \
  language — null if no sentiment expressed
- Do NOT invent venues not present in the text
- Do NOT include transit hubs (airports, train stations) as venues unless \
  the person is explicitly reviewing them as a destination
- Ignore purely logistical mentions (hotels named only as sleeping location)"""

_EXTRACT_USER_TEMPLATE = """\
Extract venue visits from this travel diary.
City hint (may be null): {city_hint}

<user_diary>
{text}
</user_diary>"""

_EXTRACT_TOOL = {
    "name": "extract_venues",
    "description": (
        "Return all venue visits extracted from the travel diary. "
        "Each item represents one distinct venue visit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "venues": {
                "type": "array",
                "description": "List of extracted venues",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Venue name as it appears or a clean version",
                        },
                        "category": {
                            "type": ["string", "null"],
                            "enum": [
                                "dining", "drinks", "culture", "outdoors", "active",
                                "entertainment", "shopping", "experience", "nightlife",
                                "group_activity", "wellness", None,
                            ],
                            "description": "Activity category, or null if uncertain",
                        },
                        "date_or_range": {
                            "type": ["string", "null"],
                            "description": "Temporal reference for this visit, or null",
                        },
                        "city": {
                            "type": ["string", "null"],
                            "description": "City of this venue if explicit, or null",
                        },
                        "sentiment": {
                            "type": ["string", "null"],
                            "enum": ["positive", "neutral", "negative", None],
                            "description": "Expressed sentiment, or null if absent",
                        },
                    },
                    "required": ["name"],
                },
            }
        },
        "required": ["venues"],
    },
}


async def extract_venues(
    client: anthropic.AsyncAnthropic,
    text: str,
    city_hint: Optional[str],
) -> list[ExtractedVenue]:
    """
    Extract venues from free-form diary text using Sonnet with tool use.

    Returns a list of ExtractedVenue dataclasses. Empty list if extraction
    fails or the model finds no extractable venues.
    """
    city_str = city_hint if city_hint else "not provided"
    user_msg = _EXTRACT_USER_TEMPLATE.format(
        city_hint=city_str,
        text=text[:9500],  # leave headroom for system + tool schema tokens
    )

    t0 = time.monotonic()
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=4096,
        system=_EXTRACT_SYSTEM,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "any"},  # force tool use — no prose fallback
        messages=[{"role": "user", "content": user_msg}],
    )
    latency = time.monotonic() - t0

    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens

    _log_llm_call(
        model=SONNET_MODEL,
        prompt_version=EXTRACT_PROMPT_VERSION,
        latency_s=latency,
        input_tokens=input_tok,
        output_tokens=output_tok,
        input_cpm=SONNET_INPUT_CPM,
        output_cpm=SONNET_OUTPUT_CPM,
        context="extract_venues",
    )

    # Pull tool use block
    tool_input: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_venues":
            tool_input = block.input
            break

    if not tool_input:
        logger.warning("extract_venues: no tool_use block in response")
        return []

    raw_venues = tool_input.get("venues", [])
    if not isinstance(raw_venues, list):
        logger.warning("extract_venues: 'venues' field is not a list")
        return []

    results: list[ExtractedVenue] = []
    for item in raw_venues:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip()
        if not name:
            continue
        results.append(ExtractedVenue(
            name=name,
            category=item.get("category"),
            date_or_range=item.get("date_or_range"),
            city=item.get("city"),
            sentiment=item.get("sentiment"),
        ))

    logger.info("extract_venues: extracted %d venues", len(results))
    return results


# ---------------------------------------------------------------------------
# Stage 2.5: LLM validation
# ---------------------------------------------------------------------------

_VALIDATE_SYSTEM = """\
You are a plausibility validator for a travel data pipeline.

You receive a list of venue names + metadata extracted from a user travel \
diary. For each venue, decide if it is plausible as a real place given \
the provided context.

Validation checks (any failure = reject):
1. Plausible real place name — not a generic phrase ("some restaurant", \
   "a nice cafe"), not a non-venue noun, not obviously invented
2. Geographic coherence — if a city is provided, the venue could plausibly \
   exist in that city (e.g. reject a sushi spot attributed to a landlocked \
   city with no Japanese population)
3. Date consistency — if dates are provided, they are internally consistent \
   (no visiting Day 1 and Day 99 in a 3-day trip)
4. Category reasonableness — the category matches what the name implies \
   (a museum labeled as "dining" = reject)

Important: you are checking PLAUSIBILITY, not existence in any database. \
A real-sounding local spot that you've never heard of should PASS.

Use the validate_venues tool. For each venue, return its name and whether \
it passes (keep = true) or fails (keep = false) with a brief reason if \
rejected."""

_VALIDATE_USER_TEMPLATE = """\
Validate the plausibility of these extracted venues.
Trip city context: {city}

Venues to validate:
{venues_json}"""

_VALIDATE_TOOL = {
    "name": "validate_venues",
    "description": "Return validation results for each venue",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "keep": {"type": "boolean"},
                        "reason": {
                            "type": ["string", "null"],
                            "description": "Rejection reason if keep=false, else null",
                        },
                    },
                    "required": ["name", "keep"],
                },
            }
        },
        "required": ["results"],
    },
}


async def validate_venues(
    client: anthropic.AsyncAnthropic,
    venues: list[ExtractedVenue],
    city: str,
) -> list[Optional[ExtractedVenue]]:
    """
    Validate extracted venues for plausibility using Haiku.

    Returns a list of the same length as input. Venues that fail
    validation are replaced with None. Venues that pass are returned
    as-is. If the LLM call fails entirely, all venues pass (fail open
    to avoid losing data — anomaly checks downstream will catch bad ones).
    """
    if not venues:
        return []

    venues_payload = [
        {
            "name": v.name,
            "category": v.category,
            "date_or_range": v.date_or_range,
            "city": v.city or city,
        }
        for v in venues
    ]

    user_msg = _VALIDATE_USER_TEMPLATE.format(
        city=city,
        venues_json=json.dumps(venues_payload, ensure_ascii=False, indent=2),
    )

    t0 = time.monotonic()
    try:
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2048,
            system=_VALIDATE_SYSTEM,
            tools=[_VALIDATE_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as exc:
        logger.error("validate_venues LLM call failed: %s — failing open", exc)
        return list(venues)  # pass all through on error

    latency = time.monotonic() - t0

    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens

    _log_llm_call(
        model=HAIKU_MODEL,
        prompt_version=VALIDATE_PROMPT_VERSION,
        latency_s=latency,
        input_tokens=input_tok,
        output_tokens=output_tok,
        input_cpm=HAIKU_INPUT_CPM,
        output_cpm=HAIKU_OUTPUT_CPM,
        context="validate_venues",
    )

    # Parse tool response
    tool_input: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "validate_venues":
            tool_input = block.input
            break

    if not tool_input:
        logger.warning("validate_venues: no tool_use block — failing open")
        return list(venues)

    raw_results = tool_input.get("results", [])
    # Build lookup: name -> keep
    keep_map: dict[str, bool] = {}
    reason_map: dict[str, str] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        keep_map[name] = bool(item.get("keep", True))
        if not item.get("keep") and item.get("reason"):
            reason_map[name] = item["reason"]

    output: list[Optional[ExtractedVenue]] = []
    for venue in venues:
        # Default to keep=True if the validator didn't mention this venue
        if keep_map.get(venue.name, True):
            output.append(venue)
        else:
            reason = reason_map.get(venue.name, "failed plausibility check")
            logger.info(
                "validate_venues: rejected %r — %s", venue.name, reason
            )
            output.append(None)

    kept = sum(1 for v in output if v is not None)
    logger.info(
        "validate_venues: %d/%d venues passed", kept, len(venues)
    )
    return output
