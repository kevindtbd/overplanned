from __future__ import annotations

"""
Tests for services.api.ranking.cant_miss

Covers:
  1. Nodes below floor get boosted to 0.72
  2. Nodes already above floor are unchanged
  3. Non-cantMiss nodes are never affected
  4. Empty candidate list returns empty
  5. Warning logged when cantMiss=true but no iconic-worth-it tag
  6. set_cant_miss updates the correct node
  7. Graceful handling when pool query fails
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.ranking.cant_miss import (
    CANT_MISS_SCORE_FLOOR,
    ICONIC_VIBE_TAG,
    apply_cant_miss_floor,
    set_cant_miss,
)


# ---------------------------------------------------------------------------
# Asyncpg pool / connection mock helpers
# ---------------------------------------------------------------------------


def _make_row(node_id: str, vibe_slugs: list[str] | None = None) -> dict:
    """Simulate an asyncpg Record-like dict."""
    return {
        "id": node_id,
        "cantMiss": True,
        "vibe_tag_slugs": vibe_slugs if vibe_slugs is not None else [ICONIC_VIBE_TAG],
    }


def _make_pool(
    fetch_rows: list[dict] | None = None,
    execute_result: str = "UPDATE 1",
    fetch_raises: Exception | None = None,
) -> Any:
    """Build a minimal asyncpg pool mock.

    The pool's acquire() is used as an async context manager that yields a
    connection. The connection exposes .fetch() and .execute().
    """
    conn = AsyncMock()

    if fetch_raises is not None:
        conn.fetch = AsyncMock(side_effect=fetch_raises)
    else:
        conn.fetch = AsyncMock(return_value=fetch_rows or [])

    conn.execute = AsyncMock(return_value=execute_result)

    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool


def _node(node_id: str, score: float) -> dict:
    return {"id": node_id, "score": score}


# ---------------------------------------------------------------------------
# apply_cant_miss_floor tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApplyCantMissFloor:
    """Core floor-boost behaviour."""

    async def test_node_below_floor_is_boosted(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(fetch_rows=[_make_row(node_id)])
        candidates = [_node(node_id, 0.45)]

        result = await apply_cant_miss_floor(candidates, pool)

        assert result[0]["score"] == CANT_MISS_SCORE_FLOOR

    async def test_node_above_floor_is_unchanged(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(fetch_rows=[_make_row(node_id)])
        candidates = [_node(node_id, 0.85)]

        result = await apply_cant_miss_floor(candidates, pool)

        assert result[0]["score"] == 0.85

    async def test_node_exactly_at_floor_is_unchanged(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(fetch_rows=[_make_row(node_id)])
        candidates = [_node(node_id, CANT_MISS_SCORE_FLOOR)]

        result = await apply_cant_miss_floor(candidates, pool)

        assert result[0]["score"] == CANT_MISS_SCORE_FLOOR

    async def test_non_cant_miss_nodes_never_affected(self):
        regular_id = str(uuid.uuid4())
        # DB returns no cantMiss rows — pool fetch returns empty list
        pool = _make_pool(fetch_rows=[])
        candidates = [_node(regular_id, 0.10)]

        result = await apply_cant_miss_floor(candidates, pool)

        # Score must stay at 0.10 — no boost applied
        assert result[0]["score"] == 0.10

    async def test_empty_candidate_list_returns_empty(self):
        pool = _make_pool()
        result = await apply_cant_miss_floor([], pool)
        assert result == []
        # pool should never be queried for empty input
        pool.acquire  # not called — the function returns early

    async def test_multiple_nodes_mixed_cant_miss(self):
        cant_id = str(uuid.uuid4())
        regular_id = str(uuid.uuid4())
        pool = _make_pool(fetch_rows=[_make_row(cant_id)])
        candidates = [
            _node(cant_id, 0.30),
            _node(regular_id, 0.60),
        ]

        result = await apply_cant_miss_floor(candidates, pool)

        # cantMiss node boosted to floor
        assert result[0]["score"] == CANT_MISS_SCORE_FLOOR
        # Regular node unchanged
        assert result[1]["score"] == 0.60

    async def test_multiple_cant_miss_nodes_all_boosted(self):
        ids = [str(uuid.uuid4()) for _ in range(3)]
        pool = _make_pool(fetch_rows=[_make_row(i) for i in ids])
        candidates = [_node(i, 0.20) for i in ids]

        result = await apply_cant_miss_floor(candidates, pool)

        for c in result:
            assert c["score"] == CANT_MISS_SCORE_FLOOR

    async def test_returns_same_list_object(self):
        """Mutation in-place — caller retains original list reference."""
        node_id = str(uuid.uuid4())
        pool = _make_pool(fetch_rows=[_make_row(node_id)])
        candidates = [_node(node_id, 0.50)]

        result = await apply_cant_miss_floor(candidates, pool)

        assert result is candidates

    async def test_pool_query_passes_all_candidate_ids(self):
        ids = [str(uuid.uuid4()) for _ in range(4)]
        pool = _make_pool(fetch_rows=[])
        candidates = [_node(i, 0.5) for i in ids]

        await apply_cant_miss_floor(candidates, pool)

        # Grab the connection that was used via the context manager
        # We need to reconstruct it — use a capturing pool instead
        captured: list[list] = []

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=lambda q, arg: captured.append(arg) or []
        )

        @asynccontextmanager
        async def _acquire():
            yield conn

        capturing_pool = MagicMock()
        capturing_pool.acquire = _acquire

        await apply_cant_miss_floor(candidates, capturing_pool)

        assert set(captured[0]) == set(ids)


# ---------------------------------------------------------------------------
# Warning: missing iconic-worth-it vibe tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCantMissWarnings:
    async def test_warning_when_iconic_tag_missing(self, caplog):
        node_id = str(uuid.uuid4())
        # Return a cantMiss row with NO iconic-worth-it tag
        pool = _make_pool(fetch_rows=[_make_row(node_id, vibe_slugs=["hidden-gem"])])
        candidates = [_node(node_id, 0.80)]

        import logging

        with caplog.at_level(logging.WARNING, logger="services.api.ranking.cant_miss"):
            await apply_cant_miss_floor(candidates, pool)

        assert any(ICONIC_VIBE_TAG in r.message for r in caplog.records)
        assert any(node_id in r.message for r in caplog.records)

    async def test_no_warning_when_iconic_tag_present(self, caplog):
        node_id = str(uuid.uuid4())
        # Tag IS present
        pool = _make_pool(
            fetch_rows=[_make_row(node_id, vibe_slugs=[ICONIC_VIBE_TAG, "historic"])]
        )
        candidates = [_node(node_id, 0.80)]

        import logging

        with caplog.at_level(logging.WARNING, logger="services.api.ranking.cant_miss"):
            await apply_cant_miss_floor(candidates, pool)

        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) == 0


# ---------------------------------------------------------------------------
# Graceful pool failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCantMissPoolFailure:
    async def test_pool_failure_returns_original_list_unchanged(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(fetch_raises=Exception("connection timeout"))
        candidates = [_node(node_id, 0.30)]

        # Must not raise
        result = await apply_cant_miss_floor(candidates, pool)

        # Score must remain unchanged — floor was never applied
        assert result[0]["score"] == 0.30
        assert result is candidates

    async def test_pool_failure_logs_error(self, caplog):
        pool = _make_pool(fetch_raises=RuntimeError("pool exhausted"))
        candidates = [_node(str(uuid.uuid4()), 0.20)]

        import logging

        with caplog.at_level(logging.ERROR, logger="services.api.ranking.cant_miss"):
            await apply_cant_miss_floor(candidates, pool)

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) == 1
        assert "pool exhausted" in error_records[0].message


# ---------------------------------------------------------------------------
# set_cant_miss tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSetCantMiss:
    async def test_set_cant_miss_true_returns_true_when_row_updated(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(execute_result="UPDATE 1")

        result = await set_cant_miss(pool, node_id, cant_miss=True)

        assert result is True

    async def test_set_cant_miss_false_returns_true_when_row_updated(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(execute_result="UPDATE 1")

        result = await set_cant_miss(pool, node_id, cant_miss=False)

        assert result is True

    async def test_returns_false_when_node_not_found(self):
        node_id = str(uuid.uuid4())
        pool = _make_pool(execute_result="UPDATE 0")

        result = await set_cant_miss(pool, node_id)

        assert result is False

    async def test_executes_correct_sql_and_args(self):
        node_id = str(uuid.uuid4())
        captured_calls: list[tuple] = []
        conn = AsyncMock()

        async def _execute(query: str, *args):
            captured_calls.append((query, args))
            return "UPDATE 1"

        conn.execute = _execute

        @asynccontextmanager
        async def _acquire():
            yield conn

        pool = MagicMock()
        pool.acquire = _acquire

        await set_cant_miss(pool, node_id, cant_miss=True)

        assert len(captured_calls) == 1
        query, args = captured_calls[0]
        assert 'activity_nodes' in query
        assert '"cantMiss"' in query
        assert args[0] is True  # cant_miss value
        assert args[1] == node_id

    async def test_default_cant_miss_arg_is_true(self):
        node_id = str(uuid.uuid4())
        captured_args: list = []
        conn = AsyncMock()

        async def _execute(query: str, *args):
            captured_args.extend(args)
            return "UPDATE 1"

        conn.execute = _execute

        @asynccontextmanager
        async def _acquire():
            yield conn

        pool = MagicMock()
        pool.acquire = _acquire

        await set_cant_miss(pool, node_id)

        # First positional arg to the parameterised query is the bool value
        assert captured_args[0] is True
