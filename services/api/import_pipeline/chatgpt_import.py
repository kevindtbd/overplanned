"""
Phase 3.1 — ChatGPT Conversation Import Pipeline.

Accepts a ZIP file containing a ChatGPT data export (conversations.json),
stream-parses the conversations, extracts travel preference signals using
the NLP extractor, and persists them as ImportPreferenceSignal rows linked
to an ImportJob record.

Security hardening applied:
  - ZIP bomb defense: 50MB compressed cap, 500MB decompressed cap
  - Path traversal prevention: rejects .., absolute paths, backslashes
  - Streaming cap: 500 conversations max, 200MB JSON bytes read max
  - PII scrub: phone, email, SSN, credit card patterns stripped before storage
  - HTML-encode source_text before storage
  - source_text capped at 500 chars
  - Per-user rate limit: max 3 imports per hour

Database tables used (raw SQL via asyncpg):
  - ImportJob              — job lifecycle tracking
  - ImportPreferenceSignal — extracted preference signals per job
"""

from __future__ import annotations

import html
import io
import logging
import re
import time
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Any

import ijson

from services.api.nlp.preference_extractor import extract_preferences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_COMPRESSED_BYTES = 50 * 1024 * 1024       # 50 MB
MAX_DECOMPRESSED_BYTES = 500 * 1024 * 1024    # 500 MB
MAX_CONVERSATIONS = 500
MAX_JSON_READ_BYTES = 200 * 1024 * 1024       # 200 MB
MAX_SOURCE_TEXT_CHARS = 500
RATE_LIMIT_IMPORTS_PER_HOUR = 3
RATE_LIMIT_WINDOW_SECONDS = 3600

TRAVEL_KEYWORDS: frozenset[str] = frozenset({
    "trip",
    "travel",
    "vacation",
    "itinerary",
    "flight",
    "hotel",
    "restaurant",
    "visit",
    "explore",
    "destination",
    "abroad",
    "abroad",
    "backpack",
    "hostel",
    "tour",
    "tourism",
    "airport",
    "booking",
    "airbnb",
    "sightseeing",
    "getaway",
    "journey",
    "abroad",
    "wanderlust",
    "city",
    "country",
})

# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Phone numbers (US and international variants)
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # US SSN
    (re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"), "[SSN]"),
    # Credit card numbers (Luhn-range, 13-16 digits with optional separators)
    (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,16}\b"), "[CARD]"),
]


def _scrub_pii(text: str) -> str:
    """Strip PII patterns from text before storage."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# ZIP security validation
# ---------------------------------------------------------------------------

def _validate_zip_entry(info: zipfile.ZipInfo) -> bool:
    """
    Validate a ZipInfo entry for path traversal and size safety.

    Returns True if the entry is safe to read, False otherwise.
    Raises ValueError for rejected entries.
    """
    filename = info.filename

    # Reject backslashes (Windows path separator abuse)
    if "\\" in filename:
        raise ValueError(f"Rejected ZIP entry with backslash: {filename!r}")

    # Reject absolute paths
    if filename.startswith("/"):
        raise ValueError(f"Rejected absolute path in ZIP: {filename!r}")

    # Reject path traversal
    parts = filename.split("/")
    if ".." in parts:
        raise ValueError(f"Rejected path traversal in ZIP entry: {filename!r}")

    # Decompressed size check (per-entry)
    if info.file_size > MAX_DECOMPRESSED_BYTES:
        raise ValueError(
            f"ZIP entry {filename!r} exceeds max decompressed size: "
            f"{info.file_size} > {MAX_DECOMPRESSED_BYTES}"
        )

    return True


# ---------------------------------------------------------------------------
# Conversation extraction
# ---------------------------------------------------------------------------

def _has_travel_keywords(text: str) -> bool:
    """Pre-filter: check if text contains any travel-related keywords."""
    lower = text.lower()
    return any(keyword in lower for keyword in TRAVEL_KEYWORDS)


def _extract_user_messages_from_conversation(conversation: dict) -> list[str]:
    """
    Walk a single conversation object and collect user message text.

    ChatGPT export format:
      conversation = {
        "title": "...",
        "mapping": {
          "<uuid>": {
            "message": {
              "author": {"role": "user"|"assistant"|"system"},
              "content": {"content_type": "text", "parts": ["..."]}
            }
          }
        }
      }
    """
    messages: list[str] = []
    mapping = conversation.get("mapping") or {}
    for node in mapping.values():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not message or not isinstance(message, dict):
            continue
        author = message.get("author") or {}
        if author.get("role") != "user":
            continue
        content = message.get("content") or {}
        content_type = content.get("content_type", "")
        if content_type != "text":
            continue
        parts = content.get("parts") or []
        for part in parts:
            if isinstance(part, str) and part.strip():
                messages.append(part.strip())
    return messages


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

_CREATE_JOB_SQL = """
INSERT INTO "ImportJob" (id, "userId", status, "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4, $4)
RETURNING id
"""

_UPDATE_JOB_STATUS_SQL = """
UPDATE "ImportJob"
SET status = $2, "updatedAt" = $3, "errorMessage" = $4,
    "conversationsFound" = $5, "signalsExtracted" = $6
WHERE id = $1
"""

_RATE_LIMIT_CHECK_SQL = """
SELECT COUNT(*) AS cnt
FROM "ImportJob"
WHERE "userId" = $1
  AND "createdAt" > $2
"""

_INSERT_SIGNAL_SQL = """
INSERT INTO "ImportPreferenceSignal"
  (id, "importJobId", dimension, direction, confidence, "sourceText",
   "piiScrubbed", "createdAt")
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""


async def _check_rate_limit(
    db_pool,
    user_id: str,
) -> bool:
    """
    Return True if user is within rate limit, False if they've exceeded it.

    Checks: max RATE_LIMIT_IMPORTS_PER_HOUR imports per hour.
    """
    window_start = datetime.now(timezone.utc) - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(_RATE_LIMIT_CHECK_SQL, user_id, window_start)
    count = row["cnt"] if row else 0
    return count < RATE_LIMIT_IMPORTS_PER_HOUR


async def _create_import_job(
    db_pool,
    user_id: str,
) -> str:
    """Create an ImportJob row and return its ID."""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        await conn.execute(
            _CREATE_JOB_SQL,
            job_id,
            user_id,
            "processing",
            now,
        )
    return job_id


async def _update_job(
    db_pool,
    job_id: str,
    status: str,
    conversations_processed: int,
    signals_extracted: int,
    error_message: str | None = None,
) -> None:
    """Update an ImportJob row with final status and counters."""
    now = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        await conn.execute(
            _UPDATE_JOB_STATUS_SQL,
            job_id,
            status,
            now,
            error_message,
            conversations_processed,
            signals_extracted,
        )


async def _persist_signals(
    db_pool,
    job_id: str,
    signals_batch: list[dict],
) -> int:
    """Bulk-insert a batch of ImportPreferenceSignal rows. Returns count inserted."""
    if not signals_batch:
        return 0
    now = datetime.now(timezone.utc)
    rows = [
        (
            str(uuid.uuid4()),
            job_id,
            sig["dimension"],
            sig["direction"],
            sig["confidence"],
            sig["source_text"],
            True,   # piiScrubbed — always True since we scrub before storage
            now,
        )
        for sig in signals_batch
    ]
    async with db_pool.acquire() as conn:
        await conn.executemany(_INSERT_SIGNAL_SQL, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def process_chatgpt_import(
    zip_bytes: bytes,
    user_id: str,
    db_pool,
    anthropic_client=None,
) -> dict:
    """
    Process a ChatGPT export ZIP file and extract travel preference signals.

    Security measures applied:
      - ZIP bomb defense (compressed + decompressed size caps)
      - Path traversal prevention
      - Streaming parse with conversation cap
      - PII scrubbing before storage
      - Per-user rate limiting (3 imports/hour)

    Args:
        zip_bytes: Raw bytes of the ZIP file upload.
        user_id: Authenticated user's ID (caller handles auth).
        db_pool: asyncpg connection pool for DB operations.
        anthropic_client: AsyncAnthropic client for NLP LLM pass.
            If None, only rule-based extraction runs.

    Returns:
        {
          "status": "completed" | "failed",
          "job_id": str,
          "signals_extracted": int,
          "conversations_processed": int,
          "error": str | None,
        }
    """
    job_id: str | None = None
    conversations_processed = 0
    signals_extracted = 0

    try:
        # Rate limit check before creating job
        within_limit = await _check_rate_limit(db_pool, user_id)
        if not within_limit:
            return {
                "status": "failed",
                "job_id": None,
                "signals_extracted": 0,
                "conversations_processed": 0,
                "error": f"Rate limit exceeded: max {RATE_LIMIT_IMPORTS_PER_HOUR} imports per hour",
            }

        # Compressed size check
        if len(zip_bytes) > MAX_COMPRESSED_BYTES:
            return {
                "status": "failed",
                "job_id": None,
                "signals_extracted": 0,
                "conversations_processed": 0,
                "error": f"ZIP file exceeds maximum compressed size of {MAX_COMPRESSED_BYTES // (1024*1024)}MB",
            }

        # Create job record
        job_id = await _create_import_job(db_pool, user_id)

        # Open and validate ZIP
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            await _update_job(db_pool, job_id, "failed", 0, 0, str(exc))
            return {
                "status": "failed",
                "job_id": job_id,
                "signals_extracted": 0,
                "conversations_processed": 0,
                "error": "Invalid ZIP file",
            }

        # Find conversations.json entry
        conversations_entry: zipfile.ZipInfo | None = None
        total_decompressed = 0

        with zf:
            for info in zf.infolist():
                try:
                    _validate_zip_entry(info)
                except ValueError as exc:
                    await _update_job(db_pool, job_id, "failed", 0, 0, str(exc))
                    return {
                        "status": "failed",
                        "job_id": job_id,
                        "signals_extracted": 0,
                        "conversations_processed": 0,
                        "error": str(exc),
                    }

                total_decompressed += info.file_size
                if total_decompressed > MAX_DECOMPRESSED_BYTES:
                    err = (
                        f"ZIP total decompressed size exceeds "
                        f"{MAX_DECOMPRESSED_BYTES // (1024*1024)}MB limit"
                    )
                    await _update_job(db_pool, job_id, "failed", 0, 0, err)
                    return {
                        "status": "failed",
                        "job_id": job_id,
                        "signals_extracted": 0,
                        "conversations_processed": 0,
                        "error": err,
                    }

                # Only interested in conversations.json (top-level or nested)
                name = info.filename
                if name == "conversations.json" or name.endswith("/conversations.json"):
                    conversations_entry = info

            if conversations_entry is None:
                err = "No conversations.json found in ZIP"
                await _update_job(db_pool, job_id, "failed", 0, 0, err)
                return {
                    "status": "failed",
                    "job_id": job_id,
                    "signals_extracted": 0,
                    "conversations_processed": 0,
                    "error": err,
                }

            # Stream-parse conversations.json
            signals_batch: list[dict] = []
            bytes_read = 0

            with zf.open(conversations_entry) as raw_stream:
                # Wrap with a byte-counting reader to enforce streaming cap
                class _CappedStream(io.RawIOBase):
                    def __init__(self, inner):
                        self._inner = inner
                        self.total = 0

                    def readinto(self, b):
                        chunk = self._inner.read(len(b))
                        if not chunk:
                            return 0
                        self.total += len(chunk)
                        if self.total > MAX_JSON_READ_BYTES:
                            raise ValueError(
                                f"conversations.json exceeds "
                                f"{MAX_JSON_READ_BYTES // (1024*1024)}MB read limit"
                            )
                        b[:len(chunk)] = chunk
                        return len(chunk)

                    def readable(self):
                        return True

                capped = _CappedStream(raw_stream)
                buffered = io.BufferedReader(capped)

                try:
                    # ijson: parse array items one at a time
                    parser = ijson.items(buffered, "item")
                    for conversation in parser:
                        if conversations_processed >= MAX_CONVERSATIONS:
                            logger.info(
                                "chatgpt_import: hit conversation cap %d for user=%s job=%s",
                                MAX_CONVERSATIONS,
                                user_id,
                                job_id,
                            )
                            break

                        if not isinstance(conversation, dict):
                            continue

                        # Extract user messages
                        user_messages = _extract_user_messages_from_conversation(conversation)
                        if not user_messages:
                            continue

                        # Pre-filter by travel keywords
                        combined_text = " ".join(user_messages)
                        if not _has_travel_keywords(combined_text):
                            continue

                        conversations_processed += 1

                        # Run NLP extraction on each user message
                        for msg_text in user_messages:
                            if not msg_text.strip():
                                continue

                            signals = await extract_preferences(msg_text, anthropic_client)

                            for sig in signals:
                                # PII scrub
                                clean_text = _scrub_pii(sig.source_text)
                                # HTML-encode
                                clean_text = html.escape(clean_text)
                                # Cap length
                                clean_text = clean_text[:MAX_SOURCE_TEXT_CHARS]

                                signals_batch.append(
                                    {
                                        "dimension": sig.dimension,
                                        "direction": sig.direction,
                                        "confidence": float(sig.confidence),
                                        "source_text": clean_text,
                                    }
                                )

                        # Flush batch every 100 signals to avoid large in-memory buffers
                        if len(signals_batch) >= 100:
                            count = await _persist_signals(db_pool, job_id, signals_batch)
                            signals_extracted += count
                            signals_batch = []

                except ValueError as exc:
                    # Streaming cap exceeded
                    err = str(exc)
                    logger.warning(
                        "chatgpt_import: streaming cap exceeded user=%s job=%s: %s",
                        user_id,
                        job_id,
                        err,
                    )
                    # Persist whatever we have so far, then fail
                    if signals_batch:
                        count = await _persist_signals(db_pool, job_id, signals_batch)
                        signals_extracted += count
                        signals_batch = []
                    await _update_job(
                        db_pool, job_id, "failed",
                        conversations_processed, signals_extracted, err,
                    )
                    return {
                        "status": "failed",
                        "job_id": job_id,
                        "signals_extracted": signals_extracted,
                        "conversations_processed": conversations_processed,
                        "error": err,
                    }

        # Flush remaining signals
        if signals_batch:
            count = await _persist_signals(db_pool, job_id, signals_batch)
            signals_extracted += count

        # Update job to completed
        await _update_job(
            db_pool, job_id, "complete",
            conversations_processed, signals_extracted, None,
        )

        logger.info(
            "chatgpt_import: completed user=%s job=%s "
            "conversations_processed=%d signals_extracted=%d",
            user_id,
            job_id,
            conversations_processed,
            signals_extracted,
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "signals_extracted": signals_extracted,
            "conversations_processed": conversations_processed,
            "error": None,
        }

    except Exception as exc:
        logger.exception(
            "chatgpt_import: unhandled error user=%s job=%s: %s",
            user_id,
            job_id,
            str(exc),
        )
        if job_id:
            try:
                await _update_job(
                    db_pool, job_id, "failed",
                    conversations_processed, signals_extracted, str(exc),
                )
            except Exception:
                logger.exception("chatgpt_import: failed to update job status on error")

        return {
            "status": "failed",
            "job_id": job_id,
            "signals_extracted": signals_extracted,
            "conversations_processed": conversations_processed,
            "error": str(exc),
        }
