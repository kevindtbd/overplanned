"""
Tests for extract_client_info() IP resolution logic in audit.py.

Verifies the header priority chain:
  X-Admin-Client-IP > X-Forwarded-For > request.client.host > "unknown"
"""

from unittest.mock import MagicMock

from services.api.middleware.audit import extract_client_info


def _make_request(
    headers: dict[str, str] | None = None,
    client_host: str | None = "127.0.0.1",
) -> MagicMock:
    """Build a mock FastAPI Request with configurable headers and client."""
    req = MagicMock()
    _headers = headers or {}
    req.headers = MagicMock()
    req.headers.get = lambda key, default=None: _headers.get(key, default)

    if client_host is not None:
        req.client = MagicMock()
        req.client.host = client_host
    else:
        req.client = None

    return req


def test_admin_client_ip_header_used():
    """X-Admin-Client-IP header present -- uses that IP (trusted proxy header)."""
    req = _make_request(headers={"X-Admin-Client-IP": "203.0.113.42", "User-Agent": "test-agent"})
    ip, ua = extract_client_info(req)
    assert ip == "203.0.113.42"
    assert ua == "test-agent"


def test_forwarded_for_used_when_admin_header_missing():
    """X-Admin-Client-IP missing, X-Forwarded-For present -- uses first entry."""
    req = _make_request(headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1", "User-Agent": "ua"})
    ip, _ = extract_client_info(req)
    assert ip == "198.51.100.1"


def test_client_host_used_when_both_headers_missing():
    """Both IP headers missing -- falls back to request.client.host."""
    req = _make_request(headers={"User-Agent": "ua"}, client_host="10.20.30.40")
    ip, _ = extract_client_info(req)
    assert ip == "10.20.30.40"


def test_unknown_when_all_missing():
    """All IP sources missing and no client -- returns 'unknown'."""
    req = _make_request(headers={}, client_host=None)
    ip, ua = extract_client_info(req)
    assert ip == "unknown"
    assert ua == "unknown"  # no User-Agent header either


def test_admin_client_ip_takes_priority_over_forwarded_for():
    """X-Admin-Client-IP takes priority over X-Forwarded-For when both present."""
    req = _make_request(
        headers={
            "X-Admin-Client-IP": "203.0.113.42",
            "X-Forwarded-For": "198.51.100.1",
            "User-Agent": "ua",
        },
        client_host="10.0.0.1",
    )
    ip, _ = extract_client_info(req)
    assert ip == "203.0.113.42"
