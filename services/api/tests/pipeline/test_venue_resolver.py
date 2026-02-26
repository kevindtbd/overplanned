"""Tests for Pipeline D simplified venue name resolver."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.api.pipeline.venue_resolver import (
    resolve_venue_names,
    ResolutionResult,
    MatchType,
)


def _make_fake_pool():
    conn = AsyncMock()

    # asyncpg pool.acquire() returns an async context manager directly (not a coroutine).
    # Use MagicMock for the context manager object so __aenter__/__aexit__ wire up properly.
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


class TestResolveVenueNames:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        pool, conn = _make_fake_pool()
        conn.fetchrow.return_value = {"id": "node-1", "canonicalName": "Pine Tavern"}
        results = await resolve_venue_names(pool, "bend", [{"venue_name": "Pine Tavern"}])
        assert len(results) == 1
        assert results[0].match_type == MatchType.EXACT
        assert results[0].activity_node_id == "node-1"

    @pytest.mark.asyncio
    async def test_fuzzy_match_fallback(self):
        pool, conn = _make_fake_pool()
        conn.fetchrow.side_effect = [
            None,  # exact miss
            {"id": "node-2", "canonicalName": "Pine Tavern Restaurant", "similarity": 0.85},
        ]
        results = await resolve_venue_names(pool, "bend", [{"venue_name": "Pine Tavern"}])
        assert len(results) == 1
        assert results[0].match_type == MatchType.FUZZY

    @pytest.mark.asyncio
    async def test_unresolved_when_no_match(self):
        pool, conn = _make_fake_pool()
        conn.fetchrow.return_value = None
        results = await resolve_venue_names(pool, "bend", [{"venue_name": "Nonexistent"}])
        assert len(results) == 1
        assert results[0].match_type == MatchType.UNRESOLVED
        assert results[0].activity_node_id is None

    @pytest.mark.asyncio
    async def test_city_scoped(self):
        pool, conn = _make_fake_pool()
        conn.fetchrow.return_value = None
        await resolve_venue_names(pool, "bend", [{"venue_name": "Test"}])
        calls = conn.fetchrow.call_args_list
        for call in calls:
            sql = call[0][0]
            assert "city" in sql.lower()

    @pytest.mark.asyncio
    async def test_multiple_venues(self):
        pool, conn = _make_fake_pool()
        conn.fetchrow.side_effect = [
            {"id": "n1", "canonicalName": "Place A"},
            {"id": "n2", "canonicalName": "Place B"},
            None, None,  # Place C: exact miss, fuzzy miss
        ]
        results = await resolve_venue_names(pool, "bend",
            [{"venue_name": "Place A"}, {"venue_name": "Place B"}, {"venue_name": "Place C"}])
        resolved = [r for r in results if r.match_type != MatchType.UNRESOLVED]
        unresolved = [r for r in results if r.match_type == MatchType.UNRESOLVED]
        assert len(resolved) == 2
        assert len(unresolved) == 1

    @pytest.mark.asyncio
    async def test_empty_name_is_unresolved(self):
        pool, conn = _make_fake_pool()
        results = await resolve_venue_names(pool, "bend", [{"venue_name": ""}])
        assert results[0].match_type == MatchType.UNRESOLVED
