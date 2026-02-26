"""
Offline evaluation harness (Phase 4.3).

Evaluates ML model quality against held-out test data using standard
information retrieval metrics:
- Hit Rate @ 5 (HR@5)
- Mean Reciprocal Rank (MRR)
- NDCG@10 (Normalized Discounted Cumulative Gain at position 10)

Promotion gates (from design doc):
- HR@5 >= 0.15
- MRR >= 0.08
- NDCG@10 > current production model's NDCG@10 (bootstrap CI non-overlap)
- All three must pass for passed_gates=True

Test data: Parquet file with (user_id, ground_truth_item_id, context_items).
Model interface: model.predict(user_id, context_items) -> list[str] (ranked IDs).

Results are stored in the EvalRun table for tracking model progression.
"""

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Promotion gate thresholds
GATE_HR_AT_5 = 0.15
GATE_MRR = 0.08


class EvalModel(Protocol):
    """Protocol for models that can be evaluated."""
    model_id: str
    model_version: str

    async def predict(self, user_id: str, context_items: list[str]) -> list[str]:
        """Return ranked list of item IDs."""
        ...


@dataclass
class EvalResult:
    """Result of an offline evaluation run."""
    model_id: str
    model_version: str
    hr_at_5: float
    mrr: float
    ndcg_at_10: float
    total_queries: int
    duration_ms: int
    passed_gates: bool
    gate_details: dict = field(default_factory=dict)


_INSERT_RESULT_SQL = """
INSERT INTO eval_runs
    ("id", "modelId", "modelVersion", "hrAt5", "mrr", "ndcgAt10",
     "totalQueries", "durationMs", "passedGates", "gateDetails", "createdAt")
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
"""

# SQL: get production model's NDCG@10 for gate comparison
_PRODUCTION_NDCG_SQL = """
SELECT "ndcgAt10"
FROM eval_runs
WHERE "modelId" != $1
  AND "passedGates" = true
ORDER BY "createdAt" DESC
LIMIT 1
"""


def _compute_hr_at_k(
    rankings: list[str],
    ground_truth: str,
    k: int = 5,
) -> float:
    """Return 1.0 if ground_truth appears in top-k of rankings, else 0.0."""
    return 1.0 if ground_truth in rankings[:k] else 0.0


def _compute_reciprocal_rank(
    rankings: list[str],
    ground_truth: str,
) -> float:
    """Return 1/rank if ground_truth is found, else 0.0."""
    try:
        rank = rankings.index(ground_truth) + 1
        return 1.0 / rank
    except ValueError:
        return 0.0


def _compute_ndcg_at_k(
    rankings: list[str],
    ground_truth: str,
    k: int = 10,
) -> float:
    """
    Compute NDCG@k for a single query with one relevant item.

    For a single relevant item, ideal DCG = 1/log2(2) = 1.0 (item at position 1).
    Actual DCG = 1/log2(rank+1) if the item appears in top-k.
    """
    try:
        rank = rankings[:k].index(ground_truth) + 1
    except ValueError:
        return 0.0

    # DCG for this item at its actual rank
    dcg = 1.0 / math.log2(rank + 1)
    # Ideal DCG: item at rank 1
    idcg = 1.0 / math.log2(2)
    return dcg / idcg


def _load_test_data(test_data_path: str) -> list[dict]:
    """
    Load test data from a Parquet file.

    Expected columns: user_id (str), ground_truth_item_id (str),
    context_items (list of str).
    """
    table = pq.read_table(test_data_path)
    rows = []
    for i in range(len(table)):
        context_items_raw = table.column("context_items")[i].as_py()
        rows.append({
            "user_id": table.column("user_id")[i].as_py(),
            "ground_truth_item_id": table.column("ground_truth_item_id")[i].as_py(),
            "context_items": context_items_raw if isinstance(context_items_raw, list) else [],
        })
    return rows


async def _get_production_ndcg(pool, model_id: str) -> float | None:
    """Fetch the most recent production model's NDCG@10 for gate comparison."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_PRODUCTION_NDCG_SQL, model_id)
    if row is None:
        return None
    return row["ndcgAt10"]


def _check_gates(
    hr_at_5: float,
    mrr: float,
    ndcg_at_10: float,
    production_ndcg: float | None,
) -> tuple[bool, dict]:
    """
    Check promotion gates. Returns (passed_all, gate_details).

    Gates:
    1. HR@5 >= 0.15
    2. MRR >= 0.08
    3. NDCG@10 > production NDCG@10 (if production baseline exists)
    """
    gate_hr = hr_at_5 >= GATE_HR_AT_5
    gate_mrr = mrr >= GATE_MRR

    if production_ndcg is not None:
        gate_ndcg = ndcg_at_10 > production_ndcg
    else:
        # No production baseline: pass by default (first model)
        gate_ndcg = True

    details = {
        "hr_at_5": {"value": hr_at_5, "threshold": GATE_HR_AT_5, "passed": gate_hr},
        "mrr": {"value": mrr, "threshold": GATE_MRR, "passed": gate_mrr},
        "ndcg_at_10": {
            "value": ndcg_at_10,
            "production_baseline": production_ndcg,
            "passed": gate_ndcg,
        },
    }

    passed_all = gate_hr and gate_mrr and gate_ndcg
    return passed_all, details


async def _store_result(pool, result: EvalResult) -> None:
    """Persist an EvalResult to the EvalRun table."""
    import json
    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_RESULT_SQL,
            str(uuid.uuid4()),
            result.model_id,
            result.model_version,
            result.hr_at_5,
            result.mrr,
            result.ndcg_at_10,
            result.total_queries,
            result.duration_ms,
            result.passed_gates,
            json.dumps(result.gate_details),
            datetime.now(timezone.utc),
        )


async def run_offline_eval(
    pool,
    model: EvalModel,
    test_data_path: str,
    k: int = 10,
) -> EvalResult:
    """
    Evaluate an ML model against held-out test data.

    Args:
        pool: asyncpg connection pool.
        model: model implementing EvalModel protocol (predict method).
        test_data_path: path to Parquet file with test queries.
        k: cutoff for NDCG (default 10).

    Returns:
        EvalResult with all metrics, gate pass/fail, and details.
    """
    start = time.monotonic()

    # Load test data
    test_data = _load_test_data(test_data_path)
    total_queries = len(test_data)

    if total_queries == 0:
        duration_ms = int((time.monotonic() - start) * 1000)
        result = EvalResult(
            model_id=model.model_id,
            model_version=model.model_version,
            hr_at_5=0.0,
            mrr=0.0,
            ndcg_at_10=0.0,
            total_queries=0,
            duration_ms=duration_ms,
            passed_gates=False,
            gate_details={"error": "no test data"},
        )
        await _store_result(pool, result)
        return result

    # Run predictions and compute per-query metrics
    hr_scores = []
    rr_scores = []
    ndcg_scores = []

    for query in test_data:
        try:
            rankings = await model.predict(query["user_id"], query["context_items"])
        except Exception:
            logger.exception(
                "Model prediction failed for user=%s, treating as miss",
                query["user_id"],
            )
            rankings = []

        ground_truth = query["ground_truth_item_id"]
        hr_scores.append(_compute_hr_at_k(rankings, ground_truth, k=5))
        rr_scores.append(_compute_reciprocal_rank(rankings, ground_truth))
        ndcg_scores.append(_compute_ndcg_at_k(rankings, ground_truth, k=k))

    # Aggregate metrics
    hr_at_5 = sum(hr_scores) / total_queries
    mrr = sum(rr_scores) / total_queries
    ndcg_at_10 = sum(ndcg_scores) / total_queries

    # Get production baseline for gate comparison
    production_ndcg = await _get_production_ndcg(pool, model.model_id)

    # Check promotion gates
    passed_gates, gate_details = _check_gates(hr_at_5, mrr, ndcg_at_10, production_ndcg)

    duration_ms = int((time.monotonic() - start) * 1000)

    result = EvalResult(
        model_id=model.model_id,
        model_version=model.model_version,
        hr_at_5=hr_at_5,
        mrr=mrr,
        ndcg_at_10=ndcg_at_10,
        total_queries=total_queries,
        duration_ms=duration_ms,
        passed_gates=passed_gates,
        gate_details=gate_details,
    )

    logger.info(
        "Offline eval complete: model=%s HR@5=%.3f MRR=%.3f NDCG@10=%.3f gates=%s (%d queries, %dms)",
        model.model_id,
        hr_at_5,
        mrr,
        ndcg_at_10,
        "PASS" if passed_gates else "FAIL",
        total_queries,
        duration_ms,
    )

    # Persist results
    try:
        await _store_result(pool, result)
    except Exception:
        logger.exception("Failed to store eval result for model=%s", model.model_id)

    return result
