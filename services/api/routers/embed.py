"""
Embedding endpoints for vector generation.

POST /embed/batch — batch embed up to 100 texts
POST /embed/query — single query embedding (fast path for search)
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.api.embedding.service import embedding_service

router = APIRouter(prefix="/embed", tags=["embedding"])

_MAX_BATCH_SIZE = 100


class BatchEmbedRequest(BaseModel):
    texts: list[str] = Field(max_length=_MAX_BATCH_SIZE)
    is_query: bool = False
    batch_size: int = Field(default=32, ge=1, le=128)


class QueryEmbedRequest(BaseModel):
    text: str


class BatchEmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    dimensions: int
    count: int


class QueryEmbedResponse(BaseModel):
    vector: list[float]
    model: str
    dimensions: int


@router.post("/batch")
async def embed_batch(body: BatchEmbedRequest, request: Request) -> dict:
    """Batch embed up to 100 texts. Returns 768-dim L2-normalized vectors."""
    if not body.texts:
        return {
            "success": True,
            "data": {
                "vectors": [],
                "model": embedding_service.model_name,
                "dimensions": embedding_service.dimensions,
                "count": 0,
            },
            "requestId": request.state.request_id,
        }

    vectors = embedding_service.embed_batch(
        body.texts,
        batch_size=body.batch_size,
        is_query=body.is_query,
    )

    return {
        "success": True,
        "data": {
            "vectors": vectors,
            "model": embedding_service.model_name,
            "dimensions": embedding_service.dimensions,
            "count": len(vectors),
        },
        "requestId": request.state.request_id,
    }


@router.post("/query")
async def embed_query(body: QueryEmbedRequest, request: Request) -> dict:
    """Embed a single search query. Fast path for real-time search."""
    vector = embedding_service.embed_single(body.text, is_query=True)

    return {
        "success": True,
        "data": {
            "vector": vector,
            "model": embedding_service.model_name,
            "dimensions": embedding_service.dimensions,
        },
        "requestId": request.state.request_id,
    }
