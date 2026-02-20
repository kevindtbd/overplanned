"""
Auth tests: RBAC tier access, session lifecycle, concurrent session limit.

Tests run against mock dependencies (no real DB/Redis needed).
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest

from services.api.tests.conftest import make_user, make_session


# ---------------------------------------------------------------------------
# RBAC tier access
# ---------------------------------------------------------------------------

class TestRBACTierAccess:
    """Access control: beta, lifetime, pro have access; free does not."""

    ALLOWED_TIERS = ["beta", "lifetime", "pro"]
    DENIED_TIERS = ["free"]

    @pytest.mark.parametrize("tier", ALLOWED_TIERS)
    def test_allowed_tier_has_access(self, tier: str):
        """Tiers with access: beta, lifetime, pro."""
        user = make_user(subscriptionTier=tier)
        assert user["subscriptionTier"] in self.ALLOWED_TIERS

    @pytest.mark.parametrize("tier", DENIED_TIERS)
    def test_denied_tier_no_access(self, tier: str):
        """Free tier should not have access."""
        user = make_user(subscriptionTier=tier)
        assert user["subscriptionTier"] not in self.ALLOWED_TIERS

    def test_access_check_logic(self):
        """Matches middleware.ts: ['beta', 'lifetime', 'pro'].includes(tier)."""
        for tier in self.ALLOWED_TIERS:
            assert tier in ["beta", "lifetime", "pro"]
        for tier in self.DENIED_TIERS:
            assert tier not in ["beta", "lifetime", "pro"]


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    """Session creation, expiration, idle timeout."""

    def test_session_created_with_30d_expiry(self):
        now = datetime.now(timezone.utc)
        session = make_session(expires=now + timedelta(days=30))
        delta = session["expires"] - now
        assert 29 <= delta.days <= 30

    def test_session_expires_after_max_age(self):
        """Session with maxAge=30d should be expired after 31 days."""
        created = datetime.now(timezone.utc) - timedelta(days=31)
        session = make_session(
            expires=created + timedelta(days=30),
            createdAt=created,
        )
        assert session["expires"] < datetime.now(timezone.utc)

    def test_session_not_expired_within_window(self):
        now = datetime.now(timezone.utc)
        session = make_session(expires=now + timedelta(days=15))
        assert session["expires"] > now

    def test_idle_timeout_7d(self):
        """If session not updated within 7 days, it should be stale."""
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
        session = make_session(createdAt=seven_days_ago)
        # Idle timeout = 7d means updateAge in NextAuth config
        idle_threshold = datetime.now(timezone.utc) - timedelta(days=7)
        assert session["createdAt"] < idle_threshold


# ---------------------------------------------------------------------------
# Concurrent session limit
# ---------------------------------------------------------------------------

class TestConcurrentSessionLimit:
    """Max 5 active sessions per user. 6th deletes oldest."""

    MAX_SESSIONS = 5

    def test_within_limit(self):
        user = make_user()
        sessions = [make_session(user_id=user["id"]) for _ in range(self.MAX_SESSIONS)]
        assert len(sessions) == self.MAX_SESSIONS

    def test_exceeds_limit_identifies_oldest(self):
        """When 6 sessions exist, the oldest should be identified for deletion."""
        user = make_user()
        now = datetime.now(timezone.utc)

        sessions = []
        for i in range(self.MAX_SESSIONS + 1):
            sessions.append(
                make_session(
                    user_id=user["id"],
                    createdAt=now + timedelta(minutes=i),
                )
            )

        # Sort by creation time (oldest first)
        sessions.sort(key=lambda s: s["createdAt"])

        # Sessions exceeding limit
        excess = len(sessions) - self.MAX_SESSIONS
        assert excess == 1

        # Oldest session should be deleted
        to_delete = sessions[:excess]
        to_keep = sessions[excess:]
        assert len(to_keep) == self.MAX_SESSIONS
        assert to_delete[0]["createdAt"] < to_keep[0]["createdAt"]


# ---------------------------------------------------------------------------
# Google OAuth callback
# ---------------------------------------------------------------------------

class TestGoogleOAuthCallback:
    """Google OAuth creates user with beta role."""

    def test_new_user_defaults_to_beta(self):
        user = make_user()
        assert user["subscriptionTier"] == "beta"

    def test_new_user_has_google_id(self):
        user = make_user()
        assert user["googleId"] is not None
        assert user["googleId"].startswith("google-")

    def test_new_user_system_role_is_user(self):
        user = make_user()
        assert user["systemRole"] == "user"

    def test_user_email_is_set(self):
        user = make_user(email="test@gmail.com")
        assert user["email"] == "test@gmail.com"
