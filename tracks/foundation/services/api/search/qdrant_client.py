"""
Qdrant vector search client wrapper.

Provides connection pooling, timeout enforcement, and API key auth
for all vector similarity searches against the activities collection.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
    SearchRequest,
)

from services.api.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "activity_nodes"
SEARCH_TIMEOUT_S = 3


class QdrantSearchClient:
    """Async Qdrant client with connection pooling and timeout."""

    def __init__(self) -> None:
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=SEARCH_TIMEOUT_S,
            )
        return self._client

    async def search(
        self,
        vector: list[float],
        city: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Search Qdrant for similar activity vectors.

        Always applies is_canonical=true filter. Additional filters
        (category, etc.) are merged in.

        Returns list of {"id": str, "score": float, "payload": dict}.
        """
        must_conditions = [
            FieldCondition(key="is_canonical", match=MatchValue(value=True)),
            FieldCondition(key="city", match=MatchValue(value=city.lower())),
        ]

        if filters:
            if "category" in filters:
                must_conditions.append(
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=filters["category"]),
                    )
                )

        qdrant_filter = Filter(must=must_conditions)

        client = await self._get_client()
        results = await client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=qdrant_filter,
            limit=limit,
            score_threshold=score_threshold,
            search_params=SearchParams(hnsw_ef=128, exact=False),
        )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload or {},
            }
            for hit in results
        ]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
