"""
Shadow mode infrastructure (Phase 4.2).

Runs a candidate ML model in parallel with the production LLM ranker,
logging comparison results without affecting the user experience.

The shadow model's predictions are compared against production rankings
using overlap@5 and NDCG@10 metrics. Results are stored in the ShadowResult
table for offline analysis.

Feature-flagged via SHADOW_MODE_ENABLED env var (default: False).
When disabled, run_shadow returns None with zero overhead.
When enabled, shadow inference runs as a fire-and-forget asyncio task
so it never blocks the production response path.
"""

import asyncio
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Feature flag
SHADOW_MODE_ENABLED = os.environ.get("SHADOW_MODE_ENABLED", "false").lower() in ("true", "1", "yes")


class ShadowModel(Protocol):
    """Protocol for models that can be run in shadow mode."""
    model_id: str
    model_version: str

    async def predict(self, user_id: str, context_items: list[str]) -> list[str]:
        """Return ranked list of activity node IDs."""
        ...


@dataclass
class ShadowResult:
    """Result of a shadow model run compared against production rankings."""
    model_id: str
    model_version: str
    shadow_rankings: list[str]
    production_rankings: list[str]
    overlap_at_5: float
    ndcg_at_10: float
    latency_ms: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# SQL: ensure the ShadowResult table exists
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "ShadowResult" (
    "id" TEXT PRIMARY KEY,
    "modelId" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "shadowRankings" JSONB NOT NULL,
    "productionRankings" JSONB NOT NULL,
    "overlapAt5" DOUBLE PRECISION NOT NULL,
    "ndcgAt10" DOUBLE PRECISION NOT NULL,
    "latencyMs" INTEGER NOT NULL,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_INSERT_RESULT_SQL = """
INSERT INTO "ShadowResult"
    ("id", "modelId", "modelVersion", "userId", "tripId",
     "shadowRankings", "productionRankings", "overlapAt5", "ndcgAt10",
     "latencyMs", "createdAt")
VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11)
"""

_GET_SHADOW_MODEL_SQL = """
SELECT "modelName", "modelVersion", "artifactPath", "configSnapshot"
FROM "ModelRegistry"
WHERE "stage" = 'shadow'
ORDER BY "createdAt" DESC
LIMIT 1
"""


def compute_overlap_at_k(
    shadow: list[str],
    production: list[str],
    k: int = 5,
) -> float:
    """
    Compute overlap@k: fraction of top-k shadow items that appear in
    top-k production items.
    """
    if not shadow or not production:
        return 0.0
    shadow_top = set(shadow[:k])
    prod_top = set(production[:k])
    if not shadow_top:
        return 0.0
    return len(shadow_top & prod_top) / len(shadow_top)


def compute_ndcg_at_k(
    shadow: list[str],
    production: list[str],
    k: int = 10,
) -> float:
    """
    Compute NDCG@k using production rankings as the ground truth relevance.

    Relevance of a shadow item at position i is based on its position in the
    production ranking (higher production rank = higher relevance).
    """
    if not shadow or not production:
        return 0.0

    # Build relevance map: production rank -> relevance score
    # Item at production position 0 gets highest relevance
    prod_len = len(production)
    relevance_map: dict[str, float] = {}
    for idx, item_id in enumerate(production):
        relevance_map[item_id] = max(0.0, prod_len - idx)

    # DCG for shadow ranking
    dcg = 0.0
    for i, item_id in enumerate(shadow[:k]):
        rel = relevance_map.get(item_id, 0.0)
        dcg += rel / math.log2(i + 2)  # i+2 because log2(1) = 0

    # Ideal DCG: sort by relevance descending
    ideal_rels = sorted(
        [relevance_map.get(item_id, 0.0) for item_id in shadow[:k]],
        reverse=True,
    )
    # But we should also consider items NOT in shadow that have higher relevance
    all_rels = sorted(relevance_map.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(all_rels):
        idcg += rel / math.log2(i + 2)

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


class ShadowRunner:
    """
    Runs a shadow ML model alongside the production ranker.

    Usage:
        runner = ShadowRunner(pool=db_pool)
        # Fire-and-forget: does not block production path
        runner.run_shadow_detached(user_id, trip_id, candidates, prod_rankings)

        # Or await result directly (for testing):
        result = await runner.run_shadow(user_id, trip_id, candidates, prod_rankings)
    """

    def __init__(self, pool, model: ShadowModel | None = None):
        self._pool = pool
        self._model = model
        self._table_ensured = False

    async def _ensure_table(self) -> None:
        """Create the ShadowResult table if it does not exist."""
        if self._table_ensured:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)
        self._table_ensured = True

    async def _get_shadow_model_info(self) -> dict | None:
        """Fetch the active shadow model from ModelRegistry."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_GET_SHADOW_MODEL_SQL)
        if row is None:
            return None
        return dict(row)

    async def _store_result(
        self,
        user_id: str,
        trip_id: str,
        result: ShadowResult,
    ) -> None:
        """Persist a ShadowResult to the database."""
        await self._ensure_table()
        import json
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_RESULT_SQL,
                str(uuid.uuid4()),
                result.model_id,
                result.model_version,
                user_id,
                trip_id,
                json.dumps(result.shadow_rankings),
                json.dumps(result.production_rankings),
                result.overlap_at_5,
                result.ndcg_at_10,
                result.latency_ms,
                result.created_at,
            )

    async def run_shadow(
        self,
        user_id: str,
        trip_id: str,
        candidates: list[str],
        production_rankings: list[str],
    ) -> ShadowResult | None:
        """
        Run shadow model prediction and compare against production.

        Returns None if shadow mode is disabled or no shadow model is registered.
        """
        if not SHADOW_MODE_ENABLED and self._model is None:
            return None

        model = self._model
        if model is None:
            # No externally provided model -- check ModelRegistry
            model_info = await self._get_shadow_model_info()
            if model_info is None:
                logger.debug("No active shadow model in ModelRegistry")
                return None
            # In production, we'd load the model from artifactPath.
            # For now, log and return None if no model object is set.
            logger.warning(
                "Shadow model %s found in registry but no model object loaded",
                model_info.get("modelName"),
            )
            return None

        start = time.monotonic()
        try:
            shadow_rankings = await model.predict(user_id, candidates)
        except Exception:
            logger.exception("Shadow model prediction failed for user=%s trip=%s", user_id, trip_id)
            return None

        latency_ms = int((time.monotonic() - start) * 1000)

        overlap = compute_overlap_at_k(shadow_rankings, production_rankings, k=5)
        ndcg = compute_ndcg_at_k(shadow_rankings, production_rankings, k=10)

        result = ShadowResult(
            model_id=model.model_id,
            model_version=model.model_version,
            shadow_rankings=shadow_rankings,
            production_rankings=production_rankings,
            overlap_at_5=overlap,
            ndcg_at_10=ndcg,
            latency_ms=latency_ms,
        )

        try:
            await self._store_result(user_id, trip_id, result)
        except Exception:
            logger.exception("Failed to store shadow result for user=%s trip=%s", user_id, trip_id)

        logger.info(
            "Shadow run complete: model=%s overlap@5=%.3f ndcg@10=%.3f latency=%dms",
            model.model_id,
            overlap,
            ndcg,
            latency_ms,
        )

        return result

    def run_shadow_detached(
        self,
        user_id: str,
        trip_id: str,
        candidates: list[str],
        production_rankings: list[str],
    ) -> asyncio.Task | None:
        """
        Fire-and-forget shadow run. Returns the Task (for testing) or None
        if shadow mode is disabled.

        MUST NOT block or delay the production response.
        """
        if not SHADOW_MODE_ENABLED and self._model is None:
            return None

        task = asyncio.create_task(
            self.run_shadow(user_id, trip_id, candidates, production_rankings),
            name=f"shadow-{user_id}-{trip_id}",
        )

        # Log exceptions from the background task without crashing
        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error("Shadow task failed: %s", exc, exc_info=exc)

        task.add_done_callback(_on_done)
        return task
