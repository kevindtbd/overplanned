"""
Redis-backed sliding window rate limiter.

Tiers:
  - Anonymous: 10 req/min
  - Authenticated: 60 req/min (general)
  - LLM-triggering endpoints: 5 req/min per user
  - /events/batch: 60 req/min per user
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from services.api.config import settings

# Endpoint-specific overrides (path prefix -> requests per minute)
LLM_PREFIXES = ("/ml/", "/llm/", "/generate/")
EVENTS_BATCH_PATH = "/events/batch"


def _get_rate_limit(path: str, is_authenticated: bool) -> tuple[int, str]:
    """Return (limit_per_min, tier_name) for the given path and auth state."""
    if path == EVENTS_BATCH_PATH:
        return settings.rate_limit_events_per_min, "events"
    for prefix in LLM_PREFIXES:
        if path.startswith(prefix):
            return settings.rate_limit_llm_per_min, "llm"
    if is_authenticated:
        return settings.rate_limit_auth_per_min, "auth"
    return settings.rate_limit_anon_per_min, "anon"


def _get_client_key(request: Request) -> tuple[str, bool]:
    """Extract client identifier and whether they're authenticated."""
    # Check for user ID set by auth middleware (future integration)
    user_id = request.state.__dict__.get("user_id")
    if user_id:
        return f"user:{user_id}", True
    # Fall back to IP
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    return f"ip:{client_ip}", False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter backed by Redis sorted sets."""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        if self.redis is None:
            return await call_next(request)

        client_key, is_authenticated = _get_client_key(request)
        limit, tier = _get_rate_limit(request.url.path, is_authenticated)
        window_key = f"ratelimit:{tier}:{client_key}"

        now = time.time()
        window_start = now - 60.0  # 1-minute sliding window

        pipe = self.redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(window_key, 0, window_start)
        # Count current entries
        pipe.zcard(window_key)
        # Add current request
        pipe.zadd(window_key, {f"{now}:{id(request)}": now})
        # Set TTL on the key
        pipe.expire(window_key, 120)
        results = await pipe.execute()

        current_count = results[1]

        # Build rate limit headers
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count - 1)),
            "X-RateLimit-Reset": str(int(now + 60)),
        }

        if current_count >= limit:
            retry_after = int(60 - (now - window_start))
            headers["Retry-After"] = str(max(1, retry_after))
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded. Max {limit} requests per minute for {tier} tier.",
                    },
                    "requestId": request.state.__dict__.get("request_id", ""),
                },
                headers=headers,
            )

        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value
        return response
