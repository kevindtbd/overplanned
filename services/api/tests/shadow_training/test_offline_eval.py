"""
Tests for Phase 4.3: Offline Evaluation Harness.

Covers:
- HR@5, MRR, NDCG@10 computation (per-query and aggregate)
- Promotion gate logic (pass/fail conditions)
- Test data loading from Parquet
- End-to-end eval pipeline
- Empty test data handling
- Model prediction failure handling
- Gate details structure
- DB storage of eval results
- Edge cases (single query, all hits, all misses)
"""

import math
import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.api.evaluation.offline_eval import (
    GATE_HR_AT_5,
    GATE_MRR,
    EvalResult,
    _check_gates,
    _compute_hr_at_k,
    _compute_ndcg_at_k,
    _compute_reciprocal_rank,
    _load_test_data,
    run_offline_eval,
)


# ---------------------------------------------------------------------------
# Mock model
# ---------------------------------------------------------------------------

@dataclass
class MockEvalModel:
    """Mock model for eval tests."""
    model_id: str = "eval-bpr-v1"
    model_version: str = "1.0.0"
    _predictions: dict | None = None
    _default_ranking: list[str] | None = None
    _should_fail: bool = False

    async def predict(self, user_id: str, context_items: list[str]) -> list[str]:
        if self._should_fail:
            raise RuntimeError("Model crashed")
        if self._predictions and user_id in self._predictions:
            return self._predictions[user_id]
        if self._default_ranking is not None:
            return self._default_ranking
        return context_items  # Echo back


def _make_pool(production_ndcg=None):
    """Build a mock asyncpg pool."""
    pool = AsyncMock()
    conn = AsyncMock()

    if production_ndcg is not None:
        conn.fetchrow = AsyncMock(return_value={"ndcgAt10": production_ndcg})
    else:
        conn.fetchrow = AsyncMock(return_value=None)

    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acm)

    return pool, conn


def _write_test_data(path, rows):
    """Write test data to a Parquet file."""
    table = pa.table({
        "user_id": [r["user_id"] for r in rows],
        "ground_truth_item_id": [r["ground_truth_item_id"] for r in rows],
        "context_items": [r["context_items"] for r in rows],
    })
    pq.write_table(table, path)


# ===========================================================================
# HR@5 tests
# ===========================================================================

class TestHrAtK:
    """Tests for Hit Rate @ K."""

    def test_hit_in_top_5(self):
        """Ground truth at position 3 is a hit."""
        rankings = ["a", "b", "target", "d", "e"]
        assert _compute_hr_at_k(rankings, "target", k=5) == 1.0

    def test_hit_at_position_1(self):
        """Ground truth at position 1 is a hit."""
        rankings = ["target", "b", "c"]
        assert _compute_hr_at_k(rankings, "target", k=5) == 1.0

    def test_miss_outside_top_5(self):
        """Ground truth at position 6 is a miss."""
        rankings = ["a", "b", "c", "d", "e", "target"]
        assert _compute_hr_at_k(rankings, "target", k=5) == 0.0

    def test_miss_not_in_list(self):
        """Ground truth not in rankings at all."""
        rankings = ["a", "b", "c"]
        assert _compute_hr_at_k(rankings, "target", k=5) == 0.0

    def test_empty_rankings(self):
        """Empty rankings = miss."""
        assert _compute_hr_at_k([], "target", k=5) == 0.0


# ===========================================================================
# MRR tests
# ===========================================================================

class TestReciprocalRank:
    """Tests for Mean Reciprocal Rank computation."""

    def test_rank_1(self):
        """Ground truth at rank 1 gives RR=1.0."""
        assert _compute_reciprocal_rank(["target", "b", "c"], "target") == 1.0

    def test_rank_2(self):
        """Ground truth at rank 2 gives RR=0.5."""
        assert _compute_reciprocal_rank(["a", "target", "c"], "target") == 0.5

    def test_rank_4(self):
        """Ground truth at rank 4 gives RR=0.25."""
        assert _compute_reciprocal_rank(["a", "b", "c", "target"], "target") == 0.25

    def test_not_found(self):
        """Ground truth not in rankings gives RR=0.0."""
        assert _compute_reciprocal_rank(["a", "b", "c"], "target") == 0.0

    def test_empty_rankings(self):
        """Empty rankings give RR=0.0."""
        assert _compute_reciprocal_rank([], "target") == 0.0


# ===========================================================================
# NDCG@10 tests
# ===========================================================================

class TestNdcgAtK:
    """Tests for NDCG@K with single relevant item."""

    def test_item_at_rank_1(self):
        """Ground truth at rank 1 gives NDCG=1.0."""
        rankings = ["target", "b", "c"]
        assert _compute_ndcg_at_k(rankings, "target", k=10) == pytest.approx(1.0)

    def test_item_at_rank_2(self):
        """Ground truth at rank 2 gives lower NDCG."""
        rankings = ["a", "target", "c"]
        ndcg = _compute_ndcg_at_k(rankings, "target", k=10)
        assert 0.0 < ndcg < 1.0
        # NDCG at rank 2: (1/log2(3)) / (1/log2(2)) = log2(2)/log2(3)
        expected = math.log2(2) / math.log2(3)
        assert ndcg == pytest.approx(expected, abs=0.001)

    def test_item_not_in_top_k(self):
        """Ground truth outside top-k gives NDCG=0.0."""
        rankings = ["a", "b", "c"]
        assert _compute_ndcg_at_k(rankings, "target", k=3) == 0.0

    def test_empty_rankings(self):
        """Empty rankings give NDCG=0.0."""
        assert _compute_ndcg_at_k([], "target", k=10) == 0.0

    def test_item_at_last_position(self):
        """Ground truth at position k has lowest non-zero NDCG."""
        rankings = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "target"]
        ndcg = _compute_ndcg_at_k(rankings, "target", k=10)
        assert ndcg > 0.0
        assert ndcg < _compute_ndcg_at_k(["target"] + rankings[:9], "target", k=10)


# ===========================================================================
# Gate check tests
# ===========================================================================

class TestCheckGates:
    """Tests for promotion gate logic."""

    def test_all_gates_pass(self):
        """All metrics above thresholds + better than production = pass."""
        passed, details = _check_gates(0.20, 0.10, 0.50, 0.40)
        assert passed is True
        assert details["hr_at_5"]["passed"] is True
        assert details["mrr"]["passed"] is True
        assert details["ndcg_at_10"]["passed"] is True

    def test_hr_gate_fails(self):
        """HR@5 below threshold fails all gates."""
        passed, details = _check_gates(0.10, 0.10, 0.50, 0.40)
        assert passed is False
        assert details["hr_at_5"]["passed"] is False

    def test_mrr_gate_fails(self):
        """MRR below threshold fails all gates."""
        passed, details = _check_gates(0.20, 0.05, 0.50, 0.40)
        assert passed is False
        assert details["mrr"]["passed"] is False

    def test_ndcg_gate_fails_worse_than_production(self):
        """NDCG worse than production fails the gate."""
        passed, details = _check_gates(0.20, 0.10, 0.30, 0.40)
        assert passed is False
        assert details["ndcg_at_10"]["passed"] is False

    def test_no_production_baseline_passes_ndcg_gate(self):
        """First model (no production baseline) passes NDCG gate by default."""
        passed, details = _check_gates(0.20, 0.10, 0.05, None)
        assert passed is True
        assert details["ndcg_at_10"]["passed"] is True
        assert details["ndcg_at_10"]["production_baseline"] is None

    def test_gate_details_structure(self):
        """Gate details contain value, threshold, and passed for each metric."""
        _, details = _check_gates(0.20, 0.10, 0.50, 0.40)
        for key in ["hr_at_5", "mrr"]:
            assert "value" in details[key]
            assert "threshold" in details[key]
            assert "passed" in details[key]
        assert "value" in details["ndcg_at_10"]
        assert "production_baseline" in details["ndcg_at_10"]

    def test_exact_threshold_passes(self):
        """Values exactly at threshold pass."""
        passed, _ = _check_gates(GATE_HR_AT_5, GATE_MRR, 0.50, 0.40)
        assert passed is True


# ===========================================================================
# Test data loading tests
# ===========================================================================

class TestLoadTestData:
    """Tests for Parquet test data loading."""

    def test_load_basic_data(self, tmp_path):
        """Loads Parquet file with expected columns."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "item-1", "context_items": ["a", "b"]},
            {"user_id": "u2", "ground_truth_item_id": "item-2", "context_items": ["c", "d"]},
        ]
        _write_test_data(fp, rows)

        data = _load_test_data(fp)
        assert len(data) == 2
        assert data[0]["user_id"] == "u1"
        assert data[0]["ground_truth_item_id"] == "item-1"
        assert data[0]["context_items"] == ["a", "b"]

    def test_empty_context_items(self, tmp_path):
        """Handles empty context_items lists."""
        fp = str(tmp_path / "empty_ctx.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "item-1", "context_items": []},
        ]
        _write_test_data(fp, rows)

        data = _load_test_data(fp)
        assert data[0]["context_items"] == []


# ===========================================================================
# End-to-end eval tests
# ===========================================================================

class TestRunOfflineEval:
    """Integration tests for the full eval pipeline."""

    async def test_perfect_model(self, tmp_path):
        """Model that always ranks ground truth first gets perfect scores."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "target-1", "context_items": ["a", "b"]},
            {"user_id": "u2", "ground_truth_item_id": "target-2", "context_items": ["c", "d"]},
        ]
        _write_test_data(fp, rows)

        model = MockEvalModel(
            _predictions={
                "u1": ["target-1", "a", "b"],
                "u2": ["target-2", "c", "d"],
            }
        )
        pool, conn = _make_pool(production_ndcg=None)

        result = await run_offline_eval(pool, model, fp, k=10)
        assert result.hr_at_5 == 1.0
        assert result.mrr == 1.0
        assert result.ndcg_at_10 == pytest.approx(1.0)
        assert result.total_queries == 2
        assert result.passed_gates is True

    async def test_zero_hit_model(self, tmp_path):
        """Model that never includes ground truth gets zero scores."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "target", "context_items": ["a", "b"]},
        ]
        _write_test_data(fp, rows)

        model = MockEvalModel(_default_ranking=["x", "y", "z"])
        pool, conn = _make_pool(production_ndcg=None)

        result = await run_offline_eval(pool, model, fp, k=10)
        assert result.hr_at_5 == 0.0
        assert result.mrr == 0.0
        assert result.ndcg_at_10 == 0.0
        assert result.passed_gates is False

    async def test_empty_test_data(self, tmp_path):
        """Empty test data returns zero metrics and fails gates."""
        fp = str(tmp_path / "empty.parquet")
        _write_test_data(fp, [])

        model = MockEvalModel()
        pool, conn = _make_pool()

        result = await run_offline_eval(pool, model, fp, k=10)
        assert result.total_queries == 0
        assert result.passed_gates is False

    async def test_model_failure_treated_as_miss(self, tmp_path):
        """Model prediction failure treated as empty ranking (miss)."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "target", "context_items": ["a"]},
        ]
        _write_test_data(fp, rows)

        model = MockEvalModel(_should_fail=True)
        pool, conn = _make_pool()

        result = await run_offline_eval(pool, model, fp, k=10)
        assert result.hr_at_5 == 0.0
        assert result.mrr == 0.0

    async def test_result_stored_in_db(self, tmp_path):
        """Eval result is persisted to EvalRun table."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "a", "context_items": ["a"]},
        ]
        _write_test_data(fp, rows)

        model = MockEvalModel(_default_ranking=["a"])
        pool, conn = _make_pool()

        await run_offline_eval(pool, model, fp, k=10)

        # CREATE TABLE + INSERT
        assert conn.execute.call_count >= 2

    async def test_duration_tracked(self, tmp_path):
        """Result includes duration_ms."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "a", "context_items": ["a"]},
        ]
        _write_test_data(fp, rows)

        model = MockEvalModel(_default_ranking=["a"])
        pool, conn = _make_pool()

        result = await run_offline_eval(pool, model, fp, k=10)
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    async def test_ndcg_gate_against_production(self, tmp_path):
        """NDCG gate compares against production baseline from DB."""
        fp = str(tmp_path / "test.parquet")
        rows = [
            {"user_id": "u1", "ground_truth_item_id": "target", "context_items": ["a"]},
        ]
        _write_test_data(fp, rows)

        # Model puts target at rank 1 -- NDCG=1.0
        model = MockEvalModel(_default_ranking=["target", "a"])
        # Production NDCG is 0.5, so candidate (1.0) > production (0.5) passes
        pool, conn = _make_pool(production_ndcg=0.5)

        result = await run_offline_eval(pool, model, fp, k=10)
        assert result.gate_details["ndcg_at_10"]["passed"] is True
        assert result.gate_details["ndcg_at_10"]["production_baseline"] == 0.5


# ===========================================================================
# EvalResult dataclass tests
# ===========================================================================

class TestEvalResultDataclass:

    def test_fields_accessible(self):
        result = EvalResult(
            model_id="m1",
            model_version="1.0",
            hr_at_5=0.2,
            mrr=0.1,
            ndcg_at_10=0.3,
            total_queries=100,
            duration_ms=500,
            passed_gates=True,
            gate_details={"hr_at_5": {"passed": True}},
        )
        assert result.model_id == "m1"
        assert result.total_queries == 100
        assert result.passed_gates is True
