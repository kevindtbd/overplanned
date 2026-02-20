"""
Scheduled content purge for Reddit raw excerpts (compliance).

Reddit's content policy requires that cached/scraped content not be retained
indefinitely. This job nulls out raw_excerpt on QualitySignal rows sourced
from Reddit (arctic_shift, reddit) after a configurable retention window
(default 30 days).

All derived data (vibe tags, convergence scores, authority scores, entity
resolution results) is preserved — only the verbatim excerpt text is removed.

Usage:
    # As a standalone cron job:
    python -m services.api.pipeline.content_purge

    # Programmatic:
    pool = await asyncpg.create_pool(DATABASE_URL)
    result = await purge_expired_excerpts(pool)
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)

# Reddit-adjacent source names used by our scrapers
REDDIT_SOURCES = frozenset({"arctic_shift", "reddit"})

# Default retention: 30 days
DEFAULT_RETENTION_DAYS = 30

# Process in batches to avoid long-running transactions
BATCH_SIZE = 500


@dataclass
class PurgeResult:
    """Result of a content purge run."""
    rows_purged: int
    rows_already_null: int
    batches_run: int
    duration_s: float
    cutoff_date: str
    errors: list[str]


async def purge_expired_excerpts(
    pool: asyncpg.Pool,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    batch_size: int = BATCH_SIZE,
    dry_run: bool = False,
) -> PurgeResult:
    """
    Null out raw_excerpt on Reddit-sourced QualitySignal rows older than
    the retention window.

    Args:
        pool: asyncpg connection pool.
        retention_days: Number of days to retain raw excerpts (default 30).
        batch_size: Rows per batch update (default 500).
        dry_run: If True, count but don't modify rows.

    Returns:
        PurgeResult with stats on what was purged.
    """
    t0 = time.monotonic()
    cutoff = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []

    # Build the source list for the SQL IN clause
    source_list = list(REDDIT_SOURCES)

    async with pool.acquire() as conn:
        # Count how many are already null (for reporting)
        already_null = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM "QualitySignal"
            WHERE "sourceName" = ANY($1::text[])
              AND "extractedAt" < (NOW() - make_interval(days => $2))
              AND "rawExcerpt" IS NULL
            """,
            source_list,
            retention_days,
        )

        if dry_run:
            eligible = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM "QualitySignal"
                WHERE "sourceName" = ANY($1::text[])
                  AND "extractedAt" < (NOW() - make_interval(days => $2))
                  AND "rawExcerpt" IS NOT NULL
                """,
                source_list,
                retention_days,
            )
            logger.info(
                "[DRY RUN] Would purge %d rows (cutoff=%dd, already_null=%d)",
                eligible,
                retention_days,
                already_null,
            )
            return PurgeResult(
                rows_purged=0,
                rows_already_null=already_null or 0,
                batches_run=0,
                duration_s=round(time.monotonic() - t0, 2),
                cutoff_date=cutoff,
                errors=errors,
            )

        # Batch loop: update up to batch_size rows per iteration
        total_purged = 0
        batches = 0

        while True:
            try:
                result = await conn.execute(
                    """
                    UPDATE "QualitySignal"
                    SET "rawExcerpt" = NULL
                    WHERE id IN (
                        SELECT id FROM "QualitySignal"
                        WHERE "sourceName" = ANY($1::text[])
                          AND "extractedAt" < (NOW() - make_interval(days => $2))
                          AND "rawExcerpt" IS NOT NULL
                        LIMIT $3
                    )
                    """,
                    source_list,
                    retention_days,
                    batch_size,
                )
                # asyncpg returns "UPDATE N"
                affected = int(result.split()[-1])
                total_purged += affected
                batches += 1

                if affected < batch_size:
                    break

                logger.debug("Purged batch %d (%d rows)", batches, affected)

            except Exception as exc:
                errors.append(f"batch {batches + 1}: {exc}")
                logger.exception("Purge batch %d failed", batches + 1)
                break

    duration = round(time.monotonic() - t0, 2)

    logger.info(
        "Content purge complete: purged=%d already_null=%d batches=%d duration=%.1fs",
        total_purged,
        already_null or 0,
        batches,
        duration,
    )

    return PurgeResult(
        rows_purged=total_purged,
        rows_already_null=already_null or 0,
        batches_run=batches,
        duration_s=duration,
        cutoff_date=cutoff,
        errors=errors,
    )


async def main() -> None:
    """CLI entry point for content purge."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Purge expired Reddit raw excerpts for compliance"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Days to retain raw excerpts (default {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Rows per batch (default {BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count eligible rows without modifying",
    )
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
        result = await purge_expired_excerpts(
            pool,
            retention_days=args.retention_days,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )

        if result.errors:
            logger.warning("Purge completed with %d errors", len(result.errors))
            sys.exit(1)

        logger.info("Purge result: %s", result)
    finally:
        await pool.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
