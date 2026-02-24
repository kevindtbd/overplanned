"""
Nightly training data extraction to Parquet (Phase 4.1).

Extracts BehavioralSignal data from PostgreSQL into Parquet files formatted
for BPR (Bayesian Personalized Ranking) model training. Runs nightly via
cron or Cloud Scheduler.

BPR triplet format: (user_id, positive_item_id, negative_item_id, timestamp)
- Positive: slot_confirm, slot_complete, post_loved, discover_shortlist
- Negative: slot_skip, post_disliked, discover_swipe_left
- Each positive is paired with a random negative from the same user

Filtering:
- Only source='user_behavioral' signals (no synthetic, backfill, chatgpt_import)
- Cold-user quarantine: users with < 3 completed trips are excluded

Idempotency: skips extraction if output file already exists for target date.

Audit: each run is logged to the TrainingExtractRun table.
"""

import logging
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Signal types that count as positive engagement
POSITIVE_SIGNAL_TYPES = frozenset({
    "slot_confirm",
    "slot_complete",
    "post_loved",
    "discover_shortlist",
})

# Signal types that count as negative engagement
NEGATIVE_SIGNAL_TYPES = frozenset({
    "slot_skip",
    "post_disliked",
    "discover_swipe_left",
})

# Minimum completed trips for a user to be included (cold-user quarantine)
MIN_COMPLETED_TRIPS = 3

# Parquet schema for BPR training data
BPR_SCHEMA = pa.schema([
    pa.field("user_id", pa.string()),
    pa.field("pos_item", pa.string()),
    pa.field("neg_item", pa.string()),
    pa.field("timestamp", pa.int64()),
])

# SQL: ensure the audit table exists
_CREATE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "TrainingExtractRun" (
    "id" TEXT PRIMARY KEY,
    "targetDate" DATE NOT NULL,
    "status" TEXT NOT NULL,
    "rowsExtracted" INTEGER NOT NULL DEFAULT 0,
    "filePath" TEXT,
    "durationMs" INTEGER NOT NULL DEFAULT 0,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# SQL: fetch eligible user IDs (users with >= MIN_COMPLETED_TRIPS completed trips)
_ELIGIBLE_USERS_SQL = """
SELECT "userId"
FROM "Trip"
WHERE "status" = 'completed'
GROUP BY "userId"
HAVING COUNT(*) >= $1
"""

# SQL: fetch signals for a target date, filtered by source and eligible users
_SIGNALS_SQL = """
SELECT
    bs."userId",
    bs."activityNodeId",
    bs."signalType",
    EXTRACT(EPOCH FROM bs."createdAt")::BIGINT AS ts
FROM "BehavioralSignal" bs
WHERE bs."source" = 'user_behavioral'
  AND bs."activityNodeId" IS NOT NULL
  AND bs."createdAt" >= $1
  AND bs."createdAt" < $2
  AND bs."userId" = ANY($3)
  AND bs."signalType" = ANY($4)
ORDER BY bs."userId", bs."createdAt"
"""

# SQL: insert audit record
_INSERT_AUDIT_SQL = """
INSERT INTO "TrainingExtractRun" ("id", "targetDate", "status", "rowsExtracted", "filePath", "durationMs", "errorMessage")
VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


@dataclass
class ExtractionResult:
    """Result of a training data extraction run."""
    target_date: date
    status: str  # "success" | "skipped" | "error"
    rows_extracted: int
    file_path: str | None
    duration_ms: int
    error_message: str | None = None


def _output_file_path(output_dir: str, target_date: date) -> str:
    """Build the canonical output file path for a given date."""
    return os.path.join(output_dir, f"bpr_training_{target_date.isoformat()}.parquet")


async def _ensure_audit_table(pool) -> None:
    """Create the TrainingExtractRun audit table if it does not exist."""
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_AUDIT_TABLE_SQL)


async def _get_eligible_user_ids(pool) -> list[str]:
    """Return user IDs with at least MIN_COMPLETED_TRIPS completed trips."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_ELIGIBLE_USERS_SQL, MIN_COMPLETED_TRIPS)
    return [row["userId"] for row in rows]


async def _fetch_signals(
    pool,
    start_ts: datetime,
    end_ts: datetime,
    eligible_user_ids: list[str],
) -> list[dict]:
    """Fetch positive and negative signals for the target date window."""
    all_signal_types = list(POSITIVE_SIGNAL_TYPES | NEGATIVE_SIGNAL_TYPES)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SIGNALS_SQL,
            start_ts,
            end_ts,
            eligible_user_ids,
            all_signal_types,
        )
    return [dict(row) for row in rows]


def _build_bpr_pairs(signals: list[dict]) -> list[dict]:
    """
    Build BPR triplets from raw signals.

    For each user, pair every positive signal with a randomly selected
    negative signal from the same user. Users without both positive and
    negative signals are skipped.
    """
    # Group signals by user
    user_positives: dict[str, list[dict]] = {}
    user_negatives: dict[str, list[dict]] = {}

    for sig in signals:
        uid = sig["userId"]
        if sig["signalType"] in POSITIVE_SIGNAL_TYPES:
            user_positives.setdefault(uid, []).append(sig)
        elif sig["signalType"] in NEGATIVE_SIGNAL_TYPES:
            user_negatives.setdefault(uid, []).append(sig)

    pairs = []
    for uid, positives in user_positives.items():
        negatives = user_negatives.get(uid)
        if not negatives:
            continue
        for pos in positives:
            neg = random.choice(negatives)
            pairs.append({
                "user_id": uid,
                "pos_item": pos["activityNodeId"],
                "neg_item": neg["activityNodeId"],
                "timestamp": pos["ts"],
            })

    return pairs


def _write_parquet(pairs: list[dict], file_path: str) -> int:
    """Write BPR pairs to a Parquet file. Returns file size in bytes."""
    table = pa.table(
        {
            "user_id": [p["user_id"] for p in pairs],
            "pos_item": [p["pos_item"] for p in pairs],
            "neg_item": [p["neg_item"] for p in pairs],
            "timestamp": [p["timestamp"] for p in pairs],
        },
        schema=BPR_SCHEMA,
    )
    # Ensure output directory exists
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    pq.write_table(table, file_path)
    return os.path.getsize(file_path)


async def _log_audit(
    pool,
    run_id: str,
    target_date: date,
    status: str,
    rows: int,
    file_path: str | None,
    duration_ms: int,
    error_msg: str | None,
) -> None:
    """Insert an audit record into TrainingExtractRun."""
    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_AUDIT_SQL,
            run_id,
            target_date,
            status,
            rows,
            file_path,
            duration_ms,
            error_msg,
        )


async def extract_training_data(
    pool,
    output_dir: str,
    target_date: date | None = None,
) -> ExtractionResult:
    """
    Extract BehavioralSignal data into a BPR-ready Parquet file.

    Args:
        pool: asyncpg connection pool.
        output_dir: directory to write Parquet files into.
        target_date: date to extract (default: yesterday UTC).

    Returns:
        ExtractionResult with status, row count, file path, and duration.
    """
    start_time = time.monotonic()
    run_id = str(uuid.uuid4())

    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    file_path = _output_file_path(output_dir, target_date)

    # Idempotency: skip if file already exists
    if os.path.exists(file_path):
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Training extract skipped: file already exists for %s at %s",
            target_date.isoformat(),
            file_path,
        )
        result = ExtractionResult(
            target_date=target_date,
            status="skipped",
            rows_extracted=0,
            file_path=file_path,
            duration_ms=duration_ms,
        )
        await _ensure_audit_table(pool)
        await _log_audit(pool, run_id, target_date, "skipped", 0, file_path, duration_ms, None)
        return result

    try:
        await _ensure_audit_table(pool)

        # Get eligible users (cold-user quarantine)
        eligible_user_ids = await _get_eligible_user_ids(pool)
        if not eligible_user_ids:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("No eligible users found (need >= %d completed trips)", MIN_COMPLETED_TRIPS)
            result = ExtractionResult(
                target_date=target_date,
                status="success",
                rows_extracted=0,
                file_path=None,
                duration_ms=duration_ms,
            )
            await _log_audit(pool, run_id, target_date, "success", 0, None, duration_ms, None)
            return result

        # Build time window for target date (full day in UTC)
        start_ts = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        end_ts = start_ts + timedelta(days=1)

        # Fetch signals
        signals = await _fetch_signals(pool, start_ts, end_ts, eligible_user_ids)

        # Build BPR pairs
        pairs = _build_bpr_pairs(signals)

        if not pairs:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info("No BPR pairs generated for %s (signals: %d)", target_date.isoformat(), len(signals))
            result = ExtractionResult(
                target_date=target_date,
                status="success",
                rows_extracted=0,
                file_path=None,
                duration_ms=duration_ms,
            )
            await _log_audit(pool, run_id, target_date, "success", 0, None, duration_ms, None)
            return result

        # Write to Parquet
        file_size = _write_parquet(pairs, file_path)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            "Training extract complete: %d BPR pairs, %d bytes, %dms for %s",
            len(pairs),
            file_size,
            duration_ms,
            target_date.isoformat(),
        )

        result = ExtractionResult(
            target_date=target_date,
            status="success",
            rows_extracted=len(pairs),
            file_path=file_path,
            duration_ms=duration_ms,
        )
        await _log_audit(pool, run_id, target_date, "success", len(pairs), file_path, duration_ms, None)
        return result

    except Exception as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        error_msg = str(exc)
        logger.exception("Training extract failed for %s: %s", target_date.isoformat(), error_msg)
        result = ExtractionResult(
            target_date=target_date,
            status="error",
            rows_extracted=0,
            file_path=None,
            duration_ms=duration_ms,
            error_message=error_msg,
        )
        try:
            await _log_audit(pool, run_id, target_date, "error", 0, None, duration_ms, error_msg)
        except Exception:
            logger.exception("Failed to log audit record for failed extraction")
        return result
