"""
Nightly behavioral write-back job.

Updates ActivityNode scoring columns (impression_count, acceptance_count,
behavioral_quality_score) from BehavioralSignal data collected during the
previous calendar day.

Key design decisions:
- Single CTE transaction per day — truly atomic update.
- Laplace smoothing formula: (acceptance + 1) / (impression + 2).
  Mathematically safe for zero-impression nodes and idempotent on re-runs.
- WriteBackRun audit table records every execution attempt.
- Idempotency: if a WriteBackRun with status='success' already exists for
  today, the job exits without touching ActivityNode.
- Only signals with source='user_behavioral' are counted — synthetic /
  seeded signals are excluded.

Entry point:
    async def run_write_back(pool, target_date=None)

target_date defaults to yesterday (UTC).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL — single CTE, all-or-nothing
# ---------------------------------------------------------------------------

_WRITE_BACK_SQL = """
WITH signal_agg AS (
    SELECT
        "activityNodeId",
        COUNT(*) FILTER (
            WHERE "signalType" IN (
                'slot_view',
                'slot_tap',
                'slot_confirm',
                'slot_complete',
                'discover_swipe_right',
                'discover_shortlist'
            )
        ) AS impression_count,
        COUNT(*) FILTER (
            WHERE "signalType" IN (
                'slot_confirm',
                'slot_complete',
                'discover_shortlist',
                'post_loved'
            )
        ) AS acceptance_count
    FROM behavioral_signals
    WHERE "activityNodeId" IS NOT NULL
      AND source = 'user_behavioral'
      AND "createdAt" >= $1
      AND "createdAt" <  $2
    GROUP BY "activityNodeId"
)
UPDATE activity_nodes an
SET
    impression_count         = an.impression_count + sa.impression_count,
    acceptance_count         = an.acceptance_count + sa.acceptance_count,
    behavioral_quality_score = (
        an.acceptance_count + sa.acceptance_count + 1.0
    ) / (
        an.impression_count + sa.impression_count + 2.0
    ),
    "updatedAt" = NOW()
FROM signal_agg sa
WHERE an.id = sa."activityNodeId"
RETURNING an.id
"""

_INSERT_RUN_SQL = """
INSERT INTO write_back_runs ("runDate", status, "rowsUpdated", "durationMs", "createdAt")
VALUES ($1, $2, $3, $4, NOW())
"""

_CHECK_EXISTING_SQL = """
SELECT id FROM write_back_runs
WHERE "runDate" = $1 AND status = 'success'
LIMIT 1
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_write_back(
    pool: Any,
    target_date: date | None = None,
) -> dict[str, Any]:
    """
    Run the nightly behavioral write-back for a given target date.

    Args:
        pool:        asyncpg connection pool.
        target_date: The calendar date whose signals to aggregate.
                     Defaults to yesterday (UTC).

    Returns:
        A result dict::

            {
                "date": "2026-02-23",
                "status": "success" | "skipped" | "error",
                "rows_updated": int,
                "duration_ms": int,
            }
    """
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    date_label = target_date.isoformat()
    logger.info("write_back: starting for date=%s", date_label)

    start_ts = time.monotonic()

    async with pool.acquire() as conn:
        # Idempotency guard
        existing = await conn.fetchrow(_CHECK_EXISTING_SQL, target_date)
        if existing:
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            logger.info(
                "write_back: already succeeded for date=%s, skipping (run_id=%s)",
                date_label,
                existing["id"],
            )
            return {
                "date": date_label,
                "status": "skipped",
                "rows_updated": 0,
                "duration_ms": duration_ms,
            }

        # Window boundaries — full UTC calendar day
        day_start = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=timezone.utc,
        )
        day_end = day_start + timedelta(days=1)

        rows_updated = 0
        status = "error"

        try:
            async with conn.transaction():
                # Execute the CTE update inside the transaction
                updated_rows = await conn.fetch(_WRITE_BACK_SQL, day_start, day_end)
                rows_updated = len(updated_rows)
                status = "success"

                duration_ms = int((time.monotonic() - start_ts) * 1000)

                # Audit log — inside the same transaction so it rolls back on failure
                await conn.execute(
                    _INSERT_RUN_SQL,
                    target_date,
                    status,
                    rows_updated,
                    duration_ms,
                )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            logger.error(
                "write_back: failed for date=%s after %dms: %s",
                date_label,
                duration_ms,
                exc,
                exc_info=True,
            )
            # Attempt to log the failure outside the (already-rolled-back) transaction
            try:
                async with conn.transaction():
                    await conn.execute(
                        _INSERT_RUN_SQL,
                        target_date,
                        "error",
                        0,
                        duration_ms,
                    )
            except Exception:
                logger.warning(
                    "write_back: could not write error audit row for date=%s",
                    date_label,
                )
            raise

    logger.info(
        "write_back: complete date=%s rows_updated=%d duration_ms=%d",
        date_label,
        rows_updated,
        duration_ms,
    )

    return {
        "date": date_label,
        "status": status,
        "rows_updated": rows_updated,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Standalone entry point for running from cron or Cloud Run Job."""
    import asyncpg
    import os

    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    database_url = os.environ["DATABASE_URL"]

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        result = await run_write_back(pool)
        print(f"write_back complete: {result}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
