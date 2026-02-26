"""Pipeline D: LLM Research Synthesis orchestrator.

Usage:
    python3 -m services.api.pipeline.research_pipeline bend --triggered-by admin_seed [--write-back]
"""
import argparse
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg

from services.api.pipeline.city_configs import get_city_config
from services.api.pipeline.source_bundle import assemble_source_bundle
from services.api.pipeline.research_llm import (
    run_pass_a, run_pass_b, NonRetryableAPIError,
    INPUT_COST_PER_1M, OUTPUT_COST_PER_1M, MODEL_NAME,
)
from services.api.pipeline.research_validator import validate_full
from services.api.pipeline.venue_resolver import resolve_venue_names, MatchType
from services.api.pipeline.cross_reference import (
    reconstruct_c_signal, score_cross_reference, DSignal,
)

logger = logging.getLogger(__name__)

MAX_DAILY_COST_USD = 25.0
CITY_COOLDOWN_HOURS = 24
CIRCUIT_BREAKER_THRESHOLD = 3
DELTA_THRESHOLD = 0.40
WRITE_BACK_BATCH_SIZE = 25

STATUS_QUEUED = "QUEUED"
STATUS_ASSEMBLING = "ASSEMBLING_BUNDLE"
STATUS_PASS_A = "RUNNING_PASS_A"
STATUS_PASS_B = "RUNNING_PASS_B"
STATUS_VALIDATING = "VALIDATING"
STATUS_RESOLVING = "RESOLVING"
STATUS_CROSS_REF = "CROSS_REFERENCING"
STATUS_WRITING = "WRITING_BACK"
STATUS_COMPLETE = "COMPLETE"
STATUS_VALIDATION_FAILED = "VALIDATION_FAILED"
STATUS_ERROR = "ERROR"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_COST_PER_1M + output_tokens * OUTPUT_COST_PER_1M) / 1_000_000


def should_flag_delta(c_confidence: float, d_confidence: float) -> bool:
    return abs(d_confidence - c_confidence) > DELTA_THRESHOLD


def extract_d_features(node: dict) -> dict:
    """Extract Pipeline D features for RankingEvent logging."""
    has_d = node.get("pipelineDConfidence") is not None
    return {
        "hasDSignal": has_d,
        "hasCSignal": (node.get("convergenceScore") or 0) > 0,
        "dCAgreement": node.get("crossRefAgreementScore"),
        "signalConflictAtServe": node.get("signalConflictFlag", False),
        "pipelineDConfidence": node.get("pipelineDConfidence"),
    }


async def check_cost_budget(pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as conn:
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        spent = await conn.fetchval(
            'SELECT COALESCE(SUM("totalCostUsd"), 0) FROM research_jobs WHERE "createdAt" >= $1',
            today_start)
        return (spent or 0) < MAX_DAILY_COST_USD


async def check_city_cooldown(pool: asyncpg.Pool, city_slug: str) -> bool:
    async with pool.acquire() as conn:
        last_run = await conn.fetchval(
            'SELECT MAX("createdAt") FROM research_jobs WHERE "cityId" = $1 AND status = $2',
            city_slug, STATUS_COMPLETE)
        if last_run is None:
            return True
        return last_run < _now() - timedelta(hours=CITY_COOLDOWN_HOURS)


async def check_circuit_breaker(pool: asyncpg.Pool) -> bool:
    async with pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM (
                SELECT status FROM research_jobs ORDER BY "createdAt" DESC LIMIT $1
            ) recent WHERE status IN ($2::"ResearchJobStatus", $3::"ResearchJobStatus")
        """, CIRCUIT_BREAKER_THRESHOLD, STATUS_VALIDATION_FAILED, STATUS_ERROR)
        return (count or 0) < CIRCUIT_BREAKER_THRESHOLD


async def _create_job(conn, city_slug: str, triggered_by: str, model_version: str) -> str:
    job_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO research_jobs (id, "cityId", status, "triggeredBy", "modelVersion", "createdAt")
           VALUES ($1, $2, $3::"ResearchJobStatus", $4::"ResearchTrigger", $5, $6)""",
        job_id, city_slug, STATUS_QUEUED, triggered_by, model_version, _now())
    return job_id


_VALID_JOB_COLUMNS = frozenset({
    "passATokens", "passBTokens", "totalCostUsd", "venuesResearched",
    "venuesResolved", "venuesUnresolved", "validationWarnings",
    "errorMessage", "completedAt",
})


async def _update_job_status(conn, job_id: str, status: str, **kwargs):
    for key in kwargs:
        if key not in _VALID_JOB_COLUMNS:
            raise ValueError(f"Invalid column for job update: {key}")
    sets = ['"status" = $2::"ResearchJobStatus"']
    vals: list = [job_id, status]
    idx = 3
    for key, val in kwargs.items():
        sets.append(f'"{key}" = ${idx}')
        vals.append(val)
        idx += 1
    await conn.execute(f"UPDATE research_jobs SET {', '.join(sets)} WHERE id = $1", *vals)


async def _fetch_vibe_vocabulary(conn) -> list[str]:
    rows = await conn.fetch('SELECT slug FROM vibe_tags WHERE "isActive" = true')
    return [r["slug"] for r in rows]


async def _fetch_venue_candidates(conn, city_slug: str) -> list[str]:
    rows = await conn.fetch(
        'SELECT "canonicalName" FROM activity_nodes WHERE city = $1 AND "isCanonical" = true',
        city_slug)
    return [r["canonicalName"] for r in rows]


async def _fetch_c_baseline_median(conn, city_slug: str) -> Optional[float]:
    val = await conn.fetchval(
        'SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY "convergenceScore") '
        'FROM activity_nodes WHERE city = $1 AND "convergenceScore" IS NOT NULL',
        city_slug)
    return float(val) if val is not None else None


async def run_research_pipeline(
    pool: asyncpg.Pool,
    city_slug: str,
    *,
    triggered_by: str = "admin_seed",
    api_key: Optional[str] = None,
    write_back: bool = False,
) -> dict:
    """Execute Pipeline D for a city. Default dry-run (write_back=False)."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY required")

    config = get_city_config(city_slug)
    if config is None:
        raise ValueError(f"City '{city_slug}' not in CITY_CONFIGS allowlist")

    if triggered_by != "admin_seed":
        if not await check_cost_budget(pool):
            return {"status": "BLOCKED", "reason": "daily_cost_cap"}
        if not await check_city_cooldown(pool, city_slug):
            return {"status": "BLOCKED", "reason": "city_cooldown"}
        if not await check_circuit_breaker(pool):
            return {"status": "BLOCKED", "reason": "circuit_breaker"}

    async with pool.acquire() as conn:
        job_id = await _create_job(conn, city_slug, triggered_by, MODEL_NAME)

    try:
        # Step 1: Assemble bundle
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_ASSEMBLING)
        bundle = await assemble_source_bundle(city_slug)

        # Step 2: Pass A
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_PASS_A)
        pass_a_result = await run_pass_a(bundle, api_key=api_key)
        pass_a = pass_a_result["parsed"]
        total_input = pass_a_result["input_tokens"]
        total_output = pass_a_result["output_tokens"]

        async with pool.acquire() as conn:
            synthesis_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO city_research_syntheses
                   (id, "researchJobId", "cityId", "neighborhoodCharacter",
                    "temporalPatterns", "peakAndDeclineFlags", "sourceAmplificationFlags",
                    "divergenceSignals", "synthesisConfidence", "modelVersion", "generatedAt")
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                synthesis_id, job_id, city_slug,
                json.dumps(pass_a.get("neighborhood_character", {})),
                json.dumps(pass_a.get("temporal_patterns", {})),
                json.dumps(pass_a.get("peak_and_decline_flags", [])),
                json.dumps(pass_a.get("source_amplification_flags", [])),
                json.dumps(pass_a.get("divergence_signals", [])),
                pass_a.get("synthesis_confidence", 0),
                MODEL_NAME, _now())

            # Step 3: Pass B
            await _update_job_status(conn, job_id, STATUS_PASS_B)
            vocab = await _fetch_vibe_vocabulary(conn)
            venue_names = await _fetch_venue_candidates(conn, city_slug)

        pass_b_result = await run_pass_b(bundle, pass_a, venue_names, vocab, api_key=api_key)
        venue_signals = pass_b_result["venues"]
        total_input += pass_b_result["total_input_tokens"]
        total_output += pass_b_result["total_output_tokens"]

        # Step 4: Validate
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_VALIDATING)
            c_median = await _fetch_c_baseline_median(conn, city_slug)

        validation = validate_full(pass_a, venue_signals, set(vocab), c_baseline_median=c_median)
        if not validation.passed:
            async with pool.acquire() as conn:
                await _update_job_status(conn, job_id, STATUS_VALIDATION_FAILED,
                                         validationWarnings=json.dumps(validation.errors + validation.warnings),
                                         errorMessage="; ".join(validation.errors))
            return {"status": STATUS_VALIDATION_FAILED, "errors": validation.errors,
                    "warnings": validation.warnings, "job_id": job_id}

        # Step 5: Resolve
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_RESOLVING)
        resolution_results = await resolve_venue_names(pool, city_slug, venue_signals)

        # Store venue signals + unresolved
        async with pool.acquire() as conn:
            resolved_count = 0
            unresolved_count = 0
            for i, signal in enumerate(venue_signals):
                res = resolution_results[i] if i < len(resolution_results) else None
                signal_id = str(uuid.uuid4())
                match_type = res.match_type.value if res else "unresolved"
                node_id = res.activity_node_id if res else None
                confidence = res.confidence if res else 0.0

                await conn.execute(
                    """INSERT INTO venue_research_signals
                       (id, "researchJobId", "cityResearchSynthesisId", "activityNodeId",
                        "venueNameRaw", "resolutionMatchType", "resolutionConfidence",
                        "vibeTags", "touristScore", "temporalNotes",
                        "sourceAmplification", "localVsTouristSignalConflict",
                        "researchConfidence", "knowledgeSource", notes, "createdAt")
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::"KnowledgeSource",$15,$16)""",
                    signal_id, job_id, synthesis_id, node_id,
                    signal.get("venue_name", ""), match_type, confidence,
                    signal.get("vibe_tags", []), signal.get("tourist_score"),
                    signal.get("temporal_notes"),
                    signal.get("source_amplification", False),
                    signal.get("local_vs_tourist_signal_conflict", False),
                    signal.get("research_confidence"),
                    signal.get("knowledge_source", "neither"),
                    signal.get("notes"), _now())

                if node_id:
                    resolved_count += 1
                else:
                    unresolved_count += 1
                    await conn.execute(
                        """INSERT INTO unresolved_research_signals
                           (id, "venueResearchSignalId", "cityId", "venueNameRaw",
                            "resolutionAttempts", "lastAttemptAt")
                           VALUES ($1, $2, $3, $4, 1, $5)""",
                        str(uuid.uuid4()), signal_id, city_slug,
                        signal.get("venue_name", ""), _now())

            # Step 6: Cross-reference
            await _update_job_status(conn, job_id, STATUS_CROSS_REF)
            flagged_count = 0

            for i, signal in enumerate(venue_signals):
                res = resolution_results[i] if i < len(resolution_results) else None
                if not res or not res.activity_node_id:
                    continue

                node = await conn.fetchrow(
                    """SELECT "convergenceScore", "authorityScore", tourist_score, "sourceCount"
                       FROM activity_nodes WHERE id = $1""",
                    res.activity_node_id)
                if not node:
                    continue

                qs_count = await conn.fetchval(
                    'SELECT COUNT(*) FROM quality_signals WHERE "activityNodeId" = $1',
                    res.activity_node_id)

                c_tag_rows = await conn.fetch(
                    """SELECT vt.slug FROM activity_node_vibe_tags anvt
                       JOIN vibe_tags vt ON anvt."vibeTagId" = vt.id
                       WHERE anvt."activityNodeId" = $1""",
                    res.activity_node_id)
                node_dict = dict(node)
                node_dict["_vibe_tags"] = [r["slug"] for r in c_tag_rows]

                c_signal = reconstruct_c_signal(node_dict, qs_count or 0)
                d_signal = DSignal(
                    tourist_score=signal.get("tourist_score"),
                    research_confidence=signal.get("research_confidence", 0),
                    vibe_tags=signal.get("vibe_tags", []),
                    source_amplification=signal.get("source_amplification", False),
                    knowledge_source=signal.get("knowledge_source", "neither"))

                cross_ref = score_cross_reference(c_signal, d_signal)
                flagged = should_flag_delta(c_signal.convergence, d_signal.research_confidence)
                resolution_action = "flagged_delta" if flagged else None
                if flagged:
                    flagged_count += 1

                await conn.execute(
                    """INSERT INTO cross_reference_results
                       (id, "activityNodeId", "cityId", "researchJobId",
                        "hasPipelineDSignal", "hasPipelineCSignal",
                        "dOnly", "cOnly", "bothAgree", "bothConflict",
                        "tagAgreementScore", "touristScoreDelta", "signalConflict",
                        "mergedVibeTags", "mergedTouristScore", "mergedConfidence",
                        "resolutionAction", "computedAt")
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                       ON CONFLICT ("activityNodeId", "researchJobId") DO UPDATE SET
                        "mergedConfidence" = EXCLUDED."mergedConfidence",
                        "computedAt" = EXCLUDED."computedAt\"""",
                    str(uuid.uuid4()), res.activity_node_id, city_slug, job_id,
                    cross_ref.has_d_signal, cross_ref.has_c_signal,
                    cross_ref.d_only, cross_ref.c_only,
                    cross_ref.both_agree, cross_ref.both_conflict,
                    cross_ref.tag_agreement_score, cross_ref.tourist_score_delta,
                    cross_ref.signal_conflict,
                    cross_ref.merged_vibe_tags, cross_ref.merged_tourist_score,
                    cross_ref.merged_confidence, resolution_action, _now())

            # Step 7: Write-back (only with --write-back)
            if write_back:
                await _update_job_status(conn, job_id, STATUS_WRITING)
                cross_refs = await conn.fetch(
                    """SELECT cr."activityNodeId", cr."mergedConfidence", cr."tagAgreementScore",
                              cr."signalConflict", vrs."researchConfidence",
                              vrs."sourceAmplification", vrs."temporalNotes"
                       FROM cross_reference_results cr
                       JOIN venue_research_signals vrs ON vrs."activityNodeId" = cr."activityNodeId"
                         AND vrs."researchJobId" = cr."researchJobId"
                       WHERE cr."researchJobId" = $1 AND cr."resolutionAction" IS NULL""",
                    job_id)

                for batch_start in range(0, len(cross_refs), WRITE_BACK_BATCH_SIZE):
                    batch = cross_refs[batch_start:batch_start + WRITE_BACK_BATCH_SIZE]
                    async with conn.transaction():
                        for cr in batch:
                            await conn.execute(
                                """UPDATE activity_nodes SET
                                    "researchSynthesisId" = $2,
                                    "pipelineDConfidence" = $3,
                                    "pipelineCConfidence" = $4,
                                    "crossRefAgreementScore" = $5,
                                    "sourceAmplificationFlag" = $6,
                                    "signalConflictFlag" = $7,
                                    "pipelineDTemporalNotes" = $8,
                                    "updatedAt" = $9
                                   WHERE id = $1""",
                                cr["activityNodeId"], synthesis_id,
                                cr.get("researchConfidence"),
                                cr.get("mergedConfidence"),
                                cr.get("tagAgreementScore"),
                                cr.get("sourceAmplification", False),
                                cr.get("signalConflict", False),
                                cr.get("temporalNotes"),
                                _now())

            # Finalize
            cost = _estimate_cost(total_input, total_output)
            await _update_job_status(
                conn, job_id, STATUS_COMPLETE,
                passATokens=pass_a_result["input_tokens"] + pass_a_result["output_tokens"],
                passBTokens=pass_b_result["total_input_tokens"] + pass_b_result["total_output_tokens"],
                totalCostUsd=cost,
                venuesResearched=len(venue_signals),
                venuesResolved=resolved_count,
                venuesUnresolved=unresolved_count,
                validationWarnings=json.dumps(validation.warnings) if validation.warnings else None,
                completedAt=_now())

        return {
            "status": STATUS_COMPLETE, "job_id": job_id,
            "venues_researched": len(venue_signals),
            "venues_resolved": resolved_count, "venues_unresolved": unresolved_count,
            "cost_usd": cost, "flagged_for_review": flagged_count,
            "warnings": validation.warnings, "write_back": write_back}

    except NonRetryableAPIError as exc:
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_ERROR, errorMessage=str(exc))
        return {"status": STATUS_ERROR, "error": str(exc), "job_id": job_id}
    except Exception as exc:
        logger.exception("Pipeline D failed for %s", city_slug)
        async with pool.acquire() as conn:
            await _update_job_status(conn, job_id, STATUS_ERROR, errorMessage=str(exc)[:500])
        return {"status": STATUS_ERROR, "error": str(exc), "job_id": job_id}


async def main():
    parser = argparse.ArgumentParser(description="Pipeline D: LLM Research Synthesis")
    parser.add_argument("city", help="City slug")
    parser.add_argument("--triggered-by", default="admin_seed",
                        choices=["admin_seed", "tier2_graduation", "on_demand_fallback"])
    parser.add_argument("--write-back", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db_url = os.environ.get("DATABASE_URL", "")
    pool = await asyncpg.create_pool(db_url)
    try:
        result = await run_research_pipeline(pool, args.city,
                                              triggered_by=args.triggered_by,
                                              write_back=args.write_back)
        print(json.dumps(result, indent=2, default=str))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
