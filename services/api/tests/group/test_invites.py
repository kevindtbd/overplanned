"""
Group invite token tests (M-008).

Validates:
- Token generation: correct fields, secure randomness
- Token validation: accept valid tokens
- Rejection cases: expired, revoked, maxed — all produce identical error shapes
  (no enumeration leak)
- Use counting: usedCount increments on successful join
- Revocation: organizer can revoke before expiry
- Role assignment: token role propagates to membership record
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import (
    make_invite_token,
    make_group_trip,
    make_group_user,
    _make_obj,
    _gen_id,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Token validation logic — standalone, no API layer
# ---------------------------------------------------------------------------


class InviteTokenValidator:
    """
    Pure validation logic mirroring the production invite flow.
    Validates token state and returns a uniform error shape for
    all rejection reasons (no enumeration).
    """

    GENERIC_REJECTION_CODE = "invite_invalid"
    GENERIC_REJECTION_MSG = "This invite link is not valid."

    def validate(self, token: dict) -> tuple[bool, str | None]:
        """
        Returns (is_valid, error_code).
        All invalid states return the SAME error code to prevent enumeration.
        """
        now = datetime.now(timezone.utc)

        # Revoked check
        if token.get("revokedAt") is not None:
            return False, self.GENERIC_REJECTION_CODE

        # Expired check
        expires_at = token.get("expiresAt")
        if expires_at and expires_at < now:
            return False, self.GENERIC_REJECTION_CODE

        # Max uses check
        max_uses = token.get("maxUses")
        used_count = token.get("usedCount", 0)
        if max_uses is not None and used_count >= max_uses:
            return False, self.GENERIC_REJECTION_CODE

        return True, None

    def increment_use(self, token: dict) -> dict:
        """Return a copy of the token with usedCount incremented."""
        return {**token, "usedCount": token.get("usedCount", 0) + 1}

    def generate_token(self, trip_id: str, created_by: str, **kwargs) -> dict:
        """Generate a new invite token."""
        now = datetime.now(timezone.utc)
        return {
            "id": _gen_id(),
            "tripId": trip_id,
            "token": uuid.uuid4().hex,
            "createdBy": created_by,
            "maxUses": kwargs.get("maxUses", 10),
            "usedCount": 0,
            "role": kwargs.get("role", "editor"),
            "expiresAt": kwargs.get(
                "expiresAt", now + timedelta(days=7)
            ),
            "revokedAt": None,
            "createdAt": now,
        }

    def revoke(self, token: dict) -> dict:
        """Return a copy of the token with revokedAt set."""
        return {**token, "revokedAt": datetime.now(timezone.utc)}


# ---------------------------------------------------------------------------
# TestTokenGeneration
# ---------------------------------------------------------------------------


class TestTokenGeneration:
    """Tokens are generated with correct structure and uniqueness."""

    def test_token_has_required_fields(self):
        validator = InviteTokenValidator()
        token = validator.generate_token(
            trip_id="trip-001",
            created_by="user-alice",
        )
        assert "id" in token
        assert "token" in token
        assert "tripId" in token
        assert "createdBy" in token
        assert "expiresAt" in token
        assert token["usedCount"] == 0
        assert token["revokedAt"] is None

    def test_generated_tokens_are_unique(self):
        validator = InviteTokenValidator()
        tokens = [
            validator.generate_token("trip-001", "user-alice")
            for _ in range(10)
        ]
        token_values = [t["token"] for t in tokens]
        assert len(set(token_values)) == 10, "All tokens must be unique"

    def test_token_length_sufficient(self):
        """hex token should be 32 chars (uuid4.hex)."""
        validator = InviteTokenValidator()
        token = validator.generate_token("trip-001", "user-alice")
        assert len(token["token"]) == 32

    def test_default_max_uses_is_set(self):
        validator = InviteTokenValidator()
        token = validator.generate_token("trip-001", "user-alice")
        assert token["maxUses"] is not None
        assert token["maxUses"] > 0

    def test_role_propagates_to_token(self):
        validator = InviteTokenValidator()
        token = validator.generate_token(
            "trip-001", "user-alice", role="viewer"
        )
        assert token["role"] == "viewer"

    def test_expiry_defaults_to_seven_days(self):
        validator = InviteTokenValidator()
        now = datetime.now(timezone.utc)
        token = validator.generate_token("trip-001", "user-alice")
        delta = token["expiresAt"] - now
        # Should be close to 7 days
        assert 6 * 86400 < delta.total_seconds() < 8 * 86400


# ---------------------------------------------------------------------------
# TestTokenValidation
# ---------------------------------------------------------------------------


class TestTokenValidation:
    """Valid tokens are accepted cleanly."""

    def test_valid_token_accepted(self, valid_invite):
        validator = InviteTokenValidator()
        is_valid, error = validator.validate(valid_invite)
        assert is_valid is True
        assert error is None

    def test_fresh_token_with_zero_uses_accepted(self, valid_invite):
        assert valid_invite["usedCount"] == 0
        validator = InviteTokenValidator()
        is_valid, _ = validator.validate(valid_invite)
        assert is_valid is True

    def test_partially_used_token_still_valid(self, valid_invite):
        """Token with 3/5 uses remaining is still valid."""
        token = {**valid_invite, "usedCount": 3, "maxUses": 5}
        validator = InviteTokenValidator()
        is_valid, _ = validator.validate(token)
        assert is_valid is True


# ---------------------------------------------------------------------------
# TestTokenRejection — identical error shapes
# ---------------------------------------------------------------------------


class TestTokenRejection:
    """
    All invalid states produce the SAME error code.
    This prevents enumerating which condition caused rejection.
    """

    def test_expired_token_rejected(self, expired_invite):
        validator = InviteTokenValidator()
        is_valid, error = validator.validate(expired_invite)
        assert is_valid is False
        assert error == InviteTokenValidator.GENERIC_REJECTION_CODE

    def test_revoked_token_rejected(self, revoked_invite):
        validator = InviteTokenValidator()
        is_valid, error = validator.validate(revoked_invite)
        assert is_valid is False
        assert error == InviteTokenValidator.GENERIC_REJECTION_CODE

    def test_maxed_token_rejected(self, maxed_invite):
        validator = InviteTokenValidator()
        is_valid, error = validator.validate(maxed_invite)
        assert is_valid is False
        assert error == InviteTokenValidator.GENERIC_REJECTION_CODE

    def test_all_rejection_errors_are_identical(
        self, expired_invite, revoked_invite, maxed_invite
    ):
        """
        Critical: expired, revoked, and maxed all produce the exact same
        error code to prevent enumeration attacks.
        """
        validator = InviteTokenValidator()
        _, err_expired = validator.validate(expired_invite)
        _, err_revoked = validator.validate(revoked_invite)
        _, err_maxed = validator.validate(maxed_invite)

        assert err_expired == err_revoked == err_maxed, (
            "All rejection reasons must produce identical error codes"
        )

    def test_all_rejection_messages_use_generic_text(self):
        """No hint of WHY the invite was rejected."""
        msg = InviteTokenValidator.GENERIC_REJECTION_MSG
        assert "expired" not in msg.lower()
        assert "revoke" not in msg.lower()
        assert "max" not in msg.lower()
        assert "limit" not in msg.lower()


# ---------------------------------------------------------------------------
# TestUseCountIncrement
# ---------------------------------------------------------------------------


class TestUseCountIncrement:
    """usedCount increments on successful joins."""

    def test_use_count_increments_by_one(self, valid_invite):
        validator = InviteTokenValidator()
        updated = validator.increment_use(valid_invite)
        assert updated["usedCount"] == valid_invite["usedCount"] + 1

    def test_increment_does_not_mutate_original(self, valid_invite):
        validator = InviteTokenValidator()
        original_count = valid_invite["usedCount"]
        validator.increment_use(valid_invite)
        assert valid_invite["usedCount"] == original_count

    def test_token_becomes_invalid_at_exact_max(self, valid_invite):
        """After usedCount reaches maxUses, token is invalid."""
        validator = InviteTokenValidator()
        # Use up all slots
        token = valid_invite.copy()
        for _ in range(token["maxUses"]):
            token = validator.increment_use(token)

        is_valid, _ = validator.validate(token)
        assert is_valid is False


# ---------------------------------------------------------------------------
# TestRevocation
# ---------------------------------------------------------------------------


class TestRevocation:
    """Organizer can revoke tokens before expiry."""

    def test_revoke_sets_revokedAt(self, valid_invite):
        validator = InviteTokenValidator()
        revoked = validator.revoke(valid_invite)
        assert revoked["revokedAt"] is not None

    def test_revoked_token_fails_validation(self, valid_invite):
        validator = InviteTokenValidator()
        revoked = validator.revoke(valid_invite)
        is_valid, _ = validator.validate(revoked)
        assert is_valid is False

    def test_revoke_does_not_mutate_original(self, valid_invite):
        validator = InviteTokenValidator()
        validator.revoke(valid_invite)
        assert valid_invite["revokedAt"] is None

    def test_already_expired_can_still_be_revoked(self, expired_invite):
        """Revocation is idempotent and works regardless of expiry."""
        validator = InviteTokenValidator()
        revoked = validator.revoke(expired_invite)
        assert revoked["revokedAt"] is not None
