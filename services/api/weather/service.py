"""
WeatherService — OpenWeatherMap client with Redis caching.

Budget: 1,000 free API calls/day (~41/hour).
Cache strategy: per-city per-hour (WeatherCache), so all trips in the same
city share one API call per hour regardless of trip count.

Outdoor category detection:
  ActivityCategory.outdoors and ActivityCategory.active are flagged as outdoor.
  Rain condition codes 500-531 and storm codes 200-232 trigger weather alerts.

BehavioralSignal.weatherContext is populated as a compact JSON string:
  '{"condition": "rain", "code": 501, "temp_c": 18.2, "outdoor_risk": true}'

OpenWeatherMap /weather endpoint returns:
  {
    "weather": [{"id": 501, "main": "Rain", "description": "moderate rain"}],
    "main":    {"temp": 291.35, ...},
    "name":    "Tokyo",
    ...
  }
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from services.api.weather.cache import WeatherCache

logger = logging.getLogger(__name__)

# OpenWeatherMap condition code ranges
_RAIN_CODES    = range(500, 532)   # Rain (light -> heavy -> shower)
_STORM_CODES   = range(200, 233)   # Thunderstorm
_SNOW_CODES    = range(600, 623)   # Snow — treated as outdoor risk in warm destinations
_DRIZZLE_CODES = range(300, 322)   # Drizzle

# Activity categories that are affected by weather
_OUTDOOR_CATEGORIES = {"outdoors", "active"}

# API endpoint
_OWM_BASE = "https://api.openweathermap.org/data/2.5"
_WEATHER_ENDPOINT = f"{_OWM_BASE}/weather"

# HTTP timeout for OpenWeatherMap calls
_API_TIMEOUT_S = 8.0


def _kelvin_to_celsius(k: float) -> float:
    return round(k - 273.15, 1)


def _is_bad_weather(condition_code: int) -> bool:
    """Return True if the condition code represents rain, drizzle, or storms."""
    return (
        condition_code in _RAIN_CODES
        or condition_code in _STORM_CODES
        or condition_code in _DRIZZLE_CODES
    )


def _parse_condition(owm_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Extract a compact weather summary from the OpenWeatherMap /weather response.

    Returns:
        {
            "condition": "rain" | "storm" | "drizzle" | "snow" | "clear" | "clouds" | ...,
            "code":      int (OWM condition id),
            "temp_c":    float,
            "description": str,
        }
    """
    weather_list = owm_payload.get("weather", [{}])
    primary = weather_list[0] if weather_list else {}

    code = primary.get("id", 800)          # 800 = clear sky (default)
    main = primary.get("main", "Clear")    # "Rain", "Clouds", etc.
    description = primary.get("description", "clear sky")

    temp_kelvin = owm_payload.get("main", {}).get("temp", 293.0)
    temp_c = _kelvin_to_celsius(temp_kelvin)

    condition = main.lower()  # normalise to lowercase for consistency

    return {
        "condition": condition,
        "code": code,
        "temp_c": temp_c,
        "description": description,
    }


class WeatherService:
    """
    OpenWeatherMap client with Redis cache.

    Usage:
        service = WeatherService(api_key="...", cache=WeatherCache(redis))
        summary = await service.get_weather("Tokyo")
        context = service.build_weather_context(summary, slot_category="outdoors")
    """

    def __init__(self, api_key: str, cache: WeatherCache) -> None:
        """
        Args:
            api_key: OpenWeatherMap API key (OPENWEATHERMAP_API_KEY env var).
            cache:   WeatherCache instance backed by Redis.
        """
        self._api_key = api_key
        self._cache = cache

    async def get_weather(self, city: str) -> dict[str, Any] | None:
        """
        Fetch current weather for a city, using the Redis cache.

        Returns a parsed weather summary dict or None if the API is unreachable.

        Cache strategy:
          - Check Redis first (key: weather:{city_slug}:{hour})
          - On hit: deserialise and return
          - On miss: call OpenWeatherMap, cache the raw response, return parsed summary

        Errors are logged and return None — callers must handle None gracefully.
        """
        # Check cache first
        cached = await self._cache.get(city)
        if cached is not None:
            return _parse_condition(cached)

        # Cache miss — call OpenWeatherMap
        if not self._api_key:
            logger.warning("OPENWEATHERMAP_API_KEY not set; skipping weather fetch for %r", city)
            return None

        try:
            async with httpx.AsyncClient(timeout=_API_TIMEOUT_S) as client:
                resp = await client.get(
                    _WEATHER_ENDPOINT,
                    params={
                        "q": city,
                        "appid": self._api_key,
                    },
                )
                resp.raise_for_status()
                raw = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenWeatherMap returned %d for city=%r: %s",
                exc.response.status_code,
                city,
                exc.response.text[:200],
            )
            return None
        except Exception:
            logger.exception("OpenWeatherMap fetch failed for city=%r", city)
            return None

        # Store raw payload in cache (TTL 1 hour)
        await self._cache.set(city, raw)

        return _parse_condition(raw)

    def is_outdoor_slot(self, category: str) -> bool:
        """Return True if the activity category is weather-sensitive."""
        return category.lower() in _OUTDOOR_CATEGORIES

    def build_weather_context(
        self,
        weather_summary: dict[str, Any] | None,
        slot_category: str,
    ) -> str | None:
        """
        Build the compact JSON string stored in BehavioralSignal.weatherContext.

        Returns None if weather data is unavailable.

        Output format:
            '{"condition": "rain", "code": 501, "temp_c": 18.2, "outdoor_risk": true}'
        """
        if weather_summary is None:
            return None

        code = weather_summary.get("code", 800)
        outdoor_risk = self.is_outdoor_slot(slot_category) and _is_bad_weather(code)

        context = {
            "condition": weather_summary.get("condition", "unknown"),
            "code": code,
            "temp_c": weather_summary.get("temp_c", 0.0),
            "outdoor_risk": outdoor_risk,
        }
        return json.dumps(context, separators=(",", ":"))

    def should_trigger_weather_pivot(
        self,
        weather_summary: dict[str, Any] | None,
        slot_category: str,
    ) -> bool:
        """
        Return True if this weather + slot category combination warrants a pivot.

        Conditions:
          - Slot is an outdoor category (outdoors, active)
          - AND current weather has rain, drizzle, or storm codes
        """
        if weather_summary is None:
            return False

        if not self.is_outdoor_slot(slot_category):
            return False

        code = weather_summary.get("code", 800)
        return _is_bad_weather(code)
