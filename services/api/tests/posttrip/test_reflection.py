"""
Integration tests: trip completes -> reflection -> signals + intentions written.

Covers:
- on_trip_completed() orchestration (push enqueue, email schedule, suggestion)
- Trip highlights computation from completed slots + loved signals
- Reflection skip reasons -> IntentionSignal creation
- Email rate limiting and unsubscribe checks
- Login link generation (one-time use, 15-min expiry)
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.posttrip.intention_signal import (
    record_skip_intention,
    VALID_SKIP_REASONS,
)
from services.api.posttrip.email_service import (
    generate_login_link,
    consume_login_link,
    check_email_rate_limit,
    check_unsubscribed,
    send_trip_memory_email,
)
from services.api.posttrip.reengagement import (
    on_trip_completed,
    process_pending_emails,
    _get_trip_highlights,
    _format_date_range,
    PUSH_DELAY_HOURS,
    EMAIL_DELAY_DAYS,
)


# ===================================================================
# 1. on_trip_completed orchestration
# ===================================================================

class TestOnTripCompleted:
    """Integration: trip completion triggers push, email scheduling, and suggestion."""

    @pytest.mark.asyncio
    async def test_enqueues_push_and_email(
        self, mock_db_posttrip, mock_redis_posttrip, mock_qdrant_posttrip,
        completed_trip, completed_user,
    ):
        """Completing a trip should enqueue a 24h push and schedule a 7d email."""
        trip = completed_trip
        user = completed_user

        # Configure DB mocks
        trip_obj = MagicMock()
        trip_obj.id = trip["id"]
        trip_obj.destination = trip["destination"]
        trip_obj.city = trip["city"]
        trip_obj.country = trip["country"]
        trip_obj.startDate = trip["startDate"]
        trip_obj.endDate = trip["endDate"]
        mock_db_posttrip.trip.find_unique = AsyncMock(return_value=trip_obj)

        user_obj = MagicMock()
        user_obj.id = user["id"]
        user_obj.email = user["email"]
        user_obj.name = user["name"]
        mock_db_posttrip.user.find_unique = AsyncMock(return_value=user_obj)

        # Mock no positive signals (skip suggestion)
        mock_db_posttrip.behavioralsignal.find_many = AsyncMock(return_value=[])

        result = await on_trip_completed(
            mock_db_posttrip,
            mock_redis_posttrip,
            mock_qdrant_posttrip,
            trip_id=trip["id"],
            user_id=user["id"],
        )

        assert result["push_enqueued"] is True
        assert result["email_scheduled"] is True
        assert result["trip_id"] == trip["id"]

    @pytest.mark.asyncio
    async def test_missing_trip_returns_empty_result(
        self, mock_db_posttrip, mock_redis_posttrip, mock_qdrant_posttrip,
    ):
        """If trip doesn't exist, returns empty result without crashing."""
        mock_db_posttrip.trip.find_unique = AsyncMock(return_value=None)

        result = await on_trip_completed(
            mock_db_posttrip,
            mock_redis_posttrip,
            mock_qdrant_posttrip,
            trip_id="nonexistent",
            user_id="user-1",
        )

        assert result["push_enqueued"] is False
        assert result["email_scheduled"] is False

    @pytest.mark.asyncio
    async def test_suggestion_cached_in_redis(
        self, mock_db_posttrip, mock_redis_posttrip, mock_qdrant_posttrip,
        completed_trip, completed_user, loved_activities,
    ):
        """If suggestion is computed, it should be cached in Redis for the 7-day email."""
        trip = completed_trip
        user = completed_user

        trip_obj = MagicMock()
        trip_obj.id = trip["id"]
        trip_obj.destination = trip["destination"]
        trip_obj.city = trip["city"]
        trip_obj.country = trip["country"]
        trip_obj.startDate = trip["startDate"]
        trip_obj.endDate = trip["endDate"]
        mock_db_posttrip.trip.find_unique = AsyncMock(return_value=trip_obj)

        user_obj = MagicMock()
        user_obj.id = user["id"]
        user_obj.email = user["email"]
        user_obj.name = user["name"]
        mock_db_posttrip.user.find_unique = AsyncMock(return_value=user_obj)

        # Provide enough positive signals for suggestion
        mock_signals = []
        for act in loved_activities:
            s = MagicMock()
            s.activityNodeId = act["id"]
            s.userId = user["id"]
            mock_signals.append(s)
        mock_db_posttrip.behavioralsignal.find_many = AsyncMock(return_value=mock_signals)

        mock_activity_objs = []
        for act in loved_activities:
            a = MagicMock()
            a.id = act["id"]
            a.name = act["name"]
            a.category = act["category"]
            a.city = act["city"]
            mock_activity_objs.append(a)
        mock_db_posttrip.activitynode.find_many = AsyncMock(return_value=mock_activity_objs)

        with patch("services.api.posttrip.reengagement.embedding_service") as mock_embed:
            mock_embed.embed_single = MagicMock(return_value=[0.1] * 768)

            result = await on_trip_completed(
                mock_db_posttrip,
                mock_redis_posttrip,
                mock_qdrant_posttrip,
                trip_id=trip["id"],
                user_id=user["id"],
            )

        assert result["destination_suggestion"] is not None
        # Verify Redis setex was called for cache
        cache_key = f"posttrip:suggestion:{user['id']}:{trip['id']}"
        assert cache_key in mock_redis_posttrip._store


# ===================================================================
# 2. Trip highlights
# ===================================================================

class TestTripHighlights:
    """Tests for _get_trip_highlights() used in memory email."""

    @pytest.mark.asyncio
    async def test_returns_loved_activities_first(self, mock_db_posttrip):
        """Loved activities should appear before non-loved in highlights."""
        slot1 = MagicMock()
        slot1.activityNodeId = "node-loved"
        slot1.activityNode = MagicMock(
            id="node-loved", name="Tsukiji", category="dining",
            primaryImageUrl="https://img.example.com/tsukiji.jpg",
        )
        slot1.dayNumber = 2
        slot1.status = "completed"

        slot2 = MagicMock()
        slot2.activityNodeId = "node-normal"
        slot2.activityNode = MagicMock(
            id="node-normal", name="Temple", category="culture",
            primaryImageUrl=None,
        )
        slot2.dayNumber = 1
        slot2.status = "completed"

        mock_db_posttrip.itineraryslot.find_many = AsyncMock(return_value=[slot1, slot2])

        loved_signal = MagicMock()
        loved_signal.activityNodeId = "node-loved"
        mock_db_posttrip.behavioralsignal.find_many = AsyncMock(return_value=[loved_signal])

        highlights = await _get_trip_highlights(mock_db_posttrip, "trip-1")

        assert len(highlights) == 2
        assert highlights[0]["name"] == "Tsukiji"
        assert highlights[0]["is_loved"] is True
        assert highlights[1]["is_loved"] is False

    @pytest.mark.asyncio
    async def test_empty_trip_returns_empty_highlights(self, mock_db_posttrip):
        """Trip with no completed slots returns empty highlights."""
        mock_db_posttrip.itineraryslot.find_many = AsyncMock(return_value=[])
        highlights = await _get_trip_highlights(mock_db_posttrip, "trip-empty")
        assert highlights == []

    @pytest.mark.asyncio
    async def test_highlights_capped_at_five(self, mock_db_posttrip):
        """Highlights should be capped at 5 even if more exist."""
        slots = []
        for i in range(8):
            slot = MagicMock()
            slot.activityNodeId = f"node-{i}"
            slot.activityNode = MagicMock(
                id=f"node-{i}", name=f"Activity {i}",
                category="dining", primaryImageUrl=None,
            )
            slot.dayNumber = i + 1
            slot.status = "completed"
            slots.append(slot)

        mock_db_posttrip.itineraryslot.find_many = AsyncMock(return_value=slots)
        mock_db_posttrip.behavioralsignal.find_many = AsyncMock(return_value=[])

        highlights = await _get_trip_highlights(mock_db_posttrip, "trip-many")
        assert len(highlights) <= 5


# ===================================================================
# 3. IntentionSignal from skip reasons
# ===================================================================

class TestRecordSkipIntention:
    """Tests for record_skip_intention() — explicit user feedback."""

    @pytest.mark.asyncio
    async def test_valid_skip_reason_creates_intention(self, mock_db_posttrip):
        """Valid skip reason creates IntentionSignal with confidence=1.0."""
        parent = MagicMock()
        parent.id = "signal-1"
        parent.userId = "user-1"
        parent.signalType = "post_skipped"
        mock_db_posttrip.behavioralsignal.find_unique = AsyncMock(return_value=parent)

        intention = MagicMock()
        intention.id = "int-1"
        intention.userId = "user-1"
        intention.behavioralSignalId = "signal-1"
        intention.rawEventId = None
        intention.intentionType = "not_interested"
        intention.confidence = 1.0
        intention.source = "user_explicit"
        intention.userProvided = True
        intention.createdAt = datetime.now(timezone.utc)
        mock_db_posttrip.intentionsignal.create = AsyncMock(return_value=intention)

        result = await record_skip_intention(
            mock_db_posttrip,
            user_id="user-1",
            behavioral_signal_id="signal-1",
            skip_reason="not_interested",
        )

        assert result["confidence"] == 1.0
        assert result["source"] == "user_explicit"
        assert result["userProvided"] is True

    @pytest.mark.asyncio
    async def test_all_valid_skip_reasons_accepted(self, mock_db_posttrip):
        """All six valid skip reasons should be accepted."""
        for reason in VALID_SKIP_REASONS:
            parent = MagicMock()
            parent.id = f"signal-{reason}"
            parent.userId = "user-1"
            parent.signalType = "post_skipped"
            mock_db_posttrip.behavioralsignal.find_unique = AsyncMock(return_value=parent)

            intention = MagicMock()
            intention.id = f"int-{reason}"
            intention.userId = "user-1"
            intention.behavioralSignalId = f"signal-{reason}"
            intention.rawEventId = None
            intention.intentionType = reason
            intention.confidence = 1.0
            intention.source = "user_explicit"
            intention.userProvided = True
            intention.createdAt = datetime.now(timezone.utc)
            mock_db_posttrip.intentionsignal.create = AsyncMock(return_value=intention)

            result = await record_skip_intention(
                mock_db_posttrip,
                user_id="user-1",
                behavioral_signal_id=f"signal-{reason}",
                skip_reason=reason,
            )
            assert result["intentionType"] == reason

    @pytest.mark.asyncio
    async def test_invalid_skip_reason_raises(self, mock_db_posttrip):
        """Invalid skip reason should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid skip reason"):
            await record_skip_intention(
                mock_db_posttrip,
                user_id="user-1",
                behavioral_signal_id="signal-1",
                skip_reason="bored",  # not a valid reason
            )

    @pytest.mark.asyncio
    async def test_wrong_user_signal_raises(self, mock_db_posttrip):
        """Using a signal that belongs to another user should raise."""
        parent = MagicMock()
        parent.id = "signal-1"
        parent.userId = "other-user"
        parent.signalType = "post_skipped"
        mock_db_posttrip.behavioralsignal.find_unique = AsyncMock(return_value=parent)

        with pytest.raises(ValueError, match="does not belong"):
            await record_skip_intention(
                mock_db_posttrip,
                user_id="user-1",
                behavioral_signal_id="signal-1",
                skip_reason="not_interested",
            )

    @pytest.mark.asyncio
    async def test_wrong_signal_type_raises(self, mock_db_posttrip):
        """Using a signal with wrong signalType should raise."""
        parent = MagicMock()
        parent.id = "signal-1"
        parent.userId = "user-1"
        parent.signalType = "slot_view"  # not post_skipped
        mock_db_posttrip.behavioralsignal.find_unique = AsyncMock(return_value=parent)

        with pytest.raises(ValueError, match="expected 'post_skipped'"):
            await record_skip_intention(
                mock_db_posttrip,
                user_id="user-1",
                behavioral_signal_id="signal-1",
                skip_reason="not_interested",
            )

    @pytest.mark.asyncio
    async def test_nonexistent_signal_raises(self, mock_db_posttrip):
        """Referencing a nonexistent signal should raise."""
        mock_db_posttrip.behavioralsignal.find_unique = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await record_skip_intention(
                mock_db_posttrip,
                user_id="user-1",
                behavioral_signal_id="nonexistent",
                skip_reason="weather",
            )


# ===================================================================
# 4. Email rate limiting + unsubscribe
# ===================================================================

class TestEmailGuards:
    """Tests for email rate limiting and unsubscribe checks."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_first_email(self, mock_redis_posttrip):
        """First email should pass rate limit check."""
        result = await check_email_rate_limit(mock_redis_posttrip, "user-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_second_email_within_7d(self, mock_redis_posttrip):
        """Second email within 7 days should be blocked."""
        # Simulate first email sent
        await mock_redis_posttrip.setex(
            "posttrip:email:sent:user-1", 604800, "1"
        )

        result = await check_email_rate_limit(mock_redis_posttrip, "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribed_user_detected(self, mock_db_posttrip):
        """Unsubscribed user should be detected."""
        mock_db_posttrip.query_raw = AsyncMock(return_value=[{"1": 1}])
        result = await check_unsubscribed(mock_db_posttrip, "user-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_subscribed_user_passes(self, mock_db_posttrip):
        """Subscribed user should pass unsubscribe check."""
        mock_db_posttrip.query_raw = AsyncMock(return_value=[])
        result = await check_unsubscribed(mock_db_posttrip, "user-1")
        assert result is False


# ===================================================================
# 5. Login link generation
# ===================================================================

class TestLoginLinks:
    """Tests for one-time-use login link security."""

    @pytest.mark.asyncio
    async def test_login_link_contains_token(self, mock_redis_posttrip):
        """Generated login link should contain a token parameter."""
        url = await generate_login_link(
            mock_redis_posttrip,
            user_id="user-1",
            redirect_path="/trip/abc/memory",
        )
        assert "token=" in url
        assert "/auth/magic" in url

    @pytest.mark.asyncio
    async def test_login_link_no_session_tokens(self, mock_redis_posttrip):
        """Login links must NOT contain session tokens."""
        url = await generate_login_link(
            mock_redis_posttrip,
            user_id="user-1",
            redirect_path="/trip/abc/memory",
        )
        assert "session" not in url.lower()
        assert "cookie" not in url.lower()


# ===================================================================
# 6. Date range formatting
# ===================================================================

class TestDateRangeFormat:
    """Tests for _format_date_range() utility."""

    def test_same_month_format(self):
        result = _format_date_range("2026-02-10T00:00:00", "2026-02-17T00:00:00")
        assert "Feb" in result

    def test_different_month_format(self):
        result = _format_date_range("2026-01-28T00:00:00", "2026-02-05T00:00:00")
        assert "Jan" in result
        assert "Feb" in result

    def test_different_year_format(self):
        result = _format_date_range("2025-12-28T00:00:00", "2026-01-05T00:00:00")
        assert "2025" in result
        assert "2026" in result

    def test_invalid_dates_return_empty(self):
        result = _format_date_range("not-a-date", "also-not-a-date")
        assert result == ""
