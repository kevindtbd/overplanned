"""
NLP Preference Extraction — Phase 3.2 shared infrastructure.

Two-pass architecture:
  Pass 1: Rule-based pattern matching (fast, zero API cost)
  Pass 2: LLM extraction via claude-haiku-4-5-20251001 (for long-tail patterns)

Pass 2 only fires when Pass 1 finds fewer than 3 signals, so API cost is
incurred only when rules haven't captured enough signal.

This module is intentionally DB-free. It accepts raw text, returns
PreferenceSignal objects. Callers are responsible for persistence.

Shared by:
  - ChatGPT conversation import (Wave D)
  - Onboarding freetext (Phase 3.2)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel, field_validator, model_validator

from services.api.nlp.patterns import (
    DIMENSION_PATTERNS,
    VALID_DIMENSIONS,
    VALID_VALUES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXTRACTOR_MODEL = "claude-haiku-4-5-20251001"
EXTRACTOR_PROMPT_VERSION = "pref-extract-v1.0"

# LLM pass fires only when rules find fewer than this many signals
LLM_TRIGGER_THRESHOLD = 3

# LLM confidence is capped lower than rules — rules are more reliable
LLM_MAX_CONFIDENCE = 0.7

# Hard limit on source_text length (per ImportPreferenceSignal schema)
SOURCE_TEXT_MAX_LEN = 500

LLM_TIMEOUT_S = 10


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PreferenceSignal:
    """
    A single extracted preference signal from natural language text.

    dimension:   persona dimension key (one of 10 valid keys)
    direction:   "positive" | "negative"
    confidence:  0.0-1.0
    source_text: matched snippet from the input, max 500 chars
    source:      "rule_based" | "llm_haiku"
    """
    dimension: str
    direction: str
    confidence: float
    source_text: str
    source: str

    def __post_init__(self) -> None:
        # Truncate source_text to schema limit
        if len(self.source_text) > SOURCE_TEXT_MAX_LEN:
            self.source_text = self.source_text[:SOURCE_TEXT_MAX_LEN]


# ---------------------------------------------------------------------------
# Pydantic model for LLM output validation
# ---------------------------------------------------------------------------

class _LLMSignalItem(BaseModel):
    """Validates a single signal object from the LLM JSON response."""
    dimension: str
    direction: str
    confidence: float
    evidence: str

    @field_validator("dimension")
    @classmethod
    def dimension_must_be_valid(cls, v: str) -> str:
        if v not in VALID_DIMENSIONS:
            raise ValueError(f"Unknown dimension: {v!r}")
        return v

    @field_validator("direction")
    @classmethod
    def direction_must_be_valid(cls, v: str) -> str:
        if v not in ("positive", "negative"):
            raise ValueError(f"Invalid direction: {v!r}")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_must_be_in_range(cls, v: float) -> float:
        return max(0.0, min(LLM_MAX_CONFIDENCE, float(v)))

    @model_validator(mode="after")
    def evidence_truncated(self) -> "_LLMSignalItem":
        if len(self.evidence) > SOURCE_TEXT_MAX_LEN:
            self.evidence = self.evidence[:SOURCE_TEXT_MAX_LEN]
        return self


class _LLMResponse(BaseModel):
    """Top-level wrapper for LLM JSON output."""
    signals: list[_LLMSignalItem]


# ---------------------------------------------------------------------------
# System + user prompts for LLM pass
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a preference extraction system for a travel planning app.
You extract persona preference signals from natural language text written by travelers.

You must return ONLY a valid JSON object in this exact shape:
{
  "signals": [
    {
      "dimension": "<dimension_key>",
      "direction": "positive" | "negative",
      "confidence": <float 0.0-0.7>,
      "evidence": "<exact quoted text or paraphrase, max 200 chars>"
    }
  ]
}

Rules:
- Only use dimension keys from the provided valid list.
- Only extract signals for dimensions NOT already covered by existing signals.
- direction "positive" = the traveler prefers/is this; "negative" = avoids/is not this.
- confidence max is 0.7.
- evidence must reference the actual text — do not invent.
- If no additional signals can be reliably extracted, return {"signals": []}.
- No markdown, no explanation outside the JSON block."""


def _build_llm_user_prompt(
    text: str,
    existing_signals: list[PreferenceSignal],
) -> str:
    """Build the user message for the LLM extraction pass."""
    already_covered = sorted({s.dimension for s in existing_signals})

    valid_dims_list = sorted(VALID_DIMENSIONS)
    remaining_dims = [d for d in valid_dims_list if d not in already_covered]

    parts: list[str] = []

    parts.append("Traveler text:")
    parts.append(f'"""\n{text[:2000]}\n"""')

    if already_covered:
        parts.append(
            f"\nDimensions already extracted (DO NOT re-extract these): "
            + ", ".join(already_covered)
        )

    parts.append(
        "\nDimensions to extract from (only these, only if you find clear evidence):\n"
        + "\n".join(f"- {d}" for d in remaining_dims)
    )

    # Provide the valid values so the LLM understands what "positive" means
    parts.append("\nValid dimension values for context:")
    for dim in remaining_dims:
        vals = ", ".join(sorted(VALID_VALUES.get(dim, set())))
        parts.append(f"  {dim}: {vals}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Pass 1: Rule-based extraction
# ---------------------------------------------------------------------------

def extract_preferences_rules(text: str) -> list[PreferenceSignal]:
    """
    Extract preference signals using regex pattern matching.

    Runs all patterns from DIMENSION_PATTERNS against the input text.
    For each dimension, keeps the single highest-confidence match to
    avoid double-counting. Case-insensitive, word-boundary anchored.

    Args:
        text: raw input text (any length)

    Returns:
        List of PreferenceSignal, one per matched dimension value,
        sorted by confidence descending. Empty list on no match.
    """
    if not text or not text.strip():
        return []

    # best_match[dimension][value] = (confidence, matched_snippet)
    best_match: dict[str, dict[str, tuple[float, str]]] = {}

    for dimension, specs in DIMENSION_PATTERNS.items():
        for spec in specs:
            pattern = spec["pattern"]
            value = spec["value"]
            confidence = spec["confidence"]

            # Skip values outside the closed enum
            valid_vals = VALID_VALUES.get(dimension, frozenset())
            if value not in valid_vals:
                logger.debug(
                    "Pattern value %r not in valid values for %s — skipping",
                    value, dimension,
                )
                continue

            match = pattern.search(text)
            if match is None:
                continue

            # Capture a snippet of surrounding context for source_text
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            snippet = text[start:end].strip()

            if dimension not in best_match:
                best_match[dimension] = {}

            existing = best_match[dimension].get(value)
            if existing is None or confidence > existing[0]:
                best_match[dimension][value] = (confidence, snippet)

    # Flatten: one signal per (dimension, value) — keep highest confidence
    signals: list[PreferenceSignal] = []
    for dimension, value_map in best_match.items():
        for value, (confidence, snippet) in value_map.items():
            signals.append(PreferenceSignal(
                dimension=dimension,
                direction="positive",
                confidence=confidence,
                source_text=snippet,
                source="rule_based",
            ))

    # Deduplicate within dimension: keep highest-confidence value per dimension
    signals = _deduplicate_by_dimension(signals)
    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals


# ---------------------------------------------------------------------------
# Pass 2: LLM extraction
# ---------------------------------------------------------------------------

async def extract_preferences_llm(
    text: str,
    existing_signals: list[PreferenceSignal],
    anthropic_client: anthropic.AsyncAnthropic,
) -> list[PreferenceSignal]:
    """
    Extract preference signals using claude-haiku-4-5-20251001.

    Only extracts dimensions NOT already covered by existing_signals.
    Confidence is capped at LLM_MAX_CONFIDENCE (0.7) — rules are
    more reliable for what they match.

    Args:
        text:              raw input text
        existing_signals:  signals already found by Pass 1
        anthropic_client:  initialized AsyncAnthropic client

    Returns:
        List of new PreferenceSignal objects (does not include existing_signals).
        Empty list on parse failure or API error (logged, never raised).
    """
    if not text or not text.strip():
        return []

    user_prompt = _build_llm_user_prompt(text, existing_signals)
    start = time.monotonic()

    try:
        response = await asyncio.wait_for(
            anthropic_client.messages.create(
                model=EXTRACTOR_MODEL,
                max_tokens=512,
                system=_LLM_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            ),
            timeout=LLM_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "LLM preference extraction timed out after %ds (prompt_version=%s)",
            LLM_TIMEOUT_S, EXTRACTOR_PROMPT_VERSION,
        )
        return []
    except anthropic.APIError as exc:
        logger.error(
            "Anthropic API error during preference extraction: %s",
            exc,
            exc_info=True,
        )
        return []

    latency_ms = int((time.monotonic() - start) * 1000)
    raw_text = response.content[0].text.strip()

    logger.info(
        "LLM preference extraction: %dms, in=%d out=%d (prompt=%s)",
        latency_ms,
        response.usage.input_tokens,
        response.usage.output_tokens,
        EXTRACTOR_PROMPT_VERSION,
    )

    parsed_items = _parse_llm_response(raw_text)
    if not parsed_items:
        return []

    signals: list[PreferenceSignal] = []
    for item in parsed_items:
        signals.append(PreferenceSignal(
            dimension=item.dimension,
            direction=item.direction,
            confidence=item.confidence,
            source_text=item.evidence,
            source="llm_haiku",
        ))

    return signals


def _parse_llm_response(raw_text: str) -> list[_LLMSignalItem]:
    """
    Parse and validate LLM JSON response.

    Tolerates markdown code fences. Returns empty list on any parse
    or validation failure — never raises.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                data = json.loads(block)
                return _validate_llm_data(data)
            except (json.JSONDecodeError, Exception):
                continue

    # Direct JSON parse
    try:
        data = json.loads(text)
        return _validate_llm_data(data)
    except json.JSONDecodeError:
        logger.error(
            "LLM preference extractor returned non-JSON: %s", text[:300]
        )
        return []


def _validate_llm_data(data: Any) -> list[_LLMSignalItem]:
    """Validate parsed JSON dict via Pydantic. Returns empty list on failure."""
    try:
        validated = _LLMResponse.model_validate(data)
        return validated.signals
    except Exception as exc:
        logger.error(
            "LLM preference extractor Pydantic validation failed: %s",
            exc,
            exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

async def extract_preferences(
    text: str,
    anthropic_client: anthropic.AsyncAnthropic | None = None,
) -> list[PreferenceSignal]:
    """
    Extract preference signals from natural language text.

    Two-pass:
      1. Rule-based patterns (always runs, zero cost)
      2. LLM extraction (only if Pass 1 found < LLM_TRIGGER_THRESHOLD signals
         AND an anthropic_client is provided)

    Deduplicates by dimension — when both passes produce a signal for the
    same dimension, the higher-confidence one wins.

    Args:
        text:              raw input text from user
        anthropic_client:  optional AsyncAnthropic client for Pass 2.
                           If None, LLM pass is skipped regardless of signal count.

    Returns:
        Merged list of PreferenceSignal, sorted by confidence descending.
        All returned dimensions are guaranteed to be in VALID_DIMENSIONS.
    """
    if not text or not text.strip():
        return []

    # Pass 1
    rule_signals = extract_preferences_rules(text)
    logger.debug("Rule pass: %d signals from %d chars", len(rule_signals), len(text))

    # Pass 2 — only if rules under-delivered and client is available
    llm_signals: list[PreferenceSignal] = []
    if len(rule_signals) < LLM_TRIGGER_THRESHOLD and anthropic_client is not None:
        logger.debug(
            "Rule pass found %d signals (threshold=%d) — running LLM pass",
            len(rule_signals), LLM_TRIGGER_THRESHOLD,
        )
        llm_signals = await extract_preferences_llm(
            text, rule_signals, anthropic_client
        )
        logger.debug("LLM pass: %d additional signals", len(llm_signals))

    # Merge and deduplicate
    combined = rule_signals + llm_signals
    combined = _deduplicate_by_dimension(combined)
    combined.sort(key=lambda s: s.confidence, reverse=True)
    return combined


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deduplicate_by_dimension(signals: list[PreferenceSignal]) -> list[PreferenceSignal]:
    """
    Keep only the highest-confidence signal per dimension.

    When multiple signals exist for the same dimension (e.g., rule + LLM both
    matched energy_level), only the one with the highest confidence survives.
    Tie-breaks favor rule_based over llm_haiku.
    """
    best: dict[str, PreferenceSignal] = {}
    for sig in signals:
        existing = best.get(sig.dimension)
        if existing is None:
            best[sig.dimension] = sig
            continue

        if sig.confidence > existing.confidence:
            best[sig.dimension] = sig
        elif sig.confidence == existing.confidence:
            # Prefer rule_based on tie
            if sig.source == "rule_based" and existing.source != "rule_based":
                best[sig.dimension] = sig

    return list(best.values())
