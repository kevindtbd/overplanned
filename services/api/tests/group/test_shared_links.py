"""
SharedTripToken tests (M-008).

Validates:
- Token creation: correct fields, secure randomness
- View endpoint: increments viewCount
- Expiry: past-expiry tokens rejected
- Revocation: tokens can be revoked, subsequent views rejected
- Rate limiting: too many views within window rejected
- Import tracking: importCount increments on itinerary import
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    make_shared_trip_token,
    make_group_trip,
    make_group_user,
    _make_obj,
    _gen_id,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# SharedTripToken business logic
# ---------------------------------------------------------------------------


class SharedTripTokenService:
    """
    Pure shared trip token logic — no DB layer.
    Mirrors the production service contract.
    """

    GENERIC_REJECTION_CODE = "token_invalid"
    GENERIC_REJECTION_MSG = "This shared trip link is not valid."
    MAX_VIEWS_PER_HOUR = 100

    def create(
        self,
        trip_id: str,
        created_by: str,
        expires_in_days: int = 7,
    ) -> dict:
        """Create a new SharedTripToken."""
        now = datetime.now(timezone.utc)
        return {
            "id": _gen_id(),
            "tripId": trip_id,
            "token": uuid.uuid4().hex,
            "createdBy": created_by,
            "expiresAt": now + timedelta(days=expires_in_days),
            "revokedAt": None,
            "viewCount": 0,
            "importCount": 0,
            "createdAt": now,
        }

    def validate(self, token: dict) -> tuple[bool, str | None]:
        """Validate a token for viewing. Returns (valid, error_code)."""
        now = datetime.now(timezone.utc)

        if token.get("revokedAt") is not None:
            return False, self.GENERIC_REJECTION_CODE

        expires_at = token.get("expiresAt")
        if expires_at and expires_at < now:
            return False, self.GENERIC_REJECTION_CODE

        return True, None

    def record_view(self, token: dict) -> dict:
        """Return updated token with viewCount incremented."""
        return {**token, "viewCount": token.get("viewCount", 0) + 1}

    def record_import(self, token: dict) -> dict:
        """Return updated token with importCount incremented."""
        return {**token, "importCount": token.get("importCount", 0) + 1}

    def revoke(self, token: dict) -> dict:
        """Revoke the token."""
        return {**token, "revokedAt": datetime.now(timezone.utc)}

    def check_rate_limit(self, view_count_in_window: int) -> bool:
        """Returns True if under limit, False if over."""
        return view_count_in_window < self.MAX_VIEWS_PER_HOUR


# ---------------------------------------------------------------------------
# TestSharedTripTokenCreate
# ---------------------------------------------------------------------------


class TestSharedTripTokenCreate:
    """Token creation produces well-formed records."""

    def test_create_has_required_fields(self):
        svc = SharedTripTokenService()
        token = svc.create(trip_id="trip-001", created_by="user-alice")
        assert "id" in token
        assert "token" in token
        assert "tripId" in token
        assert "createdBy" in token
        assert "expiresAt" in token
        assert token["viewCount"] == 0
        assert token["importCount"] == 0
        assert token["revokedAt"] is None

    def test_tokens_are_unique(self):
        svc = SharedTripTokenService()
        tokens = [svc.create("trip-001", "user-alice") for _ in range(10)]
        values = [t["token"] for t in tokens]
        assert len(set(values)) == 10

    def test_token_is_hex_string(self):
        svc = SharedTripTokenService()
        token = svc.create("trip-001", "user-alice")
        assert all(c in "0123456789abcdef" for c in token["token"])

    def test_default_expiry_is_seven_days(self):
        svc = SharedTripTokenService()
        now = datetime.now(timezone.utc)
        token = svc.create("trip-001", "user-alice")
        delta = token["expiresAt"] - now
        assert 6 * 86400 < delta.total_seconds() < 8 * 86400

    def test_custom_expiry_duration(self):
        svc = SharedTripTokenService()
        now = datetime.now(timezone.utc)
        token = svc.create("trip-001", "user-alice", expires_in_days=30)
        delta = token["expiresAt"] - now
        assert 29 * 86400 < delta.total_seconds() < 31 * 86400

    def test_trip_id_bound_correctly(self):
        svc = SharedTripTokenService()
        token = svc.create("trip-specific-999", "user-alice")
        assert token["tripId"] == "trip-specific-999"


# ---------------------------------------------------------------------------
# TestSharedTripTokenView
# ---------------------------------------------------------------------------


class TestSharedTripTokenView:
    """View recording increments counter and validates state."""

    def test_view_increments_view_count(self, valid_shared_token):
        svc = SharedTripTokenService()
        updated = svc.record_view(valid_shared_token)
        assert updated["viewCount"] == valid_shared_token["viewCount"] + 1

    def test_view_does_not_mutate_original(self, valid_shared_token):
        svc = SharedTripTokenService()
        original_count = valid_shared_token["viewCount"]
        svc.record_view(valid_shared_token)
        assert valid_shared_token["viewCount"] == original_count

    def test_multiple_views_accumulate(self, valid_shared_token):
        svc = SharedTripTokenService()
        token = valid_shared_token
        for _ in range(5):
            token = svc.record_view(token)
        assert token["viewCount"] == 5

    def test_valid_token_passes_view_validation(self, valid_shared_token):
        svc = SharedTripTokenService()
        is_valid, err = svc.validate(valid_shared_token)
        assert is_valid is True
        assert err is None


# ---------------------------------------------------------------------------
# TestSharedTripTokenExpiry
# ---------------------------------------------------------------------------


class TestSharedTripTokenExpiry:
    """Expired tokens are rejected with generic error."""

    def test_expired_token_fails_validation(self, expired_shared_token):
        svc = SharedTripTokenService()
        is_valid, err = svc.validate(expired_shared_token)
        assert is_valid is False
        assert err == SharedTripTokenService.GENERIC_REJECTION_CODE

    def test_just_expired_one_second_ago_fails(self):
        svc = SharedTripTokenService()
        token = {
            "tripId": "trip-001",
            "token": "abc",
            "revokedAt": None,
            "expiresAt": datetime.now(timezone.utc) - timedelta(seconds=1),
            "viewCount": 0,
        }
        is_valid, _ = svc.validate(token)
        assert is_valid is False

    def test_expires_in_future_passes(self):
        svc = SharedTripTokenService()
        token = {
            "tripId": "trip-001",
            "token": "abc",
            "revokedAt": None,
            "expiresAt": datetime.now(timezone.utc) + timedelta(seconds=60),
            "viewCount": 0,
        }
        is_valid, _ = svc.validate(token)
        assert is_valid is True


# ---------------------------------------------------------------------------
# TestSharedTripTokenRevoke
# ---------------------------------------------------------------------------


class TestSharedTripTokenRevoke:
    """Revoked tokens are rejected with identical error to expired."""

    def test_revoke_sets_revokedAt(self, valid_shared_token):
        svc = SharedTripTokenService()
        revoked = svc.revoke(valid_shared_token)
        assert revoked["revokedAt"] is not None

    def test_revoked_token_fails_validation(self, valid_shared_token):
        svc = SharedTripTokenService()
        revoked = svc.revoke(valid_shared_token)
        is_valid, err = svc.validate(revoked)
        assert is_valid is False
        assert err == SharedTripTokenService.GENERIC_REJECTION_CODE

    def test_revoke_error_identical_to_expiry_error(
        self, valid_shared_token, expired_shared_token
    ):
        """Both revoked and expired produce same error code."""
        svc = SharedTripTokenService()
        revoked = svc.revoke(valid_shared_token)
        _, err_revoked = svc.validate(revoked)
        _, err_expired = svc.validate(expired_shared_token)
        assert err_revoked == err_expired

    def test_revoke_does_not_mutate_original(self, valid_shared_token):
        svc = SharedTripTokenService()
        svc.revoke(valid_shared_token)
        assert valid_shared_token["revokedAt"] is None

    def test_already_revoked_token_stays_invalid(self, revoked_shared_token):
        svc = SharedTripTokenService()
        is_valid, _ = svc.validate(revoked_shared_token)
        assert is_valid is False


# ---------------------------------------------------------------------------
# TestRateLimiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Rate limiting on shared link views."""

    def test_under_limit_allowed(self):
        svc = SharedTripTokenService()
        assert svc.check_rate_limit(0) is True
        assert svc.check_rate_limit(50) is True
        assert svc.check_rate_limit(99) is True

    def test_at_exact_limit_rejected(self):
        svc = SharedTripTokenService()
        assert svc.check_rate_limit(100) is False

    def test_over_limit_rejected(self):
        svc = SharedTripTokenService()
        assert svc.check_rate_limit(500) is False

    def test_max_views_constant_is_reasonable(self):
        """The rate limit constant should be between 10 and 1000."""
        assert 10 <= SharedTripTokenService.MAX_VIEWS_PER_HOUR <= 1000


# ---------------------------------------------------------------------------
# TestImportTracking
# ---------------------------------------------------------------------------


class TestImportTracking:
    """importCount tracks when users import a shared trip."""

    def test_import_increments_import_count(self, valid_shared_token):
        svc = SharedTripTokenService()
        updated = svc.record_import(valid_shared_token)
        assert updated["importCount"] == valid_shared_token["importCount"] + 1

    def test_multiple_imports_accumulate(self, valid_shared_token):
        svc = SharedTripTokenService()
        token = valid_shared_token
        for _ in range(3):
            token = svc.record_import(token)
        assert token["importCount"] == 3

    def test_import_does_not_affect_view_count(self, valid_shared_token):
        svc = SharedTripTokenService()
        initial_views = valid_shared_token["viewCount"]
        updated = svc.record_import(valid_shared_token)
        assert updated["viewCount"] == initial_views

    def test_import_does_not_mutate_original(self, valid_shared_token):
        svc = SharedTripTokenService()
        original_count = valid_shared_token["importCount"]
        svc.record_import(valid_shared_token)
        assert valid_shared_token["importCount"] == original_count
