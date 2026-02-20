"""
Group itinerary generation engine.

Generates a shared itinerary for N group members by:
  1. Collecting all members' personaSeeds from Trip.affinityMatrix
  2. Merging them via PreferenceMerger (fairness-weighted query vector)
  3. Running Qdrant search with the merged query
  4. Scoring each candidate against all members' preferences individually
  5. Fairness-weighted ranking via FairnessEngine
  6. Same fallback cascade as solo (run_with_fallbacks)
  7. Assigning time slots (anchor-first, same logic as solo)
  8. Persisting ItinerarySlot rows (voteState = 'proposed' by default)
  9. Logging full candidate pool + per-member scores to RawEvent
  10. Registering prompt version in ModelRegistry (if LLM path taken)

Differences from solo engine:
  - Query vector is a weighted merge of N persona seeds
  - Per-member preference scores logged in RawEvent payload
  - Slots created with voteState = 'proposed' and isContested = false
  - fairnessState on Trip is read (not written — FairnessEngine handles writes)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic

from services.api.generation.fallbacks import run_with_fallbacks
from services.api.generation.preference_merger import merge_preferences, score_candidate_per_member
from services.api.generation.slot_assigner import SlotAssignment, assign_slots
from services.api.generation.ranker import RANKER_MODEL, RANKER_PROMPT_VERSION
from services.api.search.service import ActivitySearchService

logger = logging.getLogger(__name__)

# Approx cost per token for claude-sonnet-4-6 (USD)
_COST_PER_INPUT_TOKEN = 3e-6
_COST_PER_OUTPUT_TOKEN = 15e-6

# Candidate pool size for group generation (larger than solo to improve coverage)
GROUP_CANDIDATE_POOL_SIZE = 40


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class GroupGenerationEngine:
    """
    Orchestrates the full group itinerary generation pipeline.

    Injected dependencies keep this testable without real services.
    """

    def __init__(
        self,
        search_service: ActivitySearchService,
        anthropic_client: anthropic.AsyncAnthropic,
        db,
    ) -> None:
        self._search = search_service
        self._anthropic = anthropic_client
        self._db = db

    async def generate(
        self,
        trip_id: str,
        group_id: str,
        city: str,
        member_ids: list[str],
        member_seeds: list[dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
        fairness_state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run the full generation pipeline for a group trip.

        Args:
            trip_id:       UUID of the Trip record.
            group_id:      UUID of the Group record.
            city:          Trip destination city.
            member_ids:    Ordered list of member user IDs.
            member_seeds:  Parallel list of personaSeed dicts per member.
            start_date:    First day of trip (UTC).
            end_date:      Last day of trip (UTC).
            fairness_state: Trip.fairnessState (adjusts weights if present).
            session_id:    Optional session UUID for RawEvent correlation.

        Returns:
            {
                "tripId": str,
                "generationMethod": str,
                "slotsCreated": int,
                "candidatesConsidered": int,
                "memberCount": int,
                "logMeta": dict,
                "warning": str | None,
            }
        """
        pipeline_start = time.monotonic()
        session_id = session_id or str(uuid.uuid4())
        warning: str | None = None

        num_days = max(1, (end_date.date() - start_date.date()).days + 1)
        n_members = len(member_ids)

        logger.info(
            "Group generation started: trip=%s city=%s days=%d members=%d",
            trip_id, city, num_days, n_members,
        )

        # ------------------------------------------------------------------
        # Step 1: Merge member preferences into a single weighted query
        # ------------------------------------------------------------------
        merged = merge_preferences(
            member_ids=member_ids,
            member_seeds=member_seeds,
            city=city,
            fairness_state=fairness_state,
        )
        logger.info(
            "Preference merge: vibes=%s pace=%s budget=%s weights=%s",
            merged.dominant_vibes,
            merged.blended_pace,
            merged.blended_budget,
            merged.member_weights,
        )

        # ------------------------------------------------------------------
        # Step 2: Qdrant vector search with merged query
        # ------------------------------------------------------------------
        search_result = await self._search.search(
            query=merged.query,
            city=city,
            limit=GROUP_CANDIDATE_POOL_SIZE,
        )

        candidates: list[dict[str, Any]] = search_result.get("results", [])
        qdrant_available = True

        if search_result.get("warning") and not candidates:
            qdrant_available = False
            warning = search_result["warning"]
            logger.warning("Qdrant unavailable for group gen: %s", warning)

        logger.info(
            "Group candidate pool: %d nodes (qdrant_available=%s)",
            len(candidates), qdrant_available,
        )

        # ------------------------------------------------------------------
        # Step 3: Score each candidate per-member
        # ------------------------------------------------------------------
        per_member_scores: dict[str, dict[str, float]] = {}
        for candidate in candidates:
            node_id = candidate.get("id", "")
            per_member_scores[node_id] = score_candidate_per_member(
                candidate=candidate,
                member_seeds=member_seeds,
                member_ids=member_ids,
            )

        # ------------------------------------------------------------------
        # Step 4: Fallback cascade — same tiers as solo
        # Uses merged.blended_pace/budget as the effective persona_seed
        # ------------------------------------------------------------------
        effective_persona = {
            "vibes": merged.dominant_vibes,
            "pace": merged.blended_pace,
            "budget": merged.blended_budget,
        }

        ranked_meta, resolved_candidates, generation_method, log_meta = (
            await run_with_fallbacks(
                candidates=candidates,
                persona_seed=effective_persona,
                city=city,
                anthropic_client=self._anthropic,
                db=self._db,
                qdrant_available=qdrant_available,
            )
        )

        # ------------------------------------------------------------------
        # Step 5: Slot assignment (same anchor-first logic as solo)
        # ------------------------------------------------------------------
        slots: list[SlotAssignment] = []

        if generation_method != "template_fallback":
            slots = assign_slots(
                ranked_nodes=resolved_candidates,
                ranked_meta=ranked_meta,
                trip_start_date=start_date,
                num_days=num_days,
            )
        else:
            logger.warning("Using template itinerary for group trip=%s", trip_id)

        # ------------------------------------------------------------------
        # Step 6: Persist ItinerarySlot rows with voteState = 'proposed'
        # ------------------------------------------------------------------
        slots_created = 0
        if slots:
            slots_created = await self._write_group_slots(trip_id, slots)

        # ------------------------------------------------------------------
        # Step 7: Update Trip.generationMethod
        # ------------------------------------------------------------------
        await self._update_trip_generation_method(trip_id, generation_method)

        # ------------------------------------------------------------------
        # Step 8: Log candidate pool + per-member scores to RawEvent
        # ------------------------------------------------------------------
        # Use group_id as "userId" for the group-level event;
        # individual member events are emitted separately during voting.
        await self._log_group_candidate_pool(
            group_id=group_id,
            session_id=session_id,
            trip_id=trip_id,
            candidates=candidates,
            ranked_meta=ranked_meta,
            per_member_scores=per_member_scores,
            generation_method=generation_method,
            log_meta=log_meta,
            merger_meta=merged.merger_meta,
        )

        # ------------------------------------------------------------------
        # Step 9: Register prompt version (if LLM path taken)
        # ------------------------------------------------------------------
        if generation_method == "llm":
            await self._register_prompt_version(log_meta)

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        total_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.info(
            "Group generation complete: trip=%s method=%s slots=%d candidates=%d latency=%dms",
            trip_id, generation_method, slots_created, len(candidates), total_ms,
        )

        return {
            "tripId": trip_id,
            "generationMethod": generation_method,
            "slotsCreated": slots_created,
            "candidatesConsidered": len(candidates),
            "memberCount": n_members,
            "logMeta": {
                **log_meta,
                "pipelineLatencyMs": total_ms,
                "costEstimateUsd": _estimate_cost(log_meta),
                "mergerMeta": merged.merger_meta,
            },
            "warning": warning,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_group_slots(
        self,
        trip_id: str,
        slots: list[SlotAssignment],
    ) -> int:
        """
        Bulk-insert ItinerarySlot rows for group trips.

        Differences from solo:
          - voteState = 'proposed' (voting lifecycle begins after generation)
          - isContested = false (starts false; CampDetector sets it later)
        """
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
                        "voteState", "isContested",
                        "createdAt", "updatedAt"
                    ) VALUES (
                        $1, $2, $3,
                        $4, $5,
                        $6, 'proposed',
                        $7, $8, $9,
                        false, false,
                        'proposed', false,
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
            logger.exception(
                "Failed to update Trip.generationMethod for group trip=%s", trip_id
            )

    async def _log_group_candidate_pool(
        self,
        group_id: str,
        session_id: str,
        trip_id: str,
        candidates: list[dict[str, Any]],
        ranked_meta: list[dict[str, Any]],
        per_member_scores: dict[str, dict[str, float]],
        generation_method: str,
        log_meta: dict[str, Any],
        merger_meta: dict[str, Any],
    ) -> None:
        """Log the full group candidate pool + per-member scores as RawEvent."""
        try:
            event_id = str(uuid.uuid4())
            client_event_id = f"group-gen-candidates-{trip_id}"
            payload = {
                "candidateCount": len(candidates),
                "rankedCount": len(ranked_meta),
                "generationMethod": generation_method,
                "mergerMeta": merger_meta,
                "logMeta": log_meta,
                "rankedPool": [
                    {
                        "id": m["id"],
                        "rank": m.get("rank"),
                        "slotType": m.get("slotType"),
                        "memberScores": per_member_scores.get(m["id"], {}),
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
                    $5, 'group_itinerary_generated', 'contextual',
                    'group_generation_engine', $6, NOW()
                )
                ON CONFLICT ("userId", "clientEventId") DO NOTHING
                """,
                event_id,
                group_id,
                session_id,
                trip_id,
                client_event_id,
                json.dumps(payload),
            )
        except Exception:
            logger.exception(
                "Failed to log group candidate pool RawEvent for trip=%s", trip_id
            )

    async def _register_prompt_version(self, log_meta: dict[str, Any]) -> None:
        """Upsert a ModelRegistry record for the group ranker prompt version."""
        try:
            registry_id = str(uuid.uuid4())
            config_snapshot = {
                "model": log_meta.get("model", RANKER_MODEL),
                "promptVersion": log_meta.get("promptVersion", RANKER_PROMPT_VERSION),
                "avgLatencyMs": log_meta.get("latencyMs"),
                "context": "group_generation",
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
                    'Group itinerary LLM ranker',
                    $4, NOW(), NOW()
                )
                ON CONFLICT ("modelName", "modelVersion") DO NOTHING
                """,
                registry_id,
                "group-itinerary-ranker",
                log_meta.get("promptVersion", RANKER_PROMPT_VERSION),
                json.dumps(config_snapshot),
            )
        except Exception:
            logger.exception(
                "Failed to register group prompt version in ModelRegistry"
            )


def _estimate_cost(log_meta: dict[str, Any]) -> float | None:
    """Rough USD cost estimate from token counts."""
    input_tokens = log_meta.get("inputTokens")
    output_tokens = log_meta.get("outputTokens")
    if input_tokens is None or output_tokens is None:
        return None
    return round(
        input_tokens * _COST_PER_INPUT_TOKEN
        + output_tokens * _COST_PER_OUTPUT_TOKEN,
        6,
    )
