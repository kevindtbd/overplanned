"""Tests for ranking_logger -- RankingEvent row insertion."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.signals.ranking_logger import log_ranking_event


def _make_mock_session(*, should_fail: bool = False) -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    if should_fail:
        session.commit = AsyncMock(side_effect=Exception("DB write failed"))
        session.rollback = AsyncMock()
    else:
        session.commit = AsyncMock()
    return session


def _base_kwargs() -> dict:
    """Minimum required kwargs for log_ranking_event."""
    return {
        "trip_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "day_number": 1,
        "model_name": "overplanned-ranker",
        "model_version": "v0.1.0",
        "candidate_ids": [str(uuid.uuid4()) for _ in range(5)],
        "ranked_ids": [str(uuid.uuid4()) for _ in range(3)],
        "selected_ids": [str(uuid.uuid4()) for _ in range(2)],
        "surface": "itinerary",
    }


@pytest.mark.asyncio
class TestLogRankingEvent:
    """RankingEvent logger creates rows correctly."""

    async def test_creates_ranking_event_row(self):
        session = _make_mock_session()
        kwargs = _base_kwargs()

        await log_ranking_event(session, **kwargs)

        session.add.assert_called_once()
        event = session.add.call_args[0][0]
        assert event.tripId == kwargs["trip_id"]
        assert event.userId == kwargs["user_id"]
        assert event.dayNumber == 1
        assert event.modelName == "overplanned-ranker"
        assert event.modelVersion == "v0.1.0"
        assert event.candidateIds == kwargs["candidate_ids"]
        assert event.rankedIds == kwargs["ranked_ids"]
        assert event.selectedIds == kwargs["selected_ids"]
        assert event.surface == "itinerary"
        session.commit.assert_awaited_once()

    async def test_optional_fields_default_to_none(self):
        session = _make_mock_session()
        kwargs = _base_kwargs()

        await log_ranking_event(session, **kwargs)

        event = session.add.call_args[0][0]
        assert event.sessionId is None
        assert event.shadowModelName is None
        assert event.shadowModelVersion is None
        assert event.shadowRankedIds == []
        assert event.latencyMs is None

    async def test_optional_fields_set_when_provided(self):
        session = _make_mock_session()
        kwargs = _base_kwargs()
        kwargs["session_id"] = str(uuid.uuid4())
        kwargs["shadow_model_name"] = "shadow-ranker"
        kwargs["shadow_model_version"] = "v0.0.1"
        kwargs["shadow_ranked_ids"] = [str(uuid.uuid4())]
        kwargs["latency_ms"] = 42

        await log_ranking_event(session, **kwargs)

        event = session.add.call_args[0][0]
        assert event.sessionId == kwargs["session_id"]
        assert event.shadowModelName == "shadow-ranker"
        assert event.shadowModelVersion == "v0.0.1"
        assert event.shadowRankedIds == kwargs["shadow_ranked_ids"]
        assert event.latencyMs == 42

    async def test_generates_uuid_id(self):
        session = _make_mock_session()
        await log_ranking_event(session, **_base_kwargs())
        event = session.add.call_args[0][0]
        # Should be a valid UUID
        uuid.UUID(event.id)

    async def test_sets_created_at(self):
        session = _make_mock_session()
        before = datetime.now(timezone.utc)
        await log_ranking_event(session, **_base_kwargs())
        after = datetime.now(timezone.utc)
        event = session.add.call_args[0][0]
        assert before <= event.createdAt <= after


@pytest.mark.asyncio
class TestLogRankingEventErrorHandling:
    """Logger is fire-and-forget safe -- never raises."""

    async def test_db_error_is_caught_and_logged(self):
        session = _make_mock_session(should_fail=True)

        # Should NOT raise
        await log_ranking_event(session, **_base_kwargs())

        session.rollback.assert_awaited_once()

    async def test_rollback_failure_also_caught(self):
        session = _make_mock_session(should_fail=True)
        session.rollback = AsyncMock(side_effect=Exception("rollback failed too"))

        # Still should NOT raise
        await log_ranking_event(session, **_base_kwargs())
