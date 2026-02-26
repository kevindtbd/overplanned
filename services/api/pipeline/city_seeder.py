"""
End-to-end city seeding orchestrator.

Seeds a city with all data sources, resolves entities, extracts/infers
vibe tags, scores convergence + authority, and syncs to Qdrant.

Pipeline steps (in order):
  1. Scrape — blog RSS, Atlas Obscura, Arctic Shift (Reddit)
  2. Entity resolution — deduplicate new ActivityNodes
  3. LLM vibe extraction — Haiku-based tag classification (untagged nodes)
  4. Rule-based vibe inference — deterministic category→tag baseline
  5. Convergence + authority scoring — cross-source signal aggregation
  6. Qdrant sync — embed and upsert to vector DB

Checkpoint/resume:
  - Progress tracked in a JSON file per city: data/seed_progress/{city}.json
  - Each step is idempotent (safe to re-run)
  - On crash, restarts from the last completed step
  - Counters: nodes_scraped, nodes_resolved, nodes_tagged, nodes_indexed

Usage:
    pool = await asyncpg.create_pool(DATABASE_URL)
    result = await seed_city(pool, "tokyo", anthropic_api_key=api_key)
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import asyncpg

from services.api.pipeline.city_configs import validate_city_seed, ValidationResult
from services.api.pipeline.entity_resolution import EntityResolver
from services.api.pipeline.llm_fallback_seeder import run_llm_fallback
from services.api.pipeline.vibe_extraction import run_extraction
from services.api.pipeline.rule_inference import run_rule_inference
from services.api.pipeline.convergence import run_convergence_scoring
from services.api.pipeline import qdrant_sync
from services.api.scrapers.blog_rss import BlogRssScraper
from services.api.scrapers.atlas_obscura import AtlasObscuraScraper
from services.api.scrapers.arctic_shift import ArcticShiftScraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------

PROGRESS_DIR = Path("data/seed_progress")
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStep(str, Enum):
    SCRAPE = "scrape"
    LLM_FALLBACK = "llm_fallback"
    ENTITY_RESOLUTION = "entity_resolution"
    VIBE_EXTRACTION = "vibe_extraction"
    RULE_INFERENCE = "rule_inference"
    CONVERGENCE = "convergence"
    QDRANT_SYNC = "qdrant_sync"


# Ordered list of steps — execution follows this sequence
STEP_ORDER: list[PipelineStep] = [
    PipelineStep.SCRAPE,
    PipelineStep.LLM_FALLBACK,
    PipelineStep.ENTITY_RESOLUTION,
    PipelineStep.VIBE_EXTRACTION,
    PipelineStep.RULE_INFERENCE,
    PipelineStep.CONVERGENCE,
    PipelineStep.QDRANT_SYNC,
]


@dataclass
class StepProgress:
    """Progress state for a single pipeline step."""
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class SeedProgress:
    """Full pipeline progress for a city seed run."""
    city: str = ""
    run_id: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    overall_status: StepStatus = StepStatus.PENDING
    nodes_scraped: int = 0
    nodes_resolved: int = 0
    nodes_tagged: int = 0
    nodes_indexed: int = 0
    steps: dict[str, StepProgress] = field(default_factory=dict)

    def __post_init__(self):
        # Ensure all steps exist
        for step in STEP_ORDER:
            if step.value not in self.steps:
                self.steps[step.value] = StepProgress()


def _progress_path(city: str) -> Path:
    """Path to the progress JSON file for a city."""
    return PROGRESS_DIR / f"{city.lower().replace(' ', '_')}.json"


def _load_progress(city: str) -> SeedProgress:
    """Load existing progress or create fresh."""
    path = _progress_path(city)
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            progress = SeedProgress(city=city, run_id=data.get("run_id", ""))
            progress.started_at = data.get("started_at")
            progress.finished_at = data.get("finished_at")
            progress.overall_status = StepStatus(data.get("overall_status", "pending"))
            progress.nodes_scraped = data.get("nodes_scraped", 0)
            progress.nodes_resolved = data.get("nodes_resolved", 0)
            progress.nodes_tagged = data.get("nodes_tagged", 0)
            progress.nodes_indexed = data.get("nodes_indexed", 0)

            for step_name, step_data in data.get("steps", {}).items():
                if step_name in {s.value for s in STEP_ORDER}:
                    sp = StepProgress()
                    sp.status = StepStatus(step_data.get("status", "pending"))
                    sp.started_at = step_data.get("started_at")
                    sp.finished_at = step_data.get("finished_at")
                    sp.error = step_data.get("error")
                    sp.metrics = step_data.get("metrics", {})
                    progress.steps[step_name] = sp

            # Ensure all steps exist
            for step in STEP_ORDER:
                if step.value not in progress.steps:
                    progress.steps[step.value] = StepProgress()

            return progress
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning("Corrupt progress file for %s, starting fresh", city)

    return SeedProgress(city=city)


def _save_progress(progress: SeedProgress) -> None:
    """Persist progress to disk."""
    path = _progress_path(progress.city)

    data: dict[str, Any] = {
        "city": progress.city,
        "run_id": progress.run_id,
        "started_at": progress.started_at,
        "finished_at": progress.finished_at,
        "overall_status": progress.overall_status.value,
        "nodes_scraped": progress.nodes_scraped,
        "nodes_resolved": progress.nodes_resolved,
        "nodes_tagged": progress.nodes_tagged,
        "nodes_indexed": progress.nodes_indexed,
        "steps": {},
    }

    for step_name, step_prog in progress.steps.items():
        data["steps"][step_name] = {
            "status": step_prog.status.value,
            "started_at": step_prog.started_at,
            "finished_at": step_prog.finished_at,
            "error": step_prog.error,
            "metrics": step_prog.metrics,
        }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _should_run_step(progress: SeedProgress, step: PipelineStep) -> bool:
    """Check if a step needs to run (not already completed)."""
    sp = progress.steps.get(step.value)
    if sp is None:
        return True
    return sp.status != StepStatus.COMPLETED


def _mark_step_start(progress: SeedProgress, step: PipelineStep) -> None:
    """Mark a step as in-progress and persist."""
    sp = progress.steps[step.value]
    sp.status = StepStatus.IN_PROGRESS
    sp.started_at = datetime.now(timezone.utc).isoformat()
    sp.error = None
    _save_progress(progress)


def _mark_step_done(
    progress: SeedProgress,
    step: PipelineStep,
    metrics: Optional[dict[str, Any]] = None,
) -> None:
    """Mark a step as completed and persist."""
    sp = progress.steps[step.value]
    sp.status = StepStatus.COMPLETED
    sp.finished_at = datetime.now(timezone.utc).isoformat()
    if metrics:
        sp.metrics = metrics
    _save_progress(progress)


def _mark_step_failed(
    progress: SeedProgress,
    step: PipelineStep,
    error: str,
) -> None:
    """Mark a step as failed and persist."""
    sp = progress.steps[step.value]
    sp.status = StepStatus.FAILED
    sp.finished_at = datetime.now(timezone.utc).isoformat()
    sp.error = error
    _save_progress(progress)


# ---------------------------------------------------------------------------
# Seed result
# ---------------------------------------------------------------------------

@dataclass
class SeedResult:
    """Final result of a city seed run."""
    city: str
    success: bool
    nodes_scraped: int = 0
    nodes_resolved: int = 0
    nodes_tagged: int = 0
    nodes_indexed: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    total_duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    # Post-seed validation result (populated automatically after each successful run)
    validation: Optional[ValidationResult] = None


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

SENTINEL_NODE_ID = "00000000-0000-0000-0000-000000000000"


async def _ensure_sentinel_node(pool: asyncpg.Pool) -> None:
    """
    Ensure the sentinel ActivityNode exists.

    Scrapers store QualitySignals with this sentinel activityNodeId when the
    real node doesn't exist yet. The LLM fallback seeder later creates real
    nodes and relinks the signals.
    """
    await pool.execute(
        """
        INSERT INTO activity_nodes (
            id, name, slug, "canonicalName", city, country, category,
            latitude, longitude, "sourceCount",
            "convergenceScore", "authorityScore",
            "isCanonical", status, "createdAt", "updatedAt"
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        ON CONFLICT (id) DO NOTHING
        """,
        SENTINEL_NODE_ID,
        "__unresolved__",
        "__unresolved__",
        "__unresolved__",
        "__sentinel__",
        "__sentinel__",
        "experience",
        0.0,
        0.0,
        0,
        0.0,
        0.0,
        False,
        "archived",
        datetime.now(timezone.utc).replace(tzinfo=None),
        datetime.now(timezone.utc).replace(tzinfo=None),
    )


async def _persist_scraper_signals(
    pool: asyncpg.Pool,
    signals: list[dict[str, Any]],
    source_name: str,
) -> int:
    """
    Persist in-memory quality signals to the DB via batch insert.

    Scrapers like Arctic Shift and Atlas Obscura accumulate signals in memory
    rather than writing to DB directly (unlike Blog RSS). This function
    writes them with the sentinel activityNodeId so the LLM fallback seeder
    can pick them up.

    Uses executemany for efficient batch writes instead of per-row inserts.

    Returns the number of signals persisted.
    """
    if not signals:
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Build batch args
    rows = []
    for signal in signals:
        signal_id = str(uuid.uuid4())
        metadata = signal.get("metadata")
        metadata_json = json.dumps(metadata) if metadata else None

        rows.append((
            signal_id,
            signal.get("activityNodeId") or SENTINEL_NODE_ID,
            signal.get("sourceName", source_name),
            signal.get("sourceUrl"),
            signal.get("sourceAuthority", 0.5),
            signal.get("signalType", "mention"),
            signal.get("rawExcerpt"),
            now,
            now,
            metadata_json,
        ))

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO quality_signals (
                    id, "activityNodeId", "sourceName", "sourceUrl",
                    "sourceAuthority", "signalType", "rawExcerpt",
                    "extractedAt", "createdAt", "extractionMetadata"
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )

    logger.info("Persisted %d signals from %s", len(rows), source_name)
    return len(rows)


async def _step_scrape(
    pool: asyncpg.Pool,
    city: str,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 1: Run all scrapers for the city.

    Each scraper runs independently — one failure doesn't block others.
    After scraping, persists in-memory signals to the DB so the LLM
    fallback seeder can create ActivityNodes from them.

    Returns metrics dict with per-scraper stats.
    """
    metrics: dict[str, Any] = {}
    total_scraped = 0

    # Ensure sentinel node exists for unlinked quality signals
    await _ensure_sentinel_node(pool)

    # Blog RSS — filter feeds by city (persists to DB in store() directly)
    try:
        blog_scraper = BlogRssScraper(db_pool=pool, feed_filter=city)
        stats = blog_scraper.run()
        metrics["blog_rss"] = stats
        total_scraped += stats.get("success", 0)
        logger.info("Blog RSS scrape: %s", stats)
    except Exception as exc:
        metrics["blog_rss"] = {"error": str(exc)}
        logger.exception("Blog RSS scrape failed for %s", city)

    # Atlas Obscura (accumulates in memory — persist after run)
    atlas_scraper = None
    try:
        atlas_scraper = AtlasObscuraScraper(city=city)
        stats = atlas_scraper.run()
        metrics["atlas_obscura"] = stats
        total_scraped += stats.get("success", 0)
        logger.info("Atlas Obscura scrape: %s", stats)
    except Exception as exc:
        metrics["atlas_obscura"] = {"error": str(exc)}
        logger.exception("Atlas Obscura scrape failed for %s", city)

    # Persist Atlas Obscura signals
    if atlas_scraper is not None:
        try:
            results = atlas_scraper.collect_results()
            # Atlas results are ActivityNode-shaped — normalize to QualitySignal shape
            atlas_signals = []
            for node in results:
                for qs in node.get("quality_signals", []):
                    atlas_signals.append({
                        "sourceName": qs.get("source", "atlas_obscura"),
                        "sourceUrl": node.get("source_url"),
                        "sourceAuthority": qs.get("score", 0.75),
                        "signalType": qs.get("signal_type", "hidden_gem"),
                        "rawExcerpt": node.get("description", ""),
                        "metadata": {
                            "venue_name": node.get("name"),
                            "city": node.get("city", city),
                            "category": node.get("category"),
                            "evidence": qs.get("evidence"),
                        },
                    })
            persisted = await _persist_scraper_signals(
                pool, atlas_signals, "atlas_obscura"
            )
            metrics.setdefault("atlas_obscura", {})["signals_persisted"] = persisted
        except Exception as exc:
            logger.exception("Failed to persist Atlas Obscura signals for %s", city)

    # Arctic Shift (Reddit) (accumulates in memory — persist after run)
    reddit_scraper = None
    try:
        reddit_scraper = ArcticShiftScraper(target_cities=[city])
        stats = reddit_scraper.run()
        metrics["arctic_shift"] = stats
        total_scraped += stats.get("success", 0)
        logger.info("Arctic Shift scrape: %s", stats)
    except Exception as exc:
        metrics["arctic_shift"] = {"error": str(exc)}
        logger.exception("Arctic Shift scrape failed for %s", city)

    # Persist Arctic Shift signals
    if reddit_scraper is not None:
        try:
            results = reddit_scraper.get_results()
            persisted = await _persist_scraper_signals(
                pool, results.get("quality_signals", []), "reddit"
            )
            metrics.setdefault("arctic_shift", {})["signals_persisted"] = persisted
        except Exception as exc:
            logger.exception("Failed to persist Arctic Shift signals for %s", city)

    progress.nodes_scraped += total_scraped
    metrics["total_scraped"] = total_scraped
    return metrics


async def _step_entity_resolution(
    pool: asyncpg.Pool,
    city: str,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 2: Entity resolution — deduplicate new nodes.

    Runs incremental resolution on nodes created since the scrape started.
    """
    resolver = EntityResolver(pool)

    # Use the scrape start time as the since threshold
    scrape_step = progress.steps.get(PipelineStep.SCRAPE.value)
    since = None
    if scrape_step and scrape_step.started_at:
        since = datetime.fromisoformat(scrape_step.started_at).replace(tzinfo=None)

    stats = await resolver.resolve_incremental(since=since)
    progress.nodes_resolved = stats.merges_executed

    return {
        "nodes_scanned": stats.nodes_scanned,
        "candidates_found": stats.candidates_found,
        "merges_executed": stats.merges_executed,
        "merges_by_tier": {k.value: v for k, v in stats.merges_by_tier.items()},
        "errors": stats.errors,
    }


async def _step_vibe_extraction(
    pool: asyncpg.Pool,
    city: str,
    anthropic_api_key: str,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 3: LLM-based vibe tag extraction for untagged nodes.

    Processes nodes that don't yet have llm_extraction tags.
    """
    stats = await run_extraction(pool, api_key=anthropic_api_key, limit=200)

    tagged_count = stats.tags_written
    progress.nodes_tagged += tagged_count

    return {
        "nodes_processed": stats.nodes_processed,
        "tags_written": stats.tags_written,
        "nodes_skipped": stats.nodes_skipped,
        "contradictions_flagged": stats.contradictions_flagged,
        "estimated_cost_usd": round(stats.estimated_cost_usd, 4),
        "errors": stats.errors[:10],
    }


async def _step_rule_inference(
    pool: asyncpg.Pool,
    city: str,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 4: Rule-based vibe tag inference.

    Applies deterministic category→vibe tag rules to all canonical nodes.
    """
    stats = await run_rule_inference(pool)

    progress.nodes_tagged += stats.tags_created

    return {
        "nodes_processed": stats.nodes_processed,
        "tags_created": stats.tags_created,
        "tags_skipped": stats.tags_skipped,
        "missing_vibe_tags": stats.missing_vibe_tags,
        "errors": stats.errors,
    }


async def _step_convergence(
    pool: asyncpg.Pool,
    city: str,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 5: Convergence + authority scoring.

    Scores all canonical nodes based on cross-source convergence.
    """
    stats = await run_convergence_scoring(pool)

    return {
        "nodes_processed": stats.nodes_processed,
        "nodes_updated": stats.nodes_updated,
        "nodes_skipped": stats.nodes_skipped,
        "vibe_boosts_applied": stats.vibe_boosts_applied,
        "errors": stats.errors,
    }


async def _step_qdrant_sync(
    pool: asyncpg.Pool,
    city: str,
    embedding_service,
    progress: SeedProgress,
) -> dict[str, Any]:
    """
    Step 6: Qdrant sync — embed and upsert all canonical nodes.

    Uses full sync for initial seed, incremental for re-runs.
    """
    # Check if this is first sync or incremental
    qdrant_step = progress.steps.get(PipelineStep.QDRANT_SYNC.value)
    prev_completed = (
        qdrant_step
        and qdrant_step.status == StepStatus.COMPLETED
        and qdrant_step.finished_at
    )

    if prev_completed:
        # Incremental: only sync nodes updated since last sync
        since = datetime.fromisoformat(qdrant_step.finished_at).replace(tzinfo=None)
        stats = await qdrant_sync.run_incremental_sync(
            pool, embedding_service, since=since
        )
    else:
        # Full sync for first run
        stats = await qdrant_sync.run_full_sync(pool, embedding_service)

    progress.nodes_indexed = stats.nodes_upserted

    return {
        "mode": stats.mode,
        "nodes_fetched": stats.nodes_fetched,
        "nodes_embedded": stats.nodes_embedded,
        "nodes_upserted": stats.nodes_upserted,
        "nodes_skipped": stats.nodes_skipped,
        "errors": stats.errors,
        "embedding_time_s": round(stats.embedding_time_s, 2),
        "upsert_time_s": round(stats.upsert_time_s, 2),
        "error_details": stats.error_details[:10],
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def seed_city(
    pool: asyncpg.Pool,
    city: str,
    *,
    anthropic_api_key: Optional[str] = None,
    embedding_service=None,
    skip_scrape: bool = False,
    skip_llm: bool = False,
    force_restart: bool = False,
) -> SeedResult:
    """
    Seed a city end-to-end with checkpoint/resume.

    Runs the 6-step pipeline: scrape → resolve → vibe extract →
    rule inference → convergence → Qdrant sync.

    Args:
        pool: asyncpg connection pool.
        city: City name/slug (e.g. "tokyo", "new-york").
        anthropic_api_key: API key for LLM vibe extraction.
            If None, reads from ANTHROPIC_API_KEY env var.
            If still None, skips LLM extraction step.
        embedding_service: EmbeddingService instance for Qdrant sync.
            If None, Qdrant sync step is skipped.
        skip_scrape: If True, skip the scraping step (useful for re-processing).
        skip_llm: If True, skip LLM extraction (saves API cost during dev).
        force_restart: If True, ignore existing progress and start fresh.

    Returns:
        SeedResult with aggregate counters and per-step outcomes.
    """
    t0 = time.monotonic()
    api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")

    # Load or create progress
    if force_restart:
        progress = SeedProgress(city=city)
    else:
        progress = _load_progress(city)
        progress.city = city

    if not progress.run_id:
        progress.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    if not progress.started_at:
        progress.started_at = datetime.now(timezone.utc).isoformat()

    progress.overall_status = StepStatus.IN_PROGRESS
    _save_progress(progress)

    result = SeedResult(city=city, success=True)

    logger.info("=== City seed: %s (run=%s) ===", city, progress.run_id)

    # --- Step 1: Scrape ---
    if skip_scrape:
        logger.info("Skipping scrape step (skip_scrape=True)")
        _mark_step_done(progress, PipelineStep.SCRAPE, {"skipped": True})
    elif _should_run_step(progress, PipelineStep.SCRAPE):
        logger.info("[1/7] Scraping %s...", city)
        _mark_step_start(progress, PipelineStep.SCRAPE)
        try:
            metrics = await _step_scrape(pool, city, progress)
            result.nodes_scraped = progress.nodes_scraped
            _mark_step_done(progress, PipelineStep.SCRAPE, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.SCRAPE, str(exc))
            result.errors.append(f"scrape: {exc}")
            result.steps_failed += 1
            logger.exception("Scrape step failed for %s", city)
    else:
        logger.info("[1/7] Scrape already completed, skipping")
        result.nodes_scraped = progress.nodes_scraped
        result.steps_completed += 1

    # --- Step 1.5: LLM Fallback Node Creation ---
    # Creates ActivityNodes from unlinked QualitySignals (sentinel node ID).
    # Only runs when an API key is available and LLM is not skipped.
    if skip_llm or not api_key:
        reason = "skip_llm=True" if skip_llm else "no API key"
        logger.info("[2/7] Skipping LLM fallback seeder (%s)", reason)
        _mark_step_done(progress, PipelineStep.LLM_FALLBACK, {"skipped": True, "reason": reason})
        result.steps_completed += 1
    elif _should_run_step(progress, PipelineStep.LLM_FALLBACK):
        logger.info("[2/7] LLM fallback node creation for %s...", city)
        _mark_step_start(progress, PipelineStep.LLM_FALLBACK)
        try:
            fallback_stats = await run_llm_fallback(pool, city, api_key=api_key)
            _mark_step_done(progress, PipelineStep.LLM_FALLBACK, {
                "venues_created": fallback_stats.venues_created,
                "venues_existing": fallback_stats.venues_existing,
                "signals_relinked": fallback_stats.signals_relinked,
                "estimated_cost_usd": round(fallback_stats.estimated_cost_usd, 4),
                "errors": fallback_stats.errors[:10],
            })
            result.nodes_scraped += fallback_stats.venues_created
            progress.nodes_scraped += fallback_stats.venues_created
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.LLM_FALLBACK, str(exc))
            result.errors.append(f"llm_fallback: {exc}")
            result.steps_failed += 1
            logger.exception("LLM fallback seeder failed for %s", city)
    else:
        logger.info("[2/7] LLM fallback already completed, skipping")
        result.steps_completed += 1

    # --- Step 3: Entity Resolution ---
    if _should_run_step(progress, PipelineStep.ENTITY_RESOLUTION):
        logger.info("[3/7] Entity resolution for %s...", city)
        _mark_step_start(progress, PipelineStep.ENTITY_RESOLUTION)
        try:
            metrics = await _step_entity_resolution(pool, city, progress)
            result.nodes_resolved = progress.nodes_resolved
            _mark_step_done(progress, PipelineStep.ENTITY_RESOLUTION, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.ENTITY_RESOLUTION, str(exc))
            result.errors.append(f"entity_resolution: {exc}")
            result.steps_failed += 1
            logger.exception("Entity resolution failed for %s", city)
    else:
        logger.info("[3/7] Entity resolution already completed, skipping")
        result.nodes_resolved = progress.nodes_resolved
        result.steps_completed += 1

    # --- Step 3: LLM Vibe Extraction ---
    if skip_llm or not api_key:
        reason = "skip_llm=True" if skip_llm else "no API key"
        logger.info("[4/7] Skipping LLM vibe extraction (%s)", reason)
        _mark_step_done(progress, PipelineStep.VIBE_EXTRACTION, {"skipped": True, "reason": reason})
        result.steps_completed += 1
    elif _should_run_step(progress, PipelineStep.VIBE_EXTRACTION):
        logger.info("[4/7] LLM vibe extraction for %s...", city)
        _mark_step_start(progress, PipelineStep.VIBE_EXTRACTION)
        try:
            metrics = await _step_vibe_extraction(pool, city, api_key, progress)
            result.nodes_tagged = progress.nodes_tagged
            _mark_step_done(progress, PipelineStep.VIBE_EXTRACTION, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.VIBE_EXTRACTION, str(exc))
            result.errors.append(f"vibe_extraction: {exc}")
            result.steps_failed += 1
            logger.exception("LLM vibe extraction failed for %s", city)
    else:
        logger.info("[4/7] LLM vibe extraction already completed, skipping")
        result.nodes_tagged = progress.nodes_tagged
        result.steps_completed += 1

    # --- Step 4: Rule-Based Vibe Inference ---
    if _should_run_step(progress, PipelineStep.RULE_INFERENCE):
        logger.info("[5/7] Rule-based vibe inference for %s...", city)
        _mark_step_start(progress, PipelineStep.RULE_INFERENCE)
        try:
            metrics = await _step_rule_inference(pool, city, progress)
            result.nodes_tagged = progress.nodes_tagged
            _mark_step_done(progress, PipelineStep.RULE_INFERENCE, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.RULE_INFERENCE, str(exc))
            result.errors.append(f"rule_inference: {exc}")
            result.steps_failed += 1
            logger.exception("Rule inference failed for %s", city)
    else:
        logger.info("[5/7] Rule inference already completed, skipping")
        result.nodes_tagged = progress.nodes_tagged
        result.steps_completed += 1

    # --- Step 5: Convergence Scoring ---
    if _should_run_step(progress, PipelineStep.CONVERGENCE):
        logger.info("[6/7] Convergence scoring for %s...", city)
        _mark_step_start(progress, PipelineStep.CONVERGENCE)
        try:
            metrics = await _step_convergence(pool, city, progress)
            _mark_step_done(progress, PipelineStep.CONVERGENCE, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.CONVERGENCE, str(exc))
            result.errors.append(f"convergence: {exc}")
            result.steps_failed += 1
            logger.exception("Convergence scoring failed for %s", city)
    else:
        logger.info("[6/7] Convergence scoring already completed, skipping")
        result.steps_completed += 1

    # --- Step 6: Qdrant Sync ---
    if embedding_service is None:
        logger.info("[7/7] Skipping Qdrant sync (no embedding_service)")
        _mark_step_done(progress, PipelineStep.QDRANT_SYNC, {"skipped": True, "reason": "no embedding_service"})
        result.steps_completed += 1
    elif _should_run_step(progress, PipelineStep.QDRANT_SYNC):
        logger.info("[7/7] Qdrant sync for %s...", city)
        _mark_step_start(progress, PipelineStep.QDRANT_SYNC)
        try:
            metrics = await _step_qdrant_sync(pool, city, embedding_service, progress)
            result.nodes_indexed = progress.nodes_indexed
            _mark_step_done(progress, PipelineStep.QDRANT_SYNC, metrics)
            result.steps_completed += 1
        except Exception as exc:
            _mark_step_failed(progress, PipelineStep.QDRANT_SYNC, str(exc))
            result.errors.append(f"qdrant_sync: {exc}")
            result.steps_failed += 1
            logger.exception("Qdrant sync failed for %s", city)
    else:
        logger.info("[7/7] Qdrant sync already completed, skipping")
        result.nodes_indexed = progress.nodes_indexed
        result.steps_completed += 1

    # --- Finalize ---
    result.total_duration_s = round(time.monotonic() - t0, 2)
    result.success = result.steps_failed == 0

    progress.overall_status = (
        StepStatus.COMPLETED if result.success else StepStatus.FAILED
    )
    progress.finished_at = datetime.now(timezone.utc).isoformat()
    _save_progress(progress)

    # --- Post-seed validation (runs automatically on every successful seed) ---
    # Validation logs warnings but does NOT block — the canary review is the real gate.
    if result.success:
        try:
            validation = await validate_city_seed(pool, city)
            result.validation = validation
            if validation.passed:
                logger.info(
                    "Post-seed validation PASSED for %s: "
                    "nodes=%d vibe_coverage=%.1f%% max_cat_share=%.1f%%",
                    city,
                    validation.node_count,
                    validation.vibe_coverage_pct,
                    validation.max_category_share * 100,
                )
            else:
                logger.warning(
                    "Post-seed validation FAILED for %s (%d issue(s)): %s",
                    city,
                    len(validation.issues),
                    " | ".join(validation.issues),
                )
        except Exception as exc:
            # Validation failures must never block a completed seed
            logger.warning(
                "Post-seed validation raised an exception for %s (non-fatal): %s",
                city,
                exc,
            )

    logger.info(
        "=== City seed %s: %s | scraped=%d resolved=%d tagged=%d indexed=%d | %.1fs ===",
        city,
        "SUCCESS" if result.success else "FAILED",
        result.nodes_scraped,
        result.nodes_resolved,
        result.nodes_tagged,
        result.nodes_indexed,
        result.total_duration_s,
    )

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """CLI entry point for city seeding."""
    import argparse
    import sys

    # Load .env if python-dotenv is available (dev convenience)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Seed a city with all data sources")
    parser.add_argument("city", help="City name/slug (e.g. tokyo, new-york)")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping step")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM extraction")
    parser.add_argument("--force-restart", action="store_true", help="Ignore existing progress")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    pool = await asyncpg.create_pool(args.database_url)
    try:
        result = await seed_city(
            pool,
            args.city,
            skip_scrape=args.skip_scrape,
            skip_llm=args.skip_llm,
            force_restart=args.force_restart,
        )

        if not result.success:
            logger.error("Seed failed with %d errors: %s", result.steps_failed, result.errors)
            sys.exit(1)

        logger.info("Seed complete: %s", result)
    finally:
        await pool.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
