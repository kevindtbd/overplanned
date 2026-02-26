"""
Integration tests: push notification queue, email queue, destination suggestion.

Covers:
- Push notification enqueue + deduplication
- Push queue processing (due items only)
- Email queue processing with rate limit + unsubscribe guards
- Destination suggestion via Qdrant (persona vector search)
- Re-engagement scheduling delays (24h push, 7d email)
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.posttrip.push_service import (
    register_push_token,
    revoke_push_token,
    enqueue_trip_completion_push,
    process_push_queue,
    PUSH_QUEUE_KEY,
)
from services.api.posttrip.reengagement import (
    suggest_next_destination,
    process_pending_emails,
    EMAIL_QUEUE_KEY,
    PUSH_DELAY_HOURS,
    EMAIL_DELAY_DAYS,
)


# ===================================================================
# 1. Push token registration
# ===================================================================

class TestPushTokenRegistration:

    @pytest.mark.asyncio
    async def test_register_valid_ios_token(self, mock_db_posttrip):
        """Register an iOS push token."""
        now = datetime.now(timezone.utc)
        # First execute: SELECT existing token -> no rows (first() returns None)
        mock_db_posttrip.returns_none()
        # Second execute: INSERT ... RETURNING -> mappings().first() returns row
        mock_db_posttrip.returns_mappings([{
            "id": "tok-1", "userId": "user-1", "deviceId": "dev-1",
            "platform": "ios", "isActive": True,
            "createdAt": now, "updatedAt": now,
        }])

        result = await register_push_token(
            mock_db_posttrip.mock,
            user_id="user-1",
            device_token="fcm-token-abc",
            platform="ios",
            device_id="dev-1",
        )
        assert result["platform"] == "ios"
        assert result["isActive"] is True

    @pytest.mark.asyncio
    async def test_reject_invalid_platform(self, mock_db_posttrip):
        """Invalid platform should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid platform"):
            await register_push_token(
                mock_db_posttrip.mock,
                user_id="user-1",
                device_token="tok",
                platform="blackberry",
                device_id="dev-1",
            )

    @pytest.mark.asyncio
    async def test_revoke_deactivates_token(self, mock_db_posttrip):
        """Revoking a token sets isActive=false."""
        # execute: UPDATE ... RETURNING id -> .first() returns a row
        mock_db_posttrip.returns_row("tok-1")

        result = await revoke_push_token(
            mock_db_posttrip.mock, user_id="user-1", device_id="dev-1"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_false(self, mock_db_posttrip):
        """Revoking a non-existent token returns False."""
        # execute: UPDATE ... RETURNING id -> .first() returns None
        mock_db_posttrip.returns_none()

        result = await revoke_push_token(
            mock_db_posttrip.mock, user_id="user-1", device_id="dev-999"
        )
        assert result is False


# ===================================================================
# 2. Push notification enqueue + dedup
# ===================================================================

class TestPushEnqueue:

    @pytest.mark.asyncio
    async def test_enqueue_new_push(self, mock_redis_posttrip):
        """First enqueue for a trip should succeed."""
        result = await enqueue_trip_completion_push(
            mock_redis_posttrip,
            user_id="user-1",
            trip_id="trip-1",
            trip_destination="Tokyo, Japan",
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_dedup_blocks_second_enqueue(self, mock_redis_posttrip):
        """Second enqueue for the same trip should be blocked by dedup."""
        # First enqueue
        await enqueue_trip_completion_push(
            mock_redis_posttrip,
            user_id="user-1",
            trip_id="trip-1",
            trip_destination="Tokyo, Japan",
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        # Mark as sent (simulate)
        dedup_key = "posttrip:push:sent:user-1:trip-1"
        await mock_redis_posttrip.setex(dedup_key, 86400, "1")

        # Second attempt -- should be blocked
        result = await enqueue_trip_completion_push(
            mock_redis_posttrip,
            user_id="user-1",
            trip_id="trip-1",
            trip_destination="Tokyo, Japan",
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_push_deep_link_has_no_session_token(self, mock_redis_posttrip):
        """Push notification payload must NOT contain session tokens."""
        await enqueue_trip_completion_push(
            mock_redis_posttrip,
            user_id="user-1",
            trip_id="trip-1",
            trip_destination="Tokyo",
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        # Check the enqueued payload
        items = mock_redis_posttrip._sorted_sets.get(PUSH_QUEUE_KEY, {})
        for payload_str in items:
            payload = json.loads(payload_str)
            assert "session" not in json.dumps(payload).lower()
            assert "token" not in payload.get("type", "").lower()


# ===================================================================
# 3. Push queue processing
# ===================================================================

class TestPushQueueProcessing:

    @pytest.mark.asyncio
    async def test_processes_due_pushes(self, mock_redis_posttrip, mock_db_posttrip):
        """Due push notifications should be processed."""
        # Enqueue a push that's already due
        now = datetime.now(timezone.utc)
        past_time = now - timedelta(hours=1)

        payload = json.dumps({
            "type": "trip_completion_24h",
            "user_id": "user-1",
            "trip_id": "trip-1",
            "destination": "Tokyo",
            "scheduled_for": past_time.isoformat(),
        })
        await mock_redis_posttrip.zadd(PUSH_QUEUE_KEY, {payload: past_time.timestamp()})

        # SA: get_active_tokens calls session.execute(text(...)) -> mappings().all()
        mock_db_posttrip.returns_mappings([
            {"id": "tok-1", "deviceToken": "fcm-xxx", "platform": "ios", "deviceId": "dev-1"},
        ])

        with patch("services.api.posttrip.push_service._send_fcm_notification") as mock_fcm:
            mock_fcm.return_value = True

            stats = await process_push_queue(
                mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
            )

        assert stats["sent"] == 1
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_skips_user_without_tokens(self, mock_redis_posttrip, mock_db_posttrip):
        """Users without active push tokens should be skipped."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        payload = json.dumps({
            "type": "trip_completion_24h",
            "user_id": "user-no-tokens",
            "trip_id": "trip-1",
            "destination": "Tokyo",
            "scheduled_for": past.isoformat(),
        })
        await mock_redis_posttrip.zadd(PUSH_QUEUE_KEY, {payload: past.timestamp()})

        # SA: get_active_tokens -> mappings().all() returns empty
        mock_db_posttrip.returns_mappings([])

        stats = await process_push_queue(
            mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
        )
        assert stats["skipped"] == 1

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero_stats(self, mock_redis_posttrip, mock_db_posttrip):
        """Empty queue returns all-zero stats."""
        stats = await process_push_queue(
            mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
        )
        assert stats == {"sent": 0, "failed": 0, "skipped": 0}


# ===================================================================
# 4. Email queue processing
# ===================================================================

class TestEmailQueueProcessing:

    @pytest.mark.asyncio
    async def test_processes_due_emails(self, mock_redis_posttrip, mock_db_posttrip):
        """Due emails should be processed (mocking the send)."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        email_payload = json.dumps({
            "type": "trip_memory_7d",
            "user_id": "user-1",
            "trip_id": "trip-1",
            "user_email": "test@example.com",
            "user_name": "Test User",
            "destination": "Tokyo, Japan",
            "city": "Tokyo",
            "country": "Japan",
            "start_date": (now - timedelta(days=14)).isoformat(),
            "end_date": (now - timedelta(days=7)).isoformat(),
            "scheduled_for": past.isoformat(),
        })
        await mock_redis_posttrip.zadd(EMAIL_QUEUE_KEY, {email_payload: past.timestamp()})

        # SA: check_unsubscribed -> session.execute(text(...)) -> .first() returns None
        mock_db_posttrip.returns_none()
        # SA: _get_trip_highlights -> session.execute(text(...)) -> mappings().all() returns []
        mock_db_posttrip.returns_mappings([])

        with patch("services.api.posttrip.reengagement.send_trip_memory_email") as mock_send:
            mock_send.return_value = True

            stats = await process_pending_emails(
                mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
            )

        assert stats["sent"] == 1

    @pytest.mark.asyncio
    async def test_skips_unsubscribed_users(self, mock_redis_posttrip, mock_db_posttrip):
        """Unsubscribed users should be skipped."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        email_payload = json.dumps({
            "type": "trip_memory_7d",
            "user_id": "user-unsub",
            "trip_id": "trip-1",
            "user_email": "unsub@example.com",
            "destination": "Tokyo",
            "scheduled_for": past.isoformat(),
        })
        await mock_redis_posttrip.zadd(EMAIL_QUEUE_KEY, {email_payload: past.timestamp()})

        # SA: check_unsubscribed -> session.execute(text(...)) -> .first() returns a row
        mock_db_posttrip.returns_row(1)

        stats = await process_pending_emails(
            mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
        )
        assert stats["skipped"] == 1

    @pytest.mark.asyncio
    async def test_rate_limited_user_blocked(self, mock_redis_posttrip, mock_db_posttrip):
        """Rate-limited users should not receive email."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        email_payload = json.dumps({
            "type": "trip_memory_7d",
            "user_id": "user-rl",
            "trip_id": "trip-1",
            "user_email": "rl@example.com",
            "destination": "Tokyo",
            "scheduled_for": past.isoformat(),
        })
        await mock_redis_posttrip.zadd(EMAIL_QUEUE_KEY, {email_payload: past.timestamp()})

        # SA: check_unsubscribed -> .first() returns None (not unsubscribed)
        mock_db_posttrip.returns_none()

        # Rate limited
        await mock_redis_posttrip.setex("posttrip:email:sent:user-rl", 604800, "1")

        stats = await process_pending_emails(
            mock_redis_posttrip, mock_db_posttrip.mock, batch_size=10,
        )
        assert stats["rate_limited"] == 1


# ===================================================================
# 5. Destination suggestion
# ===================================================================

class TestDestinationSuggestion:

    @pytest.mark.asyncio
    async def test_suggests_destination_with_enough_signals(
        self, mock_db_posttrip, mock_qdrant_posttrip,
    ):
        """With 3+ positive signals, should return a destination suggestion."""
        # Mock positive signals
        signals = []
        for i in range(5):
            s = MagicMock()
            s.activityNodeId = f"node-{i}"
            s.userId = "user-1"
            signals.append(s)

        # SA: select BehavioralSignal -> scalars().all() returns signals
        mock_db_posttrip.returns_many(signals)

        # SA: raw SQL select ActivityNode -> mappings().all()
        activities = [
            {"id": f"node-{i}", "name": f"Activity {i}", "category": "dining", "city": "Tokyo"}
            for i in range(5)
        ]
        mock_db_posttrip.returns_mappings(activities)

        # SA: select Trip -> scalars().first() returns trip
        trip = MagicMock()
        trip.city = "Tokyo"
        mock_db_posttrip.returns_one(trip)

        with patch("services.api.posttrip.reengagement.embedding_service") as mock_embed:
            mock_embed.embed_single = MagicMock(return_value=[0.1] * 768)

            result = await suggest_next_destination(
                mock_db_posttrip.mock,
                mock_qdrant_posttrip,
                user_id="user-1",
                completed_trip_id="trip-1",
            )

        assert result is not None
        assert "city" in result
        assert "country" in result
        assert "reason" in result
        assert "top_activities" in result
        assert result["city"] == "Kyoto"

    @pytest.mark.asyncio
    async def test_insufficient_signals_returns_none(
        self, mock_db_posttrip, mock_qdrant_posttrip,
    ):
        """With < 3 positive signals, should return None."""
        s = MagicMock()
        s.activityNodeId = "node-1"
        s.userId = "user-1"
        # SA: select BehavioralSignal -> scalars().all() returns [s]
        mock_db_posttrip.returns_many([s])

        result = await suggest_next_destination(
            mock_db_posttrip.mock,
            mock_qdrant_posttrip,
            user_id="user-1",
            completed_trip_id="trip-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_excludes_visited_city(
        self, mock_db_posttrip, mock_qdrant_posttrip,
    ):
        """Suggestion should NOT include the city that was just visited."""
        signals = [MagicMock(activityNodeId=f"n-{i}", userId="u-1") for i in range(5)]
        mock_db_posttrip.returns_many(signals)

        activities = [
            {"id": f"n-{i}", "name": f"Act {i}", "category": "dining", "city": "Tokyo"}
            for i in range(5)
        ]
        mock_db_posttrip.returns_mappings(activities)

        trip = MagicMock()
        trip.city = "Tokyo"
        mock_db_posttrip.returns_one(trip)

        with patch("services.api.posttrip.reengagement.embedding_service") as mock_embed:
            mock_embed.embed_single = MagicMock(return_value=[0.1] * 768)

            result = await suggest_next_destination(
                mock_db_posttrip.mock,
                mock_qdrant_posttrip,
                user_id="u-1",
                completed_trip_id="trip-1",
            )

        # Result should be Kyoto (from mock), not Tokyo
        if result:
            assert result["city"].lower() != "tokyo"


# ===================================================================
# 6. Scheduling delay constants
# ===================================================================

class TestSchedulingDelays:
    """Verify re-engagement timing constants."""

    def test_push_delay_is_24_hours(self):
        assert PUSH_DELAY_HOURS == 24

    def test_email_delay_is_7_days(self):
        assert EMAIL_DELAY_DAYS == 7
