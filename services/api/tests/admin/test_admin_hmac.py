"""
Tests for HMAC-SHA256 verification middleware (admin_hmac.py).

Validates signature computation, replay window enforcement, header requirements,
body integrity, and cross-language compatibility via shared test vectors.
"""

import hashlib
import hmac as hmac_mod
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.middleware.admin_hmac import (
    REPLAY_WINDOW_SECONDS,
    compute_body_hash,
    normalize_path,
    sort_query_string,
    verify_admin_hmac,
)

# ---------------------------------------------------------------------------
# Shared test vectors (cross-language compatibility)
# ---------------------------------------------------------------------------

VECTORS_PATH = Path(__file__).resolve().parents[4] / "test-vectors" / "admin-hmac-vectors.json"

with open(VECTORS_PATH) as f:
    _raw = json.load(f)
    TEST_VECTORS = _raw["vectors"]

DEFAULT_SECRET = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign(secret: str, method: str, path: str, query: str, ts: int, user_id: str, body: bytes) -> tuple[str, str]:
    """Compute signature and body hash the same way the production code does."""
    body_hash = compute_body_hash(body)
    normalized = normalize_path(path)
    sorted_qs = sort_query_string(query)
    canonical = f"{method}|{normalized}|{sorted_qs}|{ts}|{user_id}|{body_hash}"
    sig = hmac_mod.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig, body_hash


def _make_request(
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock FastAPI Request with the given attributes."""
    req = MagicMock()
    req.method = method

    url = MagicMock()
    url.path = path
    url.query = query
    req.url = url

    # headers behaves like a dict with .get()
    _headers = headers or {}
    req.headers = MagicMock()
    req.headers.get = lambda key, default=None: _headers.get(key, default)

    req.body = AsyncMock(return_value=body)
    return req


def _make_signed_request(
    secret: str,
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
    timestamp: int | None = None,
    user_id: str = "test-user",
    header_overrides: dict[str, str | None] | None = None,
) -> MagicMock:
    """Build a mock request with valid HMAC headers, then apply optional overrides."""
    ts = timestamp if timestamp is not None else int(time.time())
    sig, body_hash = _sign(secret, method, path, query, ts, user_id, body)

    headers: dict[str, str] = {
        "X-Admin-Signature": sig,
        "X-Admin-Timestamp": str(ts),
        "X-Admin-User-Id": user_id,
        "X-Admin-Body-Hash": body_hash,
    }

    if header_overrides:
        for k, v in header_overrides.items():
            if v is None:
                headers.pop(k, None)
            else:
                headers[k] = v

    return _make_request(method, path, query, body, headers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_hmac_secret(monkeypatch):
    """Ensure ADMIN_HMAC_SECRET is set for every test (unless explicitly removed)."""
    monkeypatch.setenv("ADMIN_HMAC_SECRET", DEFAULT_SECRET)


# ---------------------------------------------------------------------------
# Shared test vector verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vector",
    [v for v in TEST_VECTORS if "method" in v],  # skip the method_a/method_b divergence vector
    ids=[v["description"] for v in TEST_VECTORS if "method" in v],
)
async def test_shared_vectors_accepted(vector, monkeypatch):
    """Every shared test vector must be accepted by verify_admin_hmac (timestamp patched)."""
    monkeypatch.setenv("ADMIN_HMAC_SECRET", vector["secret"])

    ts = vector["timestamp"]
    body = vector["body"].encode("utf-8")
    body_hash = vector["expectedBodyHash"]
    sig = vector["expectedSignature"]

    headers = {
        "X-Admin-Signature": sig,
        "X-Admin-Timestamp": str(ts),
        "X-Admin-User-Id": vector["userId"],
        "X-Admin-Body-Hash": body_hash,
    }
    req = _make_request(vector["method"], vector["path"], vector.get("queryString", ""), body, headers)

    # Freeze time to the vector's timestamp so it's within the replay window
    monkeypatch.setattr(time, "time", lambda: float(ts))

    result = await verify_admin_hmac(req)
    assert result == vector["userId"]


@pytest.mark.asyncio
async def test_shared_vector_method_divergence(monkeypatch):
    """The method-divergence vector proves that changing the HTTP method changes the signature."""
    vec = next(v for v in TEST_VECTORS if "method_a" in v)
    monkeypatch.setenv("ADMIN_HMAC_SECRET", vec["secret"])
    assert vec["signature_a"] != vec["signature_b"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_signature_returns_user_id():
    """A properly signed request returns the X-Admin-User-Id string."""
    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users", user_id="usr-42")
    result = await verify_admin_hmac(req)
    assert result == "usr-42"


# ---------------------------------------------------------------------------
# Replay window / timestamp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timestamp_exactly_30s_old_accepted(monkeypatch):
    """A request whose timestamp is exactly REPLAY_WINDOW_SECONDS old is still valid."""
    now = int(time.time())
    ts = now - REPLAY_WINDOW_SECONDS  # exactly 30s ago
    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users", timestamp=ts)
    # Freeze time so abs(now - ts) == 30
    monkeypatch.setattr(time, "time", lambda: float(now))
    result = await verify_admin_hmac(req)
    assert result == "test-user"


@pytest.mark.asyncio
async def test_timestamp_31s_old_rejected(monkeypatch):
    """A request whose timestamp is 31 seconds old must be rejected."""
    from fastapi import HTTPException

    now = int(time.time())
    ts = now - (REPLAY_WINDOW_SECONDS + 1)
    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users", timestamp=ts)
    monkeypatch.setattr(time, "time", lambda: float(now))

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_future_timestamp_beyond_window_rejected(monkeypatch):
    """A timestamp more than 30 seconds in the future is rejected."""
    from fastapi import HTTPException

    now = int(time.time())
    ts = now + REPLAY_WINDOW_SECONDS + 1
    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users", timestamp=ts)
    monkeypatch.setattr(time, "time", lambda: float(now))

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Wrong / tampered signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_signature_rejected():
    """An incorrect signature is rejected with 401."""
    from fastapi import HTTPException

    req = _make_signed_request(
        DEFAULT_SECRET, "GET", "/admin/users",
        header_overrides={"X-Admin-Signature": "deadbeef" * 8},
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_signature_rejected():
    """An empty X-Admin-Signature header is rejected."""
    from fastapi import HTTPException

    req = _make_signed_request(
        DEFAULT_SECRET, "GET", "/admin/users",
        header_overrides={"X-Admin-Signature": ""},
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_non_hex_signature_rejected():
    """A non-hex signature string is rejected with 401."""
    from fastapi import HTTPException

    req = _make_signed_request(
        DEFAULT_SECRET, "GET", "/admin/users",
        header_overrides={"X-Admin-Signature": "not-a-hex-string!@#$%"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Missing individual headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_header", [
    "X-Admin-Signature",
    "X-Admin-Timestamp",
    "X-Admin-User-Id",
    "X-Admin-Body-Hash",
])
async def test_missing_header_rejected(missing_header):
    """Each required header missing individually results in 401."""
    from fastapi import HTTPException

    req = _make_signed_request(
        DEFAULT_SECRET, "GET", "/admin/users",
        header_overrides={missing_header: None},
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401
    assert "missing" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Tampered request components
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tampered_body_rejected():
    """Changing the body after signing must be rejected (body hash mismatch)."""
    from fastapi import HTTPException

    original_body = b'{"action":"promote"}'
    req = _make_signed_request(DEFAULT_SECRET, "POST", "/admin/models", body=original_body)
    # Swap the body to something different
    req.body = AsyncMock(return_value=b'{"action":"delete"}')

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401
    assert "body" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_tampered_path_rejected():
    """Changing the path after signing must be rejected (signature mismatch)."""
    from fastapi import HTTPException

    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users")
    # Swap the path
    req.url.path = "/admin/danger-zone"

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_tampered_method_rejected():
    """Changing the method after signing must be rejected."""
    from fastapi import HTTPException

    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users")
    req.method = "DELETE"

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Missing ADMIN_HMAC_SECRET env var
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_secret_returns_503(monkeypatch):
    """If ADMIN_HMAC_SECRET is not set, the server returns 503."""
    from fastapi import HTTPException

    monkeypatch.delenv("ADMIN_HMAC_SECRET", raising=False)
    req = _make_signed_request(DEFAULT_SECRET, "GET", "/admin/users")

    with pytest.raises(HTTPException) as exc_info:
        await verify_admin_hmac(req)
    assert exc_info.value.status_code == 503
    assert "not configured" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Unicode body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unicode_body_hashing(monkeypatch):
    """Unicode bodies are hashed as UTF-8 bytes, matching the shared vector."""
    vec = next(v for v in TEST_VECTORS if "Unicode" in v["description"])
    monkeypatch.setenv("ADMIN_HMAC_SECRET", vec["secret"])
    monkeypatch.setattr(time, "time", lambda: float(vec["timestamp"]))

    body = vec["body"].encode("utf-8")

    # Verify body hash matches vector
    assert compute_body_hash(body) == vec["expectedBodyHash"]

    headers = {
        "X-Admin-Signature": vec["expectedSignature"],
        "X-Admin-Timestamp": str(vec["timestamp"]),
        "X-Admin-User-Id": vec["userId"],
        "X-Admin-Body-Hash": vec["expectedBodyHash"],
    }
    req = _make_request(vec["method"], vec["path"], "", body, headers)
    result = await verify_admin_hmac(req)
    assert result == vec["userId"]


# ---------------------------------------------------------------------------
# Timing-safe comparison (structural check)
# ---------------------------------------------------------------------------


def test_hmac_compare_digest_used_in_module():
    """Verify that hmac.compare_digest is used in the module (timing-safe comparison)."""
    import inspect
    import services.api.middleware.admin_hmac as mod

    source = inspect.getsource(mod.verify_admin_hmac)
    assert "hmac.compare_digest" in source, (
        "verify_admin_hmac must use hmac.compare_digest for timing-safe comparison"
    )


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


def test_normalize_path_collapses_double_slashes():
    assert normalize_path("/admin//models") == "/admin/models"


def test_normalize_path_strips_trailing_slash():
    assert normalize_path("/admin/users/") == "/admin/users"


def test_normalize_path_lowercases():
    assert normalize_path("/Admin/Users") == "/admin/users"


def test_normalize_path_rejects_traversal():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        normalize_path("/admin/../etc/passwd")
    assert exc_info.value.status_code == 400


def test_sort_query_string_sorts_alphabetically():
    assert sort_query_string("sort=name&city=tokyo&search=ramen") == "city=tokyo&search=ramen&sort=name"


def test_sort_query_string_empty():
    assert sort_query_string("") == ""


def test_compute_body_hash_empty_body():
    """Empty body hash matches the well-known SHA-256 of empty string."""
    assert compute_body_hash(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
