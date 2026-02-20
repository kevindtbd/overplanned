"""
Overplanned FastAPI service — ML, scraping, search, and event ingestion.

Entrypoint: uvicorn services.api.main:app --host 0.0.0.0 --port 8000
"""

import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from starlette.responses import JSONResponse

from services.api.config import settings
from services.api.middleware.cors import setup_cors
from services.api.middleware.rate_limit import RateLimitMiddleware
from services.api.middleware.sentry import setup_sentry
from services.api.routers import health, events, embed, search
from services.api.search.qdrant_client import QdrantSearchClient
from services.api.search.service import ActivitySearchService


# Shared redis reference — set during lifespan, read by rate limiter
_redis_holder: dict = {"client": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    setup_sentry()

    # Redis for rate limiting
    redis_client = None
    if settings.redis_url:
        try:
            redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await redis_client.ping()
        except Exception:
            # Rate limiting degrades gracefully — requests pass through
            redis_client = None

    _redis_holder["client"] = redis_client
    app.state.redis = redis_client
    app.state.settings = settings
    # DB pool placeholder — wired by database migration task
    app.state.db = None

    # Search service — Qdrant client + embedding + DB hydration
    qdrant_client = QdrantSearchClient()

    from services.api.embedding.service import embedding_service

    async def _embed_fn(text: str) -> list[float]:
        return embedding_service.embed_single(text, is_query=True)

    app.state.qdrant = qdrant_client
    app.state.search_service = ActivitySearchService(
        qdrant=qdrant_client,
        db=app.state.db,
        embed_fn=_embed_fn,
        score_threshold=settings.search_score_threshold,
    )

    yield

    await qdrant_client.close()
    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title="Overplanned API",
    version=settings.app_version,
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# -- Middleware (order matters: last added = outermost in Starlette) --

# Routers first (innermost)
app.include_router(health.router)
app.include_router(events.router)
app.include_router(embed.router)
app.include_router(search.router)

# CORS (needs to be outermost to handle preflight)
setup_cors(app)


# Request ID injection + body size enforcement
@app.middleware("http")
async def request_envelope_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    # Enforce request body size limit for events batch
    if request.url.path == "/events/batch" and request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.events_request_max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Request body exceeds {settings.events_request_max_bytes} bytes.",
                    },
                    "requestId": request_id,
                },
            )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Rate limiting — uses lazy redis reference from lifespan
class _LazyRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiter that picks up Redis client after lifespan init."""

    def __init__(self, app):
        super().__init__(app, redis_client=None)

    async def dispatch(self, request, call_next):
        self.redis = _redis_holder.get("client")
        return await super().dispatch(request, call_next)


app.add_middleware(_LazyRateLimitMiddleware)


# -- Exception Handlers --

@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Resource not found."},
            "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
        },
    )


@app.exception_handler(422)
async def validation_error_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(exc.detail) if hasattr(exc, "detail") else "Validation error.",
            },
            "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
            "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
        },
    )
