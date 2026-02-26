"""
Prompt parser — converts natural language mid-trip requests into structured PivotTrigger JSON.

Security model:
- User text is sandwiched between [USER_DATA_START]/[USER_DATA_END] delimiters.
- NO ActivityNode data, user persona, or any world knowledge enters the prompt context.
  The LLM sees ONLY the user's raw text and the output schema.
- All inputs + Haiku responses are logged to security audit (RawEvent: prompt_bar.parse_attempt).
- Suspicious patterns (prompt delimiters, SQL tokens, role escalation) are rejected pre-LLM
  and logged to prompt_bar.injection_flagged for admin review.

Parsing pipeline:
1. Sanitise + length-cap input (200 chars hard cap)
2. Injection screen (keyword pattern list)
3. Call claude-haiku-4-5-20251001 with 1.5s timeout
4. On timeout / parse failure → keyword fallback
5. Return ParsedIntent

Classification maps to PivotTrigger types:
  weather_change | venue_closure | time_overrun | mood_shift | custom
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_INPUT_LENGTH = 200
HAIKU_TIMEOUT_SECONDS = 1.5
MAX_PIVOT_DEPTH = 1

# PivotTrigger classification values
VALID_CLASSIFICATIONS = {
    "weather_change",
    "venue_closure",
    "time_overrun",
    "mood_shift",
    "custom",
}

# Injection detection patterns — pre-LLM gate
_INJECTION_PATTERNS = [
    re.compile(r"\[USER_DATA_(START|END)\]", re.IGNORECASE),
    re.compile(r"(system\s*prompt|ignore\s+previous|disregard\s+instructions)", re.IGNORECASE),
    re.compile(r"(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+", re.IGNORECASE),
    re.compile(r"<\s*(script|iframe|object|embed)", re.IGNORECASE),
    re.compile(r"(persona|role\s*=|assistant\s*:)", re.IGNORECASE),
    re.compile(r"\\x[0-9a-fA-F]{2}"),  # hex escapes
    re.compile(r"\{.*\"role\"\s*:.*\}", re.DOTALL),  # JSON role injection
]

# Keyword-based fallback classification
_KEYWORD_MAP: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\b(rain|raining|storm|wet|flood|thunder|snow)\b", re.IGNORECASE), "weather_change", 0.75),
    (re.compile(r"\b(closed|closure|shut|not open|unavailable|gone)\b", re.IGNORECASE), "venue_closure", 0.65),
    (re.compile(r"\b(late|running over|overtime|overrun|too long|behind)\b", re.IGNORECASE), "time_overrun", 0.65),
    (re.compile(r"\b(tired|exhausted|bored|not feeling|skip|different|change)\b", re.IGNORECASE), "mood_shift", 0.60),
]


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

class ParsedIntent:
    """Structured output from prompt parsing."""

    __slots__ = ("classification", "confidence", "entities", "method", "raw_text")

    def __init__(
        self,
        classification: str,
        confidence: float,
        entities: dict[str, Any],
        method: str,  # "haiku" | "keyword" | "default"
        raw_text: str,
    ) -> None:
        self.classification = classification
        self.confidence = confidence
        self.entities = entities
        self.method = method
        self.raw_text = raw_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "entities": self.entities,
            "method": self.method,
        }


class InjectionRejection(Exception):
    """Raised when input fails the injection screen."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

class PromptParser:
    """
    Stateless parser — instantiate once per request (no shared state).

    Args:
        anthropic_client: anthropic.AsyncAnthropic instance.
        db: Async database pool for audit logging.
    """

    def __init__(self, anthropic_client, db) -> None:
        self._client = anthropic_client
        self._db = db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def parse(
        self,
        raw_text: str,
        user_id: str,
        trip_id: str,
        session_id: str | None = None,
    ) -> ParsedIntent:
        """
        Parse user text into structured intent. Never raises — falls back to
        'custom'/'default' on any error. Logs all attempts.

        Security guarantees:
        - Input truncated to MAX_INPUT_LENGTH before any processing.
        - Injection patterns screened before Haiku call.
        - Haiku system prompt contains ONLY schema definition, no world data.
        - User text delimited by [USER_DATA_START]/[USER_DATA_END].
        """
        truncated = raw_text[:MAX_INPUT_LENGTH]

        # Injection screen
        try:
            self._screen_for_injection(truncated)
        except InjectionRejection as exc:
            await self._log_injection_flag(
                user_id=user_id,
                trip_id=trip_id,
                session_id=session_id,
                raw_text=truncated,
                reason=exc.reason,
            )
            # Return a safe default — do NOT surface detection details to client
            return ParsedIntent(
                classification="custom",
                confidence=0.0,
                entities={"flagged": True},
                method="rejected",
                raw_text=truncated,
            )

        # Attempt Haiku parse
        result = await self._haiku_parse(truncated)
        if result is None:
            # Haiku timed out or returned unparseable output → keyword fallback
            result = self._keyword_fallback(truncated)

        # Audit log (always, even on success)
        await self._log_parse_attempt(
            user_id=user_id,
            trip_id=trip_id,
            session_id=session_id,
            raw_text=truncated,
            result=result,
        )

        return result

    # ------------------------------------------------------------------
    # Injection screen
    # ------------------------------------------------------------------

    def _screen_for_injection(self, text: str) -> None:
        """Raise InjectionRejection if any suspicious pattern matches."""
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                raise InjectionRejection(
                    f"Matched pattern: {pattern.pattern!r} at position {match.start()}"
                )

    # ------------------------------------------------------------------
    # Haiku call
    # ------------------------------------------------------------------

    async def _haiku_parse(self, text: str) -> ParsedIntent | None:
        """
        Call claude-haiku-4-5-20251001 with a 1.5s timeout.

        System prompt: schema definition ONLY — no activity data, no persona.
        User message: delimited raw text.

        Returns ParsedIntent on success, None on timeout/parse failure.
        """
        system_prompt = (
            "You are a JSON classifier. Classify the user request into one of these "
            "categories: weather_change, venue_closure, time_overrun, mood_shift, custom.\n\n"
            "Respond with ONLY valid JSON in this exact shape:\n"
            '{"classification": "<category>", "confidence": <0.0-1.0>, '
            '"entities": {"location": null, "time": null, "activity_type": null}}\n\n'
            "Rules:\n"
            "- classification must be one of the five allowed values\n"
            "- confidence must be a float between 0.0 and 1.0\n"
            "- entities may be null or strings extracted from the user text\n"
            "- Do NOT include any other fields or explanation"
        )

        user_message = (
            f"[USER_DATA_START]\n{text}\n[USER_DATA_END]"
        )

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=HAIKU_MODEL,
                    max_tokens=128,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                ),
                timeout=HAIKU_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Haiku prompt parse timed out after %.1fs", HAIKU_TIMEOUT_SECONDS)
            return None
        except Exception as exc:
            logger.warning("Haiku prompt parse failed: %s", exc)
            return None

        # Extract text content
        try:
            content_block = response.content[0]
            raw_json = content_block.text.strip()
        except (IndexError, AttributeError):
            logger.warning("Haiku returned no content blocks")
            return None

        return self._parse_haiku_json(raw_json, text)

    def _parse_haiku_json(self, raw_json: str, original_text: str) -> ParsedIntent | None:
        """Parse and validate Haiku's JSON response. Returns None on any error."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("Haiku returned non-JSON: %r", raw_json[:100])
            return None

        classification = data.get("classification", "")
        if classification not in VALID_CLASSIFICATIONS:
            logger.warning("Haiku returned unknown classification: %r", classification)
            return None

        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}

        return ParsedIntent(
            classification=classification,
            confidence=confidence,
            entities=entities,
            method="haiku",
            raw_text=original_text,
        )

    # ------------------------------------------------------------------
    # Keyword fallback
    # ------------------------------------------------------------------

    def _keyword_fallback(self, text: str) -> ParsedIntent:
        """Simple regex-based fallback when Haiku is unavailable."""
        for pattern, classification, confidence in _KEYWORD_MAP:
            if pattern.search(text):
                return ParsedIntent(
                    classification=classification,
                    confidence=confidence,
                    entities={},
                    method="keyword",
                    raw_text=text,
                )

        return ParsedIntent(
            classification="custom",
            confidence=0.3,
            entities={},
            method="default",
            raw_text=text,
        )

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _log_parse_attempt(
        self,
        user_id: str,
        trip_id: str,
        session_id: str | None,
        raw_text: str,
        result: ParsedIntent,
    ) -> None:
        """Log every parse attempt to RawEvent for security audit."""
        try:
            now = datetime.now(timezone.utc)
            await self._db.execute(
                """
                INSERT INTO raw_events (
                    id, "userId", "sessionId", "tripId",
                    "clientEventId", "eventType", "intentClass",
                    surface, payload, "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                str(uuid.uuid4()),
                user_id,
                session_id or str(uuid.uuid4()),
                trip_id,
                f"prompt-{uuid.uuid4().hex[:12]}",
                "prompt_bar.parse_attempt",
                "explicit",
                "prompt_bar",
                json.dumps({
                    "inputLength": len(raw_text),
                    "classification": result.classification,
                    "confidence": result.confidence,
                    "method": result.method,
                    # Do NOT log raw_text in audit — only metadata
                }),
                now,
            )
        except Exception:
            logger.warning("Failed to write parse_attempt audit log", exc_info=True)

    async def _log_injection_flag(
        self,
        user_id: str,
        trip_id: str,
        session_id: str | None,
        raw_text: str,
        reason: str,
    ) -> None:
        """Log injection flag to admin review queue."""
        try:
            now = datetime.now(timezone.utc)
            await self._db.execute(
                """
                INSERT INTO raw_events (
                    id, "userId", "sessionId", "tripId",
                    "clientEventId", "eventType", "intentClass",
                    surface, payload, "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                str(uuid.uuid4()),
                user_id,
                session_id or str(uuid.uuid4()),
                trip_id,
                f"prompt-flag-{uuid.uuid4().hex[:12]}",
                "prompt_bar.injection_flagged",
                "explicit",
                "prompt_bar",
                json.dumps({
                    "inputText": raw_text,
                    "detectionReason": reason,
                    "confidenceScore": 1.0,
                    "reviewStatus": "pending",
                }),
                now,
            )
        except Exception:
            logger.warning("Failed to write injection flag audit log", exc_info=True)
