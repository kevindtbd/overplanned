"""
Weather cache — Redis-backed, keyed per city per hour.

Cache key format:  weather:{city_slug}:{YYYYMMDD_HH}
TTL:               3600 seconds (1 hour)

Multiple concurrent trips in the same city share a single cached response,
keeping us within the 1,000 calls/day free tier on OpenWeatherMap.

City slug normalisation:
  "New York"  ->  "new-york"
  "São Paulo" ->  "sao-paulo"

The raw OpenWeatherMap /weather JSON is cached verbatim so WeatherService
can parse whatever fields it needs without extra round-trips.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 1 hour TTL — aligns with the hourly cache key so entries naturally expire
# one hour after they were written at most.
_TTL_SECONDS = 3600


def _slugify(city: str) -> str:
    """Normalise a city name to an ASCII slug for use in Redis keys.

    'São Paulo' -> 'sao-paulo'
    'New York'  -> 'new-york'
    """
    # Decompose unicode, strip combining characters (accents)
    normalised = unicodedata.normalize("NFKD", city)
    ascii_str = normalised.encode("ascii", "ignore").decode("ascii")
    # Lowercase, replace non-alphanumeric runs with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")
    return slug or "unknown"


def _hour_bucket() -> str:
    """Return the current UTC hour as a string: YYYYMMDD_HH."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d_%H")


def _cache_key(city: str, hour_bucket: str | None = None) -> str:
    """Build the Redis key for a city + hour combination."""
    bucket = hour_bucket or _hour_bucket()
    return f"weather:{_slugify(city)}:{bucket}"


class WeatherCache:
    """
    Redis-backed weather cache.

    Usage:
        cache = WeatherCache(redis_client)
        data = await cache.get("Tokyo")
        if data is None:
            data = await fetch_from_api(...)
            await cache.set("Tokyo", data)
    """

    def __init__(self, redis) -> None:
        """
        Args:
            redis: An async Redis client (redis.asyncio compatible).
                   May be None — all operations degrade gracefully to cache misses.
        """
        self._redis = redis

    async def get(self, city: str) -> dict[str, Any] | None:
        """Return cached weather payload for city, or None on miss / unavailable."""
        if self._redis is None:
            return None

        key = _cache_key(city)
        try:
            raw = await self._redis.get(key)
            if raw is None:
                logger.debug("Weather cache miss: %s", key)
                return None
            logger.debug("Weather cache hit: %s", key)
            return json.loads(raw)
        except Exception:
            logger.warning("Weather cache GET failed for key=%s", key, exc_info=True)
            return None

    async def set(self, city: str, payload: dict[str, Any]) -> None:
        """Write weather payload to Redis with a 1-hour TTL."""
        if self._redis is None:
            return

        key = _cache_key(city)
        try:
            await self._redis.set(key, json.dumps(payload), ex=_TTL_SECONDS)
            logger.debug("Weather cached: key=%s ttl=%ds", key, _TTL_SECONDS)
        except Exception:
            logger.warning("Weather cache SET failed for key=%s", key, exc_info=True)

    async def invalidate(self, city: str) -> None:
        """Force-evict a city's current-hour cache entry (useful in tests)."""
        if self._redis is None:
            return

        key = _cache_key(city)
        try:
            await self._redis.delete(key)
            logger.debug("Weather cache invalidated: %s", key)
        except Exception:
            logger.warning("Weather cache DELETE failed for key=%s", key, exc_info=True)
