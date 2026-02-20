"""
Itinerary generation engine — Solo trip pipeline.

Flow:
  1. Build persona-weighted query string from personaSeed
  2. Search Qdrant via ActivitySearchService (persona-weighted vector)
  3. Run fallback cascade: LLM ranking -> deterministic -> PG -> template
  4. Assign time slots: anchors first, meals at windows, flex fills gaps
  5. Write ItinerarySlot rows linked to ActivityNodes
  6. Log full candidate set to RawEvent
  7. Register prompt version in ModelRegistry
  8. Return generation summary

Every LLM call logs: model version, prompt version, latency, estimated cost.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic

from services.api.generation.fallbacks import get_template_itinerary, run_with_fallbacks
from services.api.generation.slot_assigner import SlotAssignment, assign_slots
from services.api.generation.ranker import RANKER_MODEL, RANKER_PROMPT_VERSION
from services.api.search.service import ActivitySearchService

logger = logging.getLogger(__name__)

# Approx cost per token for claude-sonnet-4-6 (USD) — used for cost estimate logging
# Input: $3 / 1M tokens, Output: $15 / 1M tokens
_COST_PER_INPUT_TOKEN = 3e-6
_COST_PER_OUTPUT_TOKEN = 15e-6

# How many candidates to pull from Qdrant before ranking
CANDIDATE_POOL_SIZE = 30

# Persona query template — interpolated from personaSeed fields
def _build_persona_query(persona_seed: dict[str, Any], city: str) -> str:
    """
    Convert a persona seed dict into a natural-language search query.
    The embedding of this query is used for Qdrant vector search.
    """
    vibes = persona_seed.get("vibes", [])
    pace = persona_seed.get("pace", "moderate")
    budget = persona_seed.get("budget", "mid")

    vibe_str = ", ".join(vibes) if vibes else "interesting local spots"
    pace_desc = {
        "slow": "relaxed and low-key",
        "moderate": "well-paced",
        "fast": "packed and energetic",
    }.get(pace, "well-paced")
    budget_desc = {
        "budget": "affordable and local",
        "mid": "mid-range quality",
        "splurge": "premium and special",
    }.get(budget, "mid-range quality")

    return (
        f"Solo traveler in {city} looking for {vibe_str} experiences. "
        f"{pace_desc.capitalize()} day, {budget_desc} options. "
        f"Local recommendations preferred, off the tourist track."
    )


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class GenerationEngine:
    """
    Orchestrates the full solo itinerary generation pipeline.

    Injected dependencies make this fully testable without touching real services.
    """

    def __init__(
        self,
        search_service: ActivitySearchService,
        anthropic_client: anthropic.AsyncAnthropic,
        db,  # asyncpg pool/connection
    ) -> None:
        self._search = search_service
        self._anthropic = anthropic_client
        self._db = db

    async def generate(
        self,
        trip_id: str,
        user_id: str,
        city: str,
        persona_seed: dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run the full generation pipeline for a solo trip.

        Returns a summary dict:
        {
            "tripId": str,
            "generationMethod": str,
            "slotsCreated": int,
            "candidatesConsidered": int,
            "logMeta": dict,
            "warning": str | None,
        }
        """
        pipeline_start = time.monotonic()
        session_id = session_id or str(uuid.uuid4())
        warning: str | None = None

        num_days = max(1, (end_date.date() - start_date.date()).days + 1)

        # ------------------------------------------------------------------
        # Step 1: Qdrant vector search with persona-weighted query
        # ------------------------------------------------------------------
        query = _build_persona_query(persona_seed, city)
        logger.info("Generation started: trip=%s city=%s days=%d", trip_id, city, num_days)

        search_result = await self._search.search(
            query=query,
            city=city,
            limit=CANDIDATE_POOL_SIZE,
        )

        candidates: list[dict[str, Any]] = search_result.get("results", [])
        qdrant_available = True

        if search_result.get("warning"):
            # Qdrant failed — search returned empty with a warning
            if not candidates:
                qdrant_available = False
                warning = search_result["warning"]
                logger.warning("Qdrant unavailable: %s", warning)

        logger.info(
            "Candidate pool: %d nodes from Qdrant (qdrant_available=%s)",
            len(candidates),
            qdrant_available,
        )

        # ------------------------------------------------------------------
        # Step 2: Fallback cascade — LLM rank -> deterministic -> PG -> template
        # ------------------------------------------------------------------
        ranked_meta, resolved_candidates, generation_method, log_meta = await run_with_fallbacks(
            candidates=candidates,
            persona_seed=persona_seed,
            city=city,
            anthropic_client=self._anthropic,
            db=self._db,
            qdrant_available=qdrant_available,
        )

        # ------------------------------------------------------------------
        # Step 3: Slot assignment
        # ------------------------------------------------------------------
        slots: list[SlotAssignment] = []

        if generation_method == "template_fallback":
            # Template path — no real ActivityNodes to assign
            logger.warning("Using template itinerary for trip=%s", trip_id)
        else:
            slots = assign_slots(
                ranked_nodes=resolved_candidates,
                ranked_meta=ranked_meta,
                trip_start_date=start_date,
                num_days=num_days,
            )

        # ------------------------------------------------------------------
        # Step 4: Persist ItinerarySlot rows
        # ------------------------------------------------------------------
        slots_created = 0
        if slots:
            slots_created = await self._write_slots(trip_id, slots)

        # ------------------------------------------------------------------
        # Step 5: Update Trip.generationMethod (stored in personaSeed JSON)
        # ------------------------------------------------------------------
        await self._update_trip_generation_method(trip_id, generation_method)

        # ------------------------------------------------------------------
        # Step 6: Log candidate pool to RawEvent
        # ------------------------------------------------------------------
        await self._log_candidate_pool(
            user_id=user_id,
            session_id=session_id,
            trip_id=trip_id,
            candidates=candidates,
            ranked_meta=ranked_meta,
            generation_method=generation_method,
            log_meta=log_meta,
        )

        # ------------------------------------------------------------------
        # Step 7: Register prompt version in ModelRegistry
        # ------------------------------------------------------------------
        if generation_method == "llm":
            await self._register_prompt_version(log_meta)

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        total_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.info(
            "Generation complete: trip=%s method=%s slots=%d candidates=%d latency=%dms",
            trip_id,
            generation_method,
            slots_created,
            len(candidates),
            total_ms,
        )

        return {
            "tripId": trip_id,
            "generationMethod": generation_method,
            "slotsCreated": slots_created,
            "candidatesConsidered": len(candidates),
            "logMeta": {
                **log_meta,
                "pipelineLatencyMs": total_ms,
                "costEstimateUsd": _estimate_cost(log_meta),
            },
            "warning": warning,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_slots(
        self,
        trip_id: str,
        slots: list[SlotAssignment],
    ) -> int:
        """Bulk-insert ItinerarySlot rows. Returns count inserted."""
        now = datetime.now(timezone.utc)
        inserted = 0

        async with self._db.transaction():
            for slot in slots:
                slot_id = str(uuid.uuid4())
                await self._db.execute(
                    """
                    INSERT INTO "ItinerarySlot" (
                        id, "tripId", "activityNodeId",
                        "dayNumber", "sortOrder",
                        "slotType", status,
                        "startTime", "endTime", "durationMinutes",
                        "isLocked", "wasSwapped",
                        "createdAt", "updatedAt"
                    ) VALUES (
                        $1, $2, $3,
                        $4, $5,
                        $6, 'proposed',
                        $7, $8, $9,
                        false, false,
                        $10, $10
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    slot_id,
                    trip_id,
                    slot.activity_node_id,
                    slot.day_number,
                    slot.sort_order,
                    slot.slot_type,
                    slot.start_time,
                    slot.end_time,
                    slot.duration_minutes,
                    now,
                )
                inserted += 1

        return inserted

    async def _update_trip_generation_method(
        self,
        trip_id: str,
        generation_method: str,
    ) -> None:
        """
        Persist generationMethod onto the Trip row.
        Stored in personaSeed JSON under key "generationMethod".
        """
        try:
            await self._db.execute(
                """
                UPDATE "Trip"
                SET "personaSeed" = COALESCE("personaSeed", '{}'::jsonb)
                    || jsonb_build_object('generationMethod', $1::text),
                    "updatedAt" = NOW()
                WHERE id = $2
                """,
                generation_method,
                trip_id,
            )
        except Exception:
            logger.exception("Failed to update Trip.generationMethod for trip=%s", trip_id)

    async def _log_candidate_pool(
        self,
        user_id: str,
        session_id: str,
        trip_id: str,
        candidates: list[dict[str, Any]],
        ranked_meta: list[dict[str, Any]],
        generation_method: str,
        log_meta: dict[str, Any],
    ) -> None:
        """Log the full ranked candidate pool as a single RawEvent."""
        try:
            event_id = str(uuid.uuid4())
            client_event_id = f"gen-candidates-{trip_id}"
            payload = {
                "candidateCount": len(candidates),
                "rankedCount": len(ranked_meta),
                "generationMethod": generation_method,
                "logMeta": log_meta,
                "rankedPool": [
                    {
                        "id": m["id"],
                        "rank": m.get("rank"),
                        "slotType": m.get("slotType"),
                    }
                    for m in ranked_meta
                ],
            }
            await self._db.execute(
                """
                INSERT INTO "RawEvent" (
                    id, "userId", "sessionId", "tripId",
                    "clientEventId", "eventType", "intentClass",
                    surface, payload, "createdAt"
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, 'itinerary_generated', 'contextual',
                    'generation_engine', $6, NOW()
                )
                ON CONFLICT ("userId", "clientEventId") DO NOTHING
                """,
                event_id,
                user_id,
                session_id,
                trip_id,
                client_event_id,
                json.dumps(payload),
            )
        except Exception:
            logger.exception("Failed to log candidate pool RawEvent for trip=%s", trip_id)

    async def _register_prompt_version(self, log_meta: dict[str, Any]) -> None:
        """
        Upsert a ModelRegistry record for the current ranker prompt version.
        Uses ON CONFLICT DO NOTHING — idempotent across calls.
        """
        try:
            registry_id = str(uuid.uuid4())
            config_snapshot = {
                "model": log_meta.get("model", RANKER_MODEL),
                "promptVersion": log_meta.get("promptVersion", RANKER_PROMPT_VERSION),
                "avgLatencyMs": log_meta.get("latencyMs"),
            }
            await self._db.execute(
                """
                INSERT INTO "ModelRegistry" (
                    id, "modelName", "modelVersion",
                    stage, "modelType", description,
                    "configSnapshot", "createdAt", "updatedAt"
                ) VALUES (
                    $1, $2, $3,
                    'production', 'llm_ranker',
                    'Solo itinerary LLM ranker',
                    $4, NOW(), NOW()
                )
                ON CONFLICT ("modelName", "modelVersion") DO NOTHING
                """,
                registry_id,
                "solo-itinerary-ranker",
                log_meta.get("promptVersion", RANKER_PROMPT_VERSION),
                json.dumps(config_snapshot),
            )
        except Exception:
            logger.exception("Failed to register prompt version in ModelRegistry")


def _estimate_cost(log_meta: dict[str, Any]) -> float | None:
    """Rough USD cost estimate from token counts."""
    input_tokens = log_meta.get("inputTokens")
    output_tokens = log_meta.get("outputTokens")
    if input_tokens is None or output_tokens is None:
        return None
    return round(
        input_tokens * _COST_PER_INPUT_TOKEN + output_tokens * _COST_PER_OUTPUT_TOKEN,
        6,
    )
