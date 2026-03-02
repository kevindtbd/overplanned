"""
Reddit data auto-download via Arctic Shift API.

Downloads subreddit posts and comments as Parquet files for pipeline
consumption. Designed as step 0 in the city seeding pipeline.

Key features:
  - Chunk-based writes (O(1) per flush, not O(n))
  - Atomic file operations (temp + os.replace)
  - Cursor-based resume on crash/restart
  - File locking for concurrent pipeline safety
  - Circuit breaker + global caps (request count, wall-clock)
  - Per-subreddit dead letter queue
  - Sort=desc (newest first) with backward pagination

Usage:
    stats = await download_reddit_data("missoula")
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from services.api.pipeline.city_configs import get_city_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARCTIC_SHIFT_BASE_URL = "https://arctic-shift.photon-reddit.com"
PAGE_SIZE = 100
REQUEST_DELAY_S = 0.5
DEFAULT_STALE_DAYS = 7
DEFAULT_MAX_ROWS_PER_SUB = 50_000
DEFAULT_CHUNK_SIZE = 500
DEFAULT_MAX_RETRIES = 3
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_MAX_TOTAL_REQUESTS = 5_000
DEFAULT_MAX_DURATION_SECONDS = 600
DEFAULT_AFTER = "2023-01-01"
MAX_BUFFER_BYTES = 50_000_000  # 50MB force-flush guard
MAX_DLQ_ATTEMPTS = 5
USER_AGENT = "overplanned-city-seeder/1.0"
SUBREDDIT_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")

# Parquet column definitions (no author — no PII)
POST_FIELDS = [
    "id", "subreddit", "title", "selftext", "score",
    "created_utc", "permalink", "upvote_ratio", "num_comments",
]
COMMENT_FIELDS = [
    "id", "subreddit", "body", "score",
    "created_utc", "permalink", "link_id", "parent_id",
]

POST_SCHEMA = pa.schema([
    ("id", pa.string()),
    ("subreddit", pa.string()),
    ("title", pa.string()),
    ("selftext", pa.string()),
    ("score", pa.int64()),
    ("created_utc", pa.int64()),
    ("permalink", pa.string()),
    ("upvote_ratio", pa.float64()),
    ("num_comments", pa.int64()),
])

COMMENT_SCHEMA = pa.schema([
    ("id", pa.string()),
    ("subreddit", pa.string()),
    ("body", pa.string()),
    ("score", pa.int64()),
    ("created_utc", pa.int64()),
    ("permalink", pa.string()),
    ("link_id", pa.string()),
    ("parent_id", pa.string()),
])


# ---------------------------------------------------------------------------
# File lock protocol + production impl
# ---------------------------------------------------------------------------


@runtime_checkable
class FileLock(Protocol):
    def try_acquire(self, path: Path) -> bool: ...
    def release(self, path: Path) -> None: ...


class FcntlFileLock:
    """Production file lock using fcntl.flock (single-host only)."""

    def __init__(self):
        self._fds: dict[Path, int] = {}

    def try_acquire(self, path: Path) -> bool:
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fds[path] = fd
            return True
        except OSError:
            os.close(fd)
            return False

    def release(self, path: Path) -> None:
        fd = self._fds.pop(path, None)
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------


@dataclass
class RedditDownloadStats:
    subreddits_checked: int = 0
    subreddits_downloaded: int = 0
    subreddits_skipped_fresh: int = 0
    subreddits_skipped_locked: int = 0
    subreddits_failed: int = 0
    subreddits_resumed: int = 0
    posts_downloaded: int = 0
    comments_downloaded: int = 0
    total_requests: int = 0
    total_bytes_downloaded: int = 0
    total_parquet_bytes: int = 0
    dlq_entries_written: int = 0
    dlq_entries_retried: int = 0
    circuit_breaker_tripped: bool = False
    request_cap_hit: bool = False
    duration_cap_hit: bool = False
    latency_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Subreddit validation
# ---------------------------------------------------------------------------


def _validate_subreddit(name: str) -> bool:
    """Validate subreddit name — alphanumeric + underscore only."""
    if not name:
        return False
    return SUBREDDIT_NAME_RE.match(name) is not None


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _read_cursor(path: Path) -> dict[str, Any] | None:
    """Read cursor JSON. Returns None on missing/corrupt file."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt cursor file %s, ignoring", path)
        return None


def _write_cursor_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write cursor JSON atomically via temp + os.replace."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Chunk helpers
# ---------------------------------------------------------------------------


def _get_schema(content_type: str) -> pa.Schema:
    """Get the Arrow schema for posts or comments."""
    return POST_SCHEMA if content_type == "posts" else COMMENT_SCHEMA


def _get_fields(content_type: str) -> list[str]:
    """Get field names for posts or comments."""
    return POST_FIELDS if content_type == "posts" else COMMENT_FIELDS


def _flush_chunk_atomic(
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    chunk_path: Path,
) -> int:
    """Write rows as a parquet chunk. Returns bytes written."""
    fields = [f.name for f in schema]
    columns: dict[str, list] = {f: [] for f in fields}
    for row in rows:
        for f in fields:
            val = row.get(f)
            columns[f].append(val)

    table = pa.table(columns, schema=schema)
    tmp = chunk_path.with_suffix(".tmp")
    pq.write_table(table, str(tmp))
    os.replace(str(tmp), str(chunk_path))
    return os.path.getsize(str(chunk_path))


def _merge_chunks_streaming(
    chunk_files: list[Path],
    output_path: Path,
    schema: pa.Schema,
) -> int:
    """Merge chunk parquet files into a single output. Returns total rows."""
    if not chunk_files:
        return 0

    tmp = output_path.with_suffix(".parquet.tmp")
    total_rows = 0
    writer = pq.ParquetWriter(str(tmp), schema)
    try:
        for chunk_file in sorted(chunk_files):
            table = pq.read_table(str(chunk_file))
            writer.write_table(table)
            total_rows += len(table)
    finally:
        writer.close()

    os.replace(str(tmp), str(output_path))

    # Clean up chunks
    for cf in chunk_files:
        cf.unlink(missing_ok=True)

    return total_rows


# ---------------------------------------------------------------------------
# DLQ helpers
# ---------------------------------------------------------------------------


def _dlq_dir(output_dir: Path) -> Path:
    """Get the DLQ directory."""
    d = output_dir.parent / "dead_letter"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dlq_path(output_dir: Path, subreddit: str) -> Path:
    return _dlq_dir(output_dir) / f"reddit_download_{subreddit}.jsonl"


def _permanent_dlq_path(output_dir: Path, subreddit: str) -> Path:
    return _dlq_dir(output_dir) / f"reddit_download_{subreddit}_permanent.jsonl"


def _read_dlq(path: Path) -> list[dict[str, Any]]:
    """Read all entries from a DLQ JSONL file."""
    if not path.exists():
        return []
    entries = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt DLQ file %s", path)
    return entries


def _write_dlq_atomic(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write DLQ entries atomically."""
    if not entries:
        # Remove the file if no entries left
        path.unlink(missing_ok=True)
        return
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Per-subreddit download
# ---------------------------------------------------------------------------


async def _download_subreddit_content(
    client: Any,
    sub: str,
    content_type: str,
    *,
    output_dir: Path,
    after: str,
    max_rows: int,
    chunk_size: int,
    max_retries: int,
    stats: RedditDownloadStats,
    max_total_requests: int,
    start_time: float,
    max_duration_seconds: int,
    before_override: int | None = None,
) -> tuple[bool, int | None]:
    """
    Download posts or comments for a single subreddit.

    Returns (success, oldest_utc_seen).
    """
    schema = _get_schema(content_type)
    fields = _get_fields(content_type)
    prefix = f"{sub}_{content_type}"

    cursor_path = output_dir / f"{prefix}.cursor.json"
    output_path = output_dir / f"{prefix}.parquet"

    # Check for existing chunks (orphans without cursor = clean up)
    existing_chunks = sorted(output_dir.glob(f"{prefix}.chunk_*.parquet"))

    # Read cursor for resume
    cursor = _read_cursor(cursor_path)
    chunk_start_num = 0
    rows_so_far = 0
    oldest_utc_seen: int | None = None

    if cursor and existing_chunks:
        # Resume from cursor
        chunk_start_num = cursor.get("chunks_written", 0)
        rows_so_far = cursor.get("rows_flushed", 0)
        oldest_utc_seen = cursor.get("oldest_utc_seen")
        stats.subreddits_resumed += 1
        logger.info(
            "Resuming %s/%s from chunk %d (rows=%d, oldest_utc=%s)",
            sub, content_type, chunk_start_num, rows_so_far, oldest_utc_seen,
        )
    elif cursor and not existing_chunks:
        # Cursor but no chunks — stale, start fresh
        logger.warning("Cursor without chunks for %s/%s, starting fresh", sub, content_type)
        cursor_path.unlink(missing_ok=True)
        oldest_utc_seen = None
    elif existing_chunks and not cursor:
        # Orphan chunks — clean up
        logger.warning("Orphan chunks for %s/%s, cleaning up", sub, content_type)
        for cf in existing_chunks:
            cf.unlink(missing_ok=True)

    # Cross-run resume: if parquet exists and we're re-downloading (stale),
    # read oldest_utc from existing file to extend backward
    if before_override is not None:
        oldest_utc_seen = before_override
    elif oldest_utc_seen is None and output_path.exists():
        try:
            existing_table = pq.read_table(str(output_path), columns=["created_utc"])
            if len(existing_table) > 0:
                min_utc = existing_table.column("created_utc").to_pylist()
                oldest_utc_seen = min(v for v in min_utc if v is not None)
                logger.info(
                    "Cross-run resume for %s/%s: extending from oldest_utc=%d",
                    sub, content_type, oldest_utc_seen,
                )
        except Exception:
            pass

    # Parse after date to epoch
    try:
        after_epoch = int(datetime.strptime(after, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ).timestamp())
    except ValueError:
        after_epoch = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())

    # Pagination
    buffer: list[dict[str, Any]] = []
    buffer_bytes = 0
    chunk_num = chunk_start_num
    total_rows_this_run = rows_so_far
    pages_completed = cursor.get("pages_completed", 0) if cursor else 0

    while total_rows_this_run < max_rows:
        # Check global caps
        if stats.total_requests >= max_total_requests:
            stats.request_cap_hit = True
            logger.info("Request cap hit (%d), stopping", stats.total_requests)
            break
        if time.monotonic() - start_time > max_duration_seconds:
            stats.duration_cap_hit = True
            logger.info("Duration cap hit, stopping")
            break

        # Build URL
        api_type = content_type  # "posts" or "comments"
        params: dict[str, Any] = {
            "subreddit": sub,
            "limit": PAGE_SIZE,
            "sort": "desc",
            "sort_type": "created_utc",
            "after": after_epoch,
        }
        if oldest_utc_seen is not None:
            params["before"] = oldest_utc_seen

        url = f"{ARCTIC_SHIFT_BASE_URL}/api/{api_type}/search"

        # Fetch with retry
        resp = None
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                stats.total_requests += 1
                resp = await client.get(url, params=params)

                if resp.status_code == 200:
                    break
                elif resp.status_code == 404:
                    logger.warning("Subreddit %s not on Arctic Shift (404)", sub)
                    return (True, oldest_utc_seen)  # not a failure
                elif resp.status_code == 400:
                    logger.warning("Bad request for %s: %s", sub, resp.text)
                    return (True, oldest_utc_seen)  # config error, not failure
                elif resp.status_code in (429, 503) or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < max_retries:
                        wait = 2 ** (attempt + 1)
                        logger.info("Retry %d/%d for %s (HTTP %d), waiting %ds",
                                    attempt + 1, max_retries, sub, resp.status_code, wait)
                        await asyncio.sleep(wait)
                        continue
                else:
                    # Other 4xx
                    logger.error("Unexpected HTTP %d for %s", resp.status_code, sub)
                    return (True, oldest_utc_seen)  # not counted as circuit breaker failure

            except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = str(exc)
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.info("Retry %d/%d for %s (%s), waiting %ds",
                                attempt + 1, max_retries, sub, type(exc).__name__, wait)
                    await asyncio.sleep(wait)
                    continue

        if resp is None or resp.status_code != 200:
            # All retries exhausted
            logger.error("Failed to fetch %s/%s after %d retries: %s",
                         sub, content_type, max_retries, last_error)
            # Flush buffer if any
            if buffer:
                chunk_path = output_dir / f"{prefix}.chunk_{chunk_num:04d}.parquet"
                _flush_chunk_atomic(buffer, schema, chunk_path)
                total_rows_this_run += len(buffer)
                chunk_num += 1
                buffer = []
                buffer_bytes = 0
            # Save cursor
            _write_cursor_atomic(cursor_path, {
                "subreddit": sub,
                "content_type": content_type,
                "oldest_utc_seen": oldest_utc_seen,
                "rows_flushed": total_rows_this_run,
                "chunks_written": chunk_num,
                "pages_completed": pages_completed,
                "started_at": cursor.get("started_at") if cursor else datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            return (False, oldest_utc_seen)

        # Parse response
        try:
            body = resp.json()
        except (json.JSONDecodeError, Exception):
            logger.error("Invalid JSON from %s/%s", sub, content_type)
            # Treat as retryable failure for this page
            return (False, oldest_utc_seen)

        items = body.get("data", [])
        if not isinstance(items, list):
            items = []

        if not items:
            # End of results
            break

        stats.total_bytes_downloaded += len(resp.text.encode("utf-8", errors="replace"))

        # Process items
        for item in items:
            if total_rows_this_run >= max_rows:
                break

            # Require id and created_utc
            item_id = item.get("id")
            created_utc = item.get("created_utc")
            if not item_id:
                logger.debug("Skipping item without id in %s/%s", sub, content_type)
                continue
            if created_utc is None:
                logger.debug("Skipping item without created_utc in %s/%s", sub, content_type)
                continue

            # Ensure created_utc is numeric
            try:
                created_utc = int(created_utc)
            except (ValueError, TypeError):
                logger.debug("Skipping item with non-numeric created_utc in %s/%s", sub, content_type)
                continue

            # Track oldest
            if oldest_utc_seen is None or created_utc < oldest_utc_seen:
                oldest_utc_seen = created_utc

            # Build row with only the fields we want
            row: dict[str, Any] = {}
            for f in fields:
                val = item.get(f)
                if f == "created_utc":
                    row[f] = created_utc
                elif f in ("score", "num_comments"):
                    row[f] = int(val) if val is not None else 0
                elif f == "upvote_ratio":
                    row[f] = float(val) if val is not None else 0.0
                else:
                    row[f] = str(val) if val is not None else ""
            buffer.append(row)
            buffer_bytes += sys.getsizeof(row)
            total_rows_this_run += 1

            # Chunk flush
            if len(buffer) >= chunk_size or buffer_bytes >= MAX_BUFFER_BYTES:
                chunk_path = output_dir / f"{prefix}.chunk_{chunk_num:04d}.parquet"
                bytes_written = _flush_chunk_atomic(buffer, schema, chunk_path)
                stats.total_parquet_bytes += bytes_written
                chunk_num += 1
                buffer = []
                buffer_bytes = 0

                # Update cursor
                _write_cursor_atomic(cursor_path, {
                    "subreddit": sub,
                    "content_type": content_type,
                    "oldest_utc_seen": oldest_utc_seen,
                    "rows_flushed": total_rows_this_run,
                    "chunks_written": chunk_num,
                    "pages_completed": pages_completed + 1,
                    "started_at": cursor.get("started_at") if cursor else datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })

        pages_completed += 1

        # Delay between pages
        await asyncio.sleep(REQUEST_DELAY_S)

    # Flush remaining buffer
    if buffer:
        chunk_path = output_dir / f"{prefix}.chunk_{chunk_num:04d}.parquet"
        bytes_written = _flush_chunk_atomic(buffer, schema, chunk_path)
        stats.total_parquet_bytes += bytes_written
        chunk_num += 1

    # Merge all chunks into final parquet
    all_chunks = sorted(output_dir.glob(f"{prefix}.chunk_*.parquet"))
    if all_chunks:
        # If existing parquet exists (cross-run), merge it too
        existing_parquet_chunks = []
        if output_path.exists() and before_override is not None:
            # Rename existing to a temp chunk for merge
            existing_as_chunk = output_dir / f"{prefix}.chunk_existing.parquet"
            os.replace(str(output_path), str(existing_as_chunk))
            existing_parquet_chunks = [existing_as_chunk]

        merge_files = existing_parquet_chunks + list(all_chunks)
        total = _merge_chunks_streaming(merge_files, output_path, schema)
        logger.info("Merged %d rows into %s", total, output_path.name)

    # Clean up cursor and lock file
    cursor_path.unlink(missing_ok=True)

    row_count = total_rows_this_run - (rows_so_far if cursor else 0)
    if content_type == "posts":
        stats.posts_downloaded += row_count
    else:
        stats.comments_downloaded += row_count

    return (True, oldest_utc_seen)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def download_reddit_data(
    city_slug: str,
    *,
    output_dir: Path = Path("data/arctic_shift"),
    stale_days: int = DEFAULT_STALE_DAYS,
    after: str = DEFAULT_AFTER,
    max_rows_per_sub: int = DEFAULT_MAX_ROWS_PER_SUB,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    circuit_breaker_threshold: int = DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    max_total_requests: int = DEFAULT_MAX_TOTAL_REQUESTS,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    http_client: Any | None = None,
    file_lock: FileLock | None = None,
) -> RedditDownloadStats:
    """
    Download Reddit data for a city's configured subreddits.

    Downloads posts and comments from Arctic Shift API, writing Parquet
    files to output_dir. Supports resume, concurrent locking, DLQ, and
    circuit breaker.
    """
    t0 = time.monotonic()
    stats = RedditDownloadStats()

    # Get city config
    config = get_city_config(city_slug)
    subreddits = list(config.subreddits.keys())

    if not subreddits:
        logger.info("No subreddits configured for %s", city_slug)
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    # Ensure output dir exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up lock and client
    lock = file_lock or FcntlFileLock()
    own_client = http_client is None

    if own_client:
        client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
    else:
        client = http_client

    consecutive_failures = 0

    try:
        for sub in subreddits:
            # Validate subreddit name
            if not _validate_subreddit(sub):
                logger.warning("Invalid subreddit name: %r, skipping", sub)
                continue

            stats.subreddits_checked += 1

            # Check circuit breaker
            if stats.circuit_breaker_tripped:
                logger.info("Circuit breaker tripped, skipping %s", sub)
                continue

            # Check global caps
            if stats.total_requests >= max_total_requests:
                stats.request_cap_hit = True
                logger.info("Request cap reached, stopping")
                break
            if time.monotonic() - t0 > max_duration_seconds:
                stats.duration_cap_hit = True
                logger.info("Duration cap reached, stopping")
                break

            # File lock
            lock_path = output_dir / f"{sub}.lock"
            if not lock.try_acquire(lock_path):
                stats.subreddits_skipped_locked += 1
                logger.info("Subreddit %s is locked, skipping", sub)
                continue

            sub_success = True
            try:
                for content_type in ("posts", "comments"):
                    prefix = f"{sub}_{content_type}"
                    parquet_path = output_dir / f"{prefix}.parquet"

                    # Freshness check (INSIDE lock — no TOCTOU)
                    before_override = None
                    if parquet_path.exists():
                        mtime = datetime.fromtimestamp(
                            parquet_path.stat().st_mtime, tz=timezone.utc
                        )
                        age_days = (datetime.now(timezone.utc) - mtime).total_seconds() / 86400
                        if stale_days > 0 and age_days < stale_days:
                            stats.subreddits_skipped_fresh += 1
                            logger.info(
                                "%s is fresh (%.1f days old), skipping",
                                parquet_path.name, age_days,
                            )
                            continue
                        else:
                            # Stale — extend backward
                            try:
                                existing = pq.read_table(str(parquet_path), columns=["created_utc"])
                                if len(existing) > 0:
                                    min_vals = [v for v in existing.column("created_utc").to_pylist() if v is not None]
                                    if min_vals:
                                        before_override = min(min_vals)
                            except Exception:
                                pass

                    success, _ = await _download_subreddit_content(
                        client, sub, content_type,
                        output_dir=output_dir,
                        after=after,
                        max_rows=max_rows_per_sub,
                        chunk_size=chunk_size,
                        max_retries=max_retries,
                        stats=stats,
                        max_total_requests=max_total_requests,
                        start_time=t0,
                        max_duration_seconds=max_duration_seconds,
                        before_override=before_override,
                    )
                    if not success:
                        sub_success = False

                if sub_success:
                    stats.subreddits_downloaded += 1
                    consecutive_failures = 0  # Reset on success
                else:
                    stats.subreddits_failed += 1
                    consecutive_failures += 1

                    # Write DLQ
                    dlq_file = _dlq_path(output_dir, sub)
                    entries = _read_dlq(dlq_file)
                    # Find existing entry for this sub or create new
                    existing_entry = None
                    for e in entries:
                        if e.get("subreddit") == sub:
                            existing_entry = e
                            break

                    now_iso = datetime.now(timezone.utc).isoformat()
                    if existing_entry:
                        existing_entry["attempts"] = existing_entry.get("attempts", 0) + 1
                        existing_entry["last_failed_at"] = now_iso

                        if existing_entry["attempts"] >= MAX_DLQ_ATTEMPTS:
                            # Move to permanent DLQ
                            perm_path = _permanent_dlq_path(output_dir, sub)
                            perm_entries = _read_dlq(perm_path)
                            perm_entries.append(existing_entry)
                            _write_dlq_atomic(perm_path, perm_entries)
                            entries.remove(existing_entry)
                            logger.warning(
                                "Subreddit %s exceeded %d DLQ attempts, moved to permanent DLQ",
                                sub, MAX_DLQ_ATTEMPTS,
                            )
                    else:
                        new_entry = {
                            "subreddit": sub,
                            "content_type": "all",
                            "city_slug": city_slug,
                            "reason": "download failed",
                            "oldest_utc_seen": None,
                            "rows_downloaded": 0,
                            "attempts": 1,
                            "first_failed_at": now_iso,
                            "last_failed_at": now_iso,
                        }
                        entries.append(new_entry)

                    _write_dlq_atomic(dlq_file, entries)
                    stats.dlq_entries_written += 1

                    # Circuit breaker check
                    if consecutive_failures >= circuit_breaker_threshold:
                        stats.circuit_breaker_tripped = True
                        logger.warning(
                            "Circuit breaker tripped after %d consecutive failures",
                            consecutive_failures,
                        )

            finally:
                lock.release(lock_path)
                # Clean up lock file on success
                if sub_success:
                    lock_path.unlink(missing_ok=True)

    finally:
        if own_client:
            await client.aclose()

    stats.latency_seconds = round(time.monotonic() - t0, 2)
    logger.info(
        "Reddit download for %s: checked=%d downloaded=%d fresh=%d locked=%d failed=%d "
        "posts=%d comments=%d requests=%d %.1fs",
        city_slug,
        stats.subreddits_checked,
        stats.subreddits_downloaded,
        stats.subreddits_skipped_fresh,
        stats.subreddits_skipped_locked,
        stats.subreddits_failed,
        stats.posts_downloaded,
        stats.comments_downloaded,
        stats.total_requests,
        stats.latency_seconds,
    )
    return stats
