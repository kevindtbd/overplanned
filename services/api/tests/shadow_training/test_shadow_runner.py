"""
Tests for Phase 4.2: Shadow Mode Infrastructure.

Covers:
- ShadowRunner with shadow mode enabled/disabled
- Overlap@5 computation
- NDCG@10 computation
- Fire-and-forget detached execution
- Model prediction failure handling
- DB storage of shadow results
- Feature flag behavior
- Edge cases (empty rankings, identical rankings, no overlap)
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.shadow.runner import (
    ShadowResult,
    ShadowRunner,
    compute_ndcg_at_k,
    compute_overlap_at_k,
)


# ---------------------------------------------------------------------------
# Mock model
# ---------------------------------------------------------------------------

@dataclass
class MockShadowModel:
    """A mock shadow model for testing."""
    model_id: str = "test-bpr-v1"
    model_version: str = "1.0.0"
    _rankings: list[str] | None = None
    _should_fail: bool = False

    async def predict(self, user_id: str, context_items: list[str]) -> list[str]:
        if self._should_fail:
            raise RuntimeError("Model inference failed")
        if self._rankings is not None:
            return self._rankings
        return list(reversed(context_items))  # Reverse as default behavior


def _make_pool():
    """Build a mock asyncpg pool."""
    pool = AsyncMock()
    conn = AsyncMock()

    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acm)

    return pool, conn


# ===========================================================================
# Overlap@5 tests
# ===========================================================================

class TestOverlapAtK:
    """Tests for overlap@k metric computation."""

    def test_identical_rankings(self):
        """Identical top-5 produces overlap=1.0."""
        shadow = ["a", "b", "c", "d", "e"]
        prod = ["a", "b", "c", "d", "e"]
        assert compute_overlap_at_k(shadow, prod, k=5) == 1.0

    def test_no_overlap(self):
        """Completely different top-5 produces overlap=0.0."""
        shadow = ["a", "b", "c", "d", "e"]
        prod = ["f", "g", "h", "i", "j"]
        assert compute_overlap_at_k(shadow, prod, k=5) == 0.0

    def test_partial_overlap(self):
        """3/5 overlap produces 0.6."""
        shadow = ["a", "b", "c", "x", "y"]
        prod = ["a", "b", "c", "d", "e"]
        assert compute_overlap_at_k(shadow, prod, k=5) == pytest.approx(0.6)

    def test_empty_shadow(self):
        """Empty shadow ranking returns 0.0."""
        assert compute_overlap_at_k([], ["a", "b", "c"], k=5) == 0.0

    def test_empty_production(self):
        """Empty production ranking returns 0.0."""
        assert compute_overlap_at_k(["a", "b"], [], k=5) == 0.0

    def test_k_larger_than_list(self):
        """When k > list length, uses entire list."""
        shadow = ["a", "b"]
        prod = ["a", "c"]
        assert compute_overlap_at_k(shadow, prod, k=5) == 0.5

    def test_different_order_same_items(self):
        """Order doesn't matter for overlap -- same items = 1.0."""
        shadow = ["e", "d", "c", "b", "a"]
        prod = ["a", "b", "c", "d", "e"]
        assert compute_overlap_at_k(shadow, prod, k=5) == 1.0


# ===========================================================================
# NDCG@10 tests
# ===========================================================================

class TestNdcgAtK:
    """Tests for NDCG@k metric computation."""

    def test_perfect_ranking(self):
        """Identical ranking produces NDCG=1.0."""
        ranking = ["a", "b", "c", "d", "e"]
        assert compute_ndcg_at_k(ranking, ranking, k=10) == pytest.approx(1.0, abs=0.001)

    def test_empty_rankings(self):
        """Empty rankings produce 0.0."""
        assert compute_ndcg_at_k([], ["a"], k=10) == 0.0
        assert compute_ndcg_at_k(["a"], [], k=10) == 0.0

    def test_completely_wrong_ranking(self):
        """Shadow items not in production have 0 relevance."""
        shadow = ["x", "y", "z"]
        prod = ["a", "b", "c"]
        assert compute_ndcg_at_k(shadow, prod, k=10) == 0.0

    def test_reversed_ranking_lower_than_perfect(self):
        """Reversed ranking has lower NDCG than perfect ranking."""
        prod = ["a", "b", "c", "d", "e"]
        shadow_reversed = ["e", "d", "c", "b", "a"]
        ndcg_perfect = compute_ndcg_at_k(prod, prod, k=5)
        ndcg_reversed = compute_ndcg_at_k(shadow_reversed, prod, k=5)
        assert ndcg_perfect > ndcg_reversed


# ===========================================================================
# ShadowRunner core tests
# ===========================================================================

class TestShadowRunner:
    """Tests for ShadowRunner execution."""

    async def test_disabled_returns_none(self):
        """When no model is set and SHADOW_MODE_ENABLED=false, returns None."""
        pool, _ = _make_pool()
        runner = ShadowRunner(pool=pool, model=None)
        result = await runner.run_shadow("u1", "t1", ["a", "b"], ["b", "a"])
        assert result is None

    async def test_enabled_with_model_returns_result(self):
        """With a model provided, returns ShadowResult."""
        pool, conn = _make_pool()
        model = MockShadowModel(_rankings=["a", "b", "c"])
        runner = ShadowRunner(pool=pool, model=model)

        result = await runner.run_shadow("u1", "t1", ["a", "b", "c"], ["a", "b", "c"])
        assert result is not None
        assert isinstance(result, ShadowResult)
        assert result.model_id == "test-bpr-v1"
        assert result.shadow_rankings == ["a", "b", "c"]

    async def test_result_has_correct_metrics(self):
        """ShadowResult contains computed overlap and NDCG values."""
        pool, conn = _make_pool()
        prod = ["a", "b", "c", "d", "e"]
        model = MockShadowModel(_rankings=["a", "b", "c", "d", "e"])
        runner = ShadowRunner(pool=pool, model=model)

        result = await runner.run_shadow("u1", "t1", prod, prod)
        assert result.overlap_at_5 == 1.0
        assert result.ndcg_at_10 > 0.0

    async def test_model_failure_returns_none(self):
        """When model.predict raises, returns None gracefully."""
        pool, conn = _make_pool()
        model = MockShadowModel(_should_fail=True)
        runner = ShadowRunner(pool=pool, model=model)

        result = await runner.run_shadow("u1", "t1", ["a", "b"], ["a", "b"])
        assert result is None

    async def test_stores_result_in_db(self):
        """Shadow result is persisted to the ShadowResult table."""
        pool, conn = _make_pool()
        model = MockShadowModel(_rankings=["a", "b"])
        runner = ShadowRunner(pool=pool, model=model)

        await runner.run_shadow("u1", "t1", ["a", "b"], ["a", "b"])

        # Should have called execute for CREATE TABLE and INSERT
        assert conn.execute.call_count >= 2

    async def test_db_storage_failure_does_not_raise(self):
        """DB storage failure is logged but does not crash the runner."""
        pool, conn = _make_pool()
        model = MockShadowModel(_rankings=["a", "b"])
        runner = ShadowRunner(pool=pool, model=model)

        # Make the INSERT fail
        call_count = 0
        async def _failing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:  # Let CREATE TABLE pass, fail INSERT
                raise Exception("DB write failed")
        conn.execute = AsyncMock(side_effect=_failing_execute)

        # Should not raise
        result = await runner.run_shadow("u1", "t1", ["a", "b"], ["a", "b"])
        # Result is still computed even if storage fails
        # (it may be None if store raises before return, but no exception propagates)

    async def test_latency_tracked(self):
        """Shadow result includes latency_ms."""
        pool, conn = _make_pool()
        model = MockShadowModel(_rankings=["a"])
        runner = ShadowRunner(pool=pool, model=model)

        result = await runner.run_shadow("u1", "t1", ["a"], ["a"])
        assert result is not None
        assert isinstance(result.latency_ms, int)
        assert result.latency_ms >= 0


# ===========================================================================
# Detached execution tests
# ===========================================================================

class TestDetachedExecution:
    """Tests for fire-and-forget shadow execution."""

    async def test_detached_returns_task(self):
        """run_shadow_detached returns an asyncio.Task."""
        pool, _ = _make_pool()
        model = MockShadowModel(_rankings=["a"])
        runner = ShadowRunner(pool=pool, model=model)

        task = runner.run_shadow_detached("u1", "t1", ["a"], ["a"])
        assert task is not None
        assert isinstance(task, asyncio.Task)
        await task  # Clean up

    async def test_detached_disabled_returns_none(self):
        """When disabled, detached run returns None (no task created)."""
        pool, _ = _make_pool()
        runner = ShadowRunner(pool=pool, model=None)

        task = runner.run_shadow_detached("u1", "t1", ["a"], ["a"])
        assert task is None

    async def test_detached_does_not_propagate_errors(self):
        """Background task errors are caught by the done callback."""
        pool, _ = _make_pool()
        model = MockShadowModel(_should_fail=True)
        runner = ShadowRunner(pool=pool, model=model)

        task = runner.run_shadow_detached("u1", "t1", ["a"], ["a"])
        assert task is not None
        # Should complete without raising
        result = await task
        assert result is None


# ===========================================================================
# ShadowResult dataclass tests
# ===========================================================================

class TestShadowResultDataclass:
    """Tests for the ShadowResult dataclass."""

    def test_created_at_default(self):
        """created_at defaults to current UTC time."""
        result = ShadowResult(
            model_id="m1",
            model_version="1.0",
            shadow_rankings=["a"],
            production_rankings=["a"],
            overlap_at_5=1.0,
            ndcg_at_10=1.0,
            latency_ms=50,
        )
        assert result.created_at is not None
        assert result.created_at.tzinfo is not None

    def test_all_fields_accessible(self):
        """All dataclass fields are accessible."""
        result = ShadowResult(
            model_id="test",
            model_version="2.0",
            shadow_rankings=["x", "y"],
            production_rankings=["y", "x"],
            overlap_at_5=0.5,
            ndcg_at_10=0.8,
            latency_ms=100,
        )
        assert result.model_id == "test"
        assert result.model_version == "2.0"
        assert len(result.shadow_rankings) == 2
        assert result.overlap_at_5 == 0.5
