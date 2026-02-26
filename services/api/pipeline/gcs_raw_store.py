"""
Persist raw signal and geocoded venue data to GCS for the off-riff city
graduation pipeline.

Path conventions:
  raw_places/{city_slug}.jsonl        -- QualitySignal excerpts (append-only)
  geocoded_venues/{city_slug}.jsonl   -- Geocoded ExtractedVenue records

JSONL format: one JSON object per line, UTF-8, newline-delimited.

Append semantics: GCS does not support true append. Each write reads the
existing blob content, appends new lines, and re-uploads the merged result.
Concurrent writers for the same city slug are unlikely in this pipeline
(fallback seeder runs are city-scoped), so this is acceptable.

Graceful degradation: every public function catches all exceptions, logs a
warning, and returns 0. The fallback seeder must never crash due to GCS
being unavailable (local dev, missing credentials, quota exceeded, etc.).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RAW_PREFIX = "raw_places"
_GEO_PREFIX = "geocoded_venues"
RESEARCH_PREFIX = "research_bundles"
VALID_BUNDLE_TYPES = frozenset({"reddit", "blogs", "atlas", "editorial", "places_metadata"})
_PII_PATTERN = re.compile(r"(?:/u/|u/)([A-Za-z0-9_-]+)")


def _blob_path(prefix: str, city_slug: str) -> str:
    return f"{prefix}/{city_slug}.jsonl"


def _encode_jsonl(records: list[dict]) -> bytes:
    """Encode a list of dicts to JSONL bytes (each record on its own line)."""
    lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _decode_jsonl(raw: bytes) -> list[dict]:
    """Decode JSONL bytes back to a list of dicts. Skips blank/invalid lines."""
    results: list[dict] = []
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSONL line: %s", line[:120])
    return results


def _get_client(project_id: str = "") -> Any:
    """
    Return a google.cloud.storage.Client.

    Uses Application Default Credentials on Cloud Run.
    Raises ImportError or google.auth.exceptions.DefaultCredentialsError
    if unavailable — callers catch those.
    """
    from google.cloud import storage  # type: ignore[import-untyped]

    kwargs: dict[str, Any] = {}
    if project_id:
        kwargs["project"] = project_id
    return storage.Client(**kwargs)


async def _append_to_blob(
    bucket_name: str,
    blob_path: str,
    new_records: list[dict],
    project_id: str = "",
) -> int:
    """
    Read existing blob (if present), merge new records, re-upload.

    Returns the number of new records written.
    Always synchronous GCS I/O — wrapped in try/except by callers.
    """
    client = _get_client(project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    existing_content = b""
    if blob.exists():
        existing_content = blob.download_as_bytes()

    new_content = _encode_jsonl(new_records)
    merged = existing_content + new_content

    blob.upload_from_string(merged, content_type="application/x-ndjson")
    return len(new_records)


async def _read_blob(
    bucket_name: str,
    blob_path: str,
    project_id: str = "",
) -> list[dict]:
    """
    Download and decode a JSONL blob. Returns [] if blob does not exist.
    Always synchronous GCS I/O — wrapped in try/except by callers.
    """
    client = _get_client(project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return []

    raw = blob.download_as_bytes()
    return _decode_jsonl(raw)


# ---------------------------------------------------------------------------
# Public API — raw signals
# ---------------------------------------------------------------------------

async def write_raw_signals_to_gcs(
    city_slug: str,
    signals: list[dict],
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> int:
    """
    Write raw QualitySignal excerpts to GCS as JSONL.

    Path: raw_places/{city_slug}.jsonl
    Append-only: subsequent fallback runs for the same city ADD lines to the
    existing file rather than overwriting it.

    Args:
        city_slug:   City identifier (e.g. "bend", "austin").
        signals:     List of signal dicts (id, source_name, raw_excerpt, …).
        bucket_name: GCS bucket name (default "overplanned-raw").
        project_id:  GCP project ID (optional, uses ADC project if empty).

    Returns:
        Number of records written, or 0 on any error (graceful degradation).
    """
    if not signals:
        return 0

    blob_path = _blob_path(_RAW_PREFIX, city_slug)
    try:
        written = await _append_to_blob(bucket_name, blob_path, signals, project_id)
        logger.info(
            "GCS: wrote %d raw signals to gs://%s/%s",
            written, bucket_name, blob_path,
        )
        return written
    except Exception as exc:
        logger.warning(
            "GCS write failed for raw signals (%s) — continuing without GCS: %s",
            city_slug, exc,
        )
        return 0


async def read_raw_signals_from_gcs(
    city_slug: str,
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> list[dict]:
    """
    Read previously persisted raw signals for a city (used by graduation pipeline).

    Path: raw_places/{city_slug}.jsonl

    Returns:
        List of signal dicts, or [] if not found or on any error.
    """
    blob_path = _blob_path(_RAW_PREFIX, city_slug)
    try:
        records = await _read_blob(bucket_name, blob_path, project_id)
        logger.info(
            "GCS: read %d raw signals from gs://%s/%s",
            len(records), bucket_name, blob_path,
        )
        return records
    except Exception as exc:
        logger.warning(
            "GCS read failed for raw signals (%s): %s",
            city_slug, exc,
        )
        return []


# ---------------------------------------------------------------------------
# Public API — geocoded venues
# ---------------------------------------------------------------------------

async def write_geocoded_venues_to_gcs(
    city_slug: str,
    venues: dict[str, Any],
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> int:
    """
    Write geocoded venue data to GCS as JSONL.

    Path: geocoded_venues/{city_slug}.jsonl
    Each line is a JSON object representing one venue keyed by slug.
    The dict values are expected to be ExtractedVenue instances or plain dicts;
    dataclasses are serialized to their __dict__.

    Args:
        city_slug:   City identifier.
        venues:      slug -> ExtractedVenue (or plain dict) mapping.
        bucket_name: GCS bucket name.
        project_id:  GCP project ID (optional).

    Returns:
        Number of records written, or 0 on any error.
    """
    if not venues:
        return 0

    records: list[dict] = []
    for slug, venue in venues.items():
        if hasattr(venue, "__dict__"):
            rec = {"slug": slug, **venue.__dict__}
        else:
            rec = {"slug": slug, **venue}
        records.append(rec)

    blob_path = _blob_path(_GEO_PREFIX, city_slug)
    try:
        written = await _append_to_blob(bucket_name, blob_path, records, project_id)
        logger.info(
            "GCS: wrote %d geocoded venues to gs://%s/%s",
            written, bucket_name, blob_path,
        )
        return written
    except Exception as exc:
        logger.warning(
            "GCS write failed for geocoded venues (%s) — continuing without GCS: %s",
            city_slug, exc,
        )
        return 0


async def read_geocoded_venues_from_gcs(
    city_slug: str,
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> list[dict]:
    """
    Read previously persisted geocoded venues for a city.

    Path: geocoded_venues/{city_slug}.jsonl

    Returns:
        List of venue dicts (with "slug" key), or [] on any error.
    """
    blob_path = _blob_path(_GEO_PREFIX, city_slug)
    try:
        records = await _read_blob(bucket_name, blob_path, project_id)
        logger.info(
            "GCS: read %d geocoded venues from gs://%s/%s",
            len(records), bucket_name, blob_path,
        )
        return records
    except Exception as exc:
        logger.warning(
            "GCS read failed for geocoded venues (%s): %s",
            city_slug, exc,
        )
        return []


# ---------------------------------------------------------------------------
# Public API — research bundles
# ---------------------------------------------------------------------------

def strip_pii(text: str) -> str:
    """Strip Reddit usernames from text before GCS persistence."""
    return _PII_PATTERN.sub("[user]", text)


async def write_research_bundle(
    city_slug: str,
    source_type: str,
    records: list[dict],
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> int:
    """Append research bundle records to GCS. Returns count written, 0 on error."""
    if source_type not in VALID_BUNDLE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of: {VALID_BUNDLE_TYPES}")
    try:
        client = _get_client(project_id)
        bucket = client.bucket(bucket_name)
        blob_path = f"{RESEARCH_PREFIX}/{city_slug}/{source_type}.jsonl"
        blob = bucket.blob(blob_path)

        sanitized = []
        for rec in records:
            clean = dict(rec)
            if "body" in clean and clean["body"]:
                clean["body"] = strip_pii(clean["body"])
            if "title" in clean and clean["title"]:
                clean["title"] = strip_pii(clean["title"])
            sanitized.append(clean)

        new_content = _encode_jsonl(sanitized)
        if blob.exists():
            existing = blob.download_as_bytes()
            merged = existing + new_content
        else:
            merged = new_content
        blob.upload_from_string(merged, content_type="application/x-ndjson")
        return len(sanitized)
    except Exception as exc:
        logger.warning("GCS research bundle write failed for %s/%s (non-fatal): %s",
                       city_slug, source_type, exc)
        return 0


async def read_research_bundle(
    city_slug: str,
    source_type: str,
    bucket_name: str = "overplanned-raw",
    project_id: str = "",
) -> list[dict]:
    """Read research bundle JSONL from GCS. Returns [] on error."""
    try:
        client = _get_client(project_id)
        bucket = client.bucket(bucket_name)
        blob_path = f"{RESEARCH_PREFIX}/{city_slug}/{source_type}.jsonl"
        blob = bucket.blob(blob_path)
        if not blob.exists():
            return []
        content = blob.download_as_bytes().decode("utf-8")
        return [json.loads(line) for line in content.strip().split("\n") if line.strip()]
    except Exception as exc:
        logger.warning("GCS research bundle read failed for %s/%s (non-fatal): %s",
                       city_slug, source_type, exc)
        return []
