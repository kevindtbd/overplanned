"""
HMAC-SHA256 verification for admin requests.

Verifies that requests to /admin/* were signed by the Next.js proxy,
not sent directly by a browser or attacker.

Canonical string format: METHOD|normalizedPath|sortedQueryString|timestamp|userId|bodyHash
Must match the TypeScript signer in apps/web/lib/admin/sign-request.ts exactly.
"""

import hashlib
import hmac
import os
import re
import time

from fastapi import HTTPException, Request


# ---------------------------------------------------------------------------
# Path normalization (must match TypeScript signer exactly)
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    """Normalize path: lowercase, collapse //, strip trailing /, reject .."""
    normalized = path.lower()
    # Collapse consecutive slashes
    normalized = re.sub(r"/+", "/", normalized)
    # Strip trailing slash (but keep root /)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    # Reject path traversal
    segments = normalized.split("/")
    if ".." in segments:
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return normalized


# ---------------------------------------------------------------------------
# Query string sorting
# ---------------------------------------------------------------------------

def sort_query_string(query_string: str) -> str:
    """Sort query params alphabetically (must match TypeScript signer)."""
    if not query_string:
        return ""
    params = [p for p in query_string.split("&") if p]
    params.sort()
    return "&".join(params)


# ---------------------------------------------------------------------------
# Body hash
# ---------------------------------------------------------------------------

def compute_body_hash(body: bytes) -> str:
    """SHA-256 hex digest of raw body bytes."""
    return hashlib.sha256(body).hexdigest()


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------

REPLAY_WINDOW_SECONDS = 30


async def verify_admin_hmac(request: Request) -> str:
    """
    Verify HMAC signature on an admin request.

    Reads raw body, verifies signature, timestamp, and body hash.
    Returns the verified actor_id (X-Admin-User-Id).

    Raises HTTPException on any failure.
    """
    secret = os.environ.get("ADMIN_HMAC_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="HMAC secret not configured",
        )

    # Read required headers
    signature = request.headers.get("X-Admin-Signature")
    timestamp_str = request.headers.get("X-Admin-Timestamp")
    user_id = request.headers.get("X-Admin-User-Id")
    body_hash_header = request.headers.get("X-Admin-Body-Hash")

    if not all([signature, timestamp_str, user_id, body_hash_header]):
        raise HTTPException(
            status_code=401,
            detail="Missing required HMAC headers",
        )

    # Validate timestamp format
    try:
        timestamp = int(timestamp_str)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid timestamp format",
        )

    # Check replay window (30 seconds)
    now = int(time.time())
    if abs(now - timestamp) > REPLAY_WINDOW_SECONDS:
        raise HTTPException(
            status_code=401,
            detail="Request timestamp expired",
        )

    # Read raw body BEFORE any JSON parsing
    body = await request.body()

    # Verify body hash
    computed_body_hash = compute_body_hash(body)
    if not hmac.compare_digest(computed_body_hash, body_hash_header):  # type: ignore[arg-type]
        raise HTTPException(
            status_code=401,
            detail="Body hash mismatch",
        )

    # Build canonical string (must match TypeScript signer)
    path = normalize_path(request.url.path)
    query_string = sort_query_string(request.url.query or "")

    canonical = f"{request.method}|{path}|{query_string}|{timestamp}|{user_id}|{computed_body_hash}"

    # Compute expected signature
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Timing-safe comparison
    if not hmac.compare_digest(expected_signature, signature):  # type: ignore[arg-type]
        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )

    return user_id  # type: ignore[return-value]
