"""
ActivitySearchService — reusable search pipeline.

Qdrant vector search -> Postgres batch hydration -> merge.
Used by itinerary generation, discover, pivot alternatives, micro-stops.

Graceful degradation:
- Qdrant timeout -> return empty results with warning
- Postgres timeout -> return Qdrant-only results (payload fields, no DB enrichment)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from services.api.search.qdrant_client import QdrantSearchClient
from services.api.search.hydrator import hydrate_activity_nodes

logger = logging.getLogger(__name__)

# Postgres hydration timeout
HYDRATION_TIMEOUT_S = 5


class ActivitySearchService:
    """
    Unified search interface for all downstream consumers.

    Usage:
        service = ActivitySearchService(qdrant_client, db_pool, embed_fn)
        results = await service.search("quiet coffee shop", city="austin")
    """

    def __init__(
        self,
        qdrant: QdrantSearchClient,
        db,
        embed_fn,
        score_threshold: float = 0.5,
    ) -> None:
        self._qdrant = qdrant
        self._db = db
        self._embed_fn = embed_fn
        self._score_threshold = score_threshold

    async def search(
        self,
        query: str,
        city: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        score_threshold: float | None = None,
    ) -> dict[str, Any]:
        """
        Search for activities matching a natural-language query.

        Returns:
            {
                "results": List[HydratedActivityNode],
                "count": int,
                "warning": str | None,
            }
        """
        threshold = score_threshold if score_threshold is not None else self._score_threshold
        warning: str | None = None

        # Step 1: Embed query
        vector = await self._embed_fn(query)

        # Step 2: Qdrant vector search
        try:
            qdrant_hits = await self._qdrant.search(
                vector=vector,
                city=city,
                filters=filters,
                limit=limit,
                score_threshold=threshold,
            )
        except Exception:
            logger.exception("Qdrant search failed for query=%r city=%r", query, city)
            return {
                "results": [],
                "count": 0,
                "warning": "Vector search unavailable. Please try again.",
            }

        if not qdrant_hits:
            return {"results": [], "count": 0, "warning": None}

        node_ids = [hit["id"] for hit in qdrant_hits]

        # Step 3: Postgres batch hydration
        hydrated: dict[str, dict[str, Any]] = {}
        try:
            hydrated = await asyncio.wait_for(
                hydrate_activity_nodes(self._db, node_ids),
                timeout=HYDRATION_TIMEOUT_S,
            )
        except (asyncio.TimeoutError, Exception):
            logger.exception("Postgres hydration failed, returning Qdrant-only results")
            warning = "Results may be less detailed due to database timeout."

        # Step 4: Merge — Qdrant payload + DB fields, preserving Qdrant score order
        results: list[dict[str, Any]] = []
        for hit in qdrant_hits:
            node_id = hit["id"]
            db_data = hydrated.get(node_id)

            if db_data:
                merged = {**db_data, "score": hit["score"]}
            else:
                # Qdrant-only fallback: payload fields + score
                merged = {
                    "id": node_id,
                    "score": hit["score"],
                    **hit["payload"],
                    "vibeTags": [],
                    "qualitySignals": [],
                }

            results.append(merged)

        return {
            "results": results,
            "count": len(results),
            "warning": warning,
        }
