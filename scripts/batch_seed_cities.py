#!/usr/bin/env python3
"""
Batch city seeder with download prefetching.

While city N runs steps 2-10 (scrape, LLM, geocode, etc.),
city N+1's reddit download runs in parallel. Cuts batch time ~50%.

Usage:
    PYTHONPATH=. python3 scripts/batch_seed_cities.py [--force] [city1 city2 ...]
"""

import asyncio
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_seed")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_CITIES = [
    # Tier 1 small mountain towns
    "moab", "taos", "telluride", "mammoth-lakes",
    "truckee", "flagstaff", "hood-river", "jackson-hole",
    # Tier 1 mid-size
    "missoula", "bozeman",
    # Re-runs
    "tacoma", "bend",
    # Bigger cities
    "austin", "denver", "nashville", "new-orleans", "portland", "seattle",
    # Handcrafted + deferred
    "mexico-city", "durango",
]


async def prefetch_download(city: str) -> None:
    """Run reddit download for a city independently (no DB needed)."""
    from services.api.pipeline.reddit_download import download_reddit_data

    logger.info("PREFETCH: Starting reddit download for %s", city)
    try:
        stats = await download_reddit_data(city)
        logger.info(
            "PREFETCH: %s done — posts=%d comments=%d (%.0fs)",
            city,
            stats.posts_downloaded,
            stats.comments_downloaded,
            stats.duration_seconds,
        )
    except Exception as exc:
        logger.warning("PREFETCH: %s failed — %s (will retry in pipeline)", city, exc)


async def run_batch(cities: list[str], force: bool = False) -> None:
    import asyncpg
    from services.api.pipeline.city_seeder import seed_city
    from services.api.embedding.service import EmbeddingService

    db_url = os.environ.get("DATABASE_URL", "")
    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
    logger.info("Pool created (min=2, max=5)")

    embedding_service = EmbeddingService()
    logger.info("EmbeddingService initialized (model loads on first use)")

    results = {}
    total = len(cities)
    t0 = time.monotonic()
    prefetch_task: asyncio.Task | None = None

    for i, city in enumerate(cities, 1):
        logger.info("=" * 60)
        logger.info("[%d/%d] Starting %s%s", i, total, city, " (force)" if force else "")
        logger.info("=" * 60)

        # Wait for this city's prefetch if one was started
        if prefetch_task and not prefetch_task.done():
            logger.info("Waiting for prefetch of %s to complete...", city)
            await prefetch_task
        prefetch_task = None

        # Kick off prefetch for NEXT city while this one runs
        if i < total:
            next_city = cities[i]
            prefetch_task = asyncio.create_task(prefetch_download(next_city))

        try:
            result = await seed_city(pool, city, force_restart=force, embedding_service=embedding_service)
            elapsed = time.monotonic() - t0
            results[city] = {
                "status": "ok",
                "steps_completed": result.steps_completed,
                "steps_failed": result.steps_failed,
                "errors": result.errors,
            }
            logger.info(
                "[%d/%d] %s DONE — %d completed, %d failed, %.0fs total elapsed",
                i, total, city, result.steps_completed, result.steps_failed, elapsed,
            )
            if result.errors:
                logger.warning("  Errors: %s", result.errors)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            results[city] = {"status": "error", "error": str(exc)}
            logger.exception(
                "[%d/%d] %s CRASHED after %.0fs total elapsed", i, total, city, elapsed
            )

    # Wait for any trailing prefetch
    if prefetch_task and not prefetch_task.done():
        await prefetch_task

    # Summary
    elapsed = time.monotonic() - t0
    logger.info("=" * 60)
    logger.info("BATCH COMPLETE — %d cities in %.1f minutes", total, elapsed / 60)
    logger.info("=" * 60)
    ok = sum(1 for r in results.values() if r["status"] == "ok" and r.get("steps_failed", 0) == 0)
    partial = sum(1 for r in results.values() if r["status"] == "ok" and r.get("steps_failed", 0) > 0)
    failed = sum(1 for r in results.values() if r["status"] == "error")
    logger.info("  Clean:   %d", ok)
    logger.info("  Partial: %d", partial)
    logger.info("  Failed:  %d", failed)
    for city, r in results.items():
        status = "OK" if r["status"] == "ok" and not r.get("steps_failed") else r["status"].upper()
        extra = ""
        if r.get("errors"):
            extra = f" errors={r['errors']}"
        if r.get("error"):
            extra = f" {r['error'][:80]}"
        logger.info("  %-20s %s%s", city, status, extra)

    await pool.close()
    logger.info("Pool closed.")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    if force:
        args.remove("--force")

    cities = args if args else DEFAULT_CITIES
    asyncio.run(run_batch(cities, force=force))
