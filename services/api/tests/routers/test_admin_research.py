"""Tests for Pipeline D admin routes."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.api.routers.admin_research import (
    list_research_jobs,
    list_conflicts,
    resolve_conflict,
)


def _make_mock_session():
    session = AsyncMock()
    return session


class TestListResearchJobs:
    @pytest.mark.asyncio
    async def test_returns_jobs(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"id": "job-1", "cityId": "bend", "status": "COMPLETE",
             "totalCostUsd": 1.50, "venuesResearched": 71, "createdAt": "2026-02-26"}
        ]
        session.execute.return_value = mock_result

        result = await list_research_jobs(session)
        assert len(result) == 1
        assert result[0]["cityId"] == "bend"

    @pytest.mark.asyncio
    async def test_filters_by_city(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        session.execute.return_value = mock_result

        await list_research_jobs(session, city_slug="bend")
        call_args = session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "cityId" in sql_text


class TestListConflicts:
    @pytest.mark.asyncio
    async def test_returns_conflicted_nodes(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"activityNodeId": "node-1", "signalConflict": True, "mergedConfidence": 0.5}
        ]
        session.execute.return_value = mock_result

        result = await list_conflicts(session, "bend")
        assert len(result) == 1


class TestResolveConflict:
    @pytest.mark.asyncio
    async def test_logs_resolution(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute.return_value = mock_result

        result = await resolve_conflict(
            session, cross_ref_id="cr-1",
            action="accept_d", resolved_by="admin@test.com")
        assert result is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_already_resolved(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        result = await resolve_conflict(
            session, cross_ref_id="cr-1",
            action="accept_d", resolved_by="admin@test.com")
        assert result is False
