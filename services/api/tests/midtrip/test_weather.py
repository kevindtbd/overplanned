"""
Tests for WeatherService and WeatherCache.

All tests run without external services — OpenWeatherMap and Redis are mocked.

Coverage targets:
  - Cache hit/miss/TTL logic
  - OWM API call lifecycle (happy path + HTTP errors + network failures)
  - Kelvin -> Celsius conversion
  - Rain/storm/drizzle condition detection
  - Outdoor category identification
  - BehavioralSignal.weatherContext string construction
  - should_trigger_weather_pivot logic
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.weather.cache import WeatherCache, _slugify, _cache_key
from services.api.weather.service import (
    WeatherService,
    _kelvin_to_celsius,
    _is_bad_weather,
    _parse_condition,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_owm_response(
    condition_id: int = 800,
    condition_main: str = "Clear",
    condition_desc: str = "clear sky",
    temp_kelvin: float = 295.0,
) -> dict[str, Any]:
    """Factory for OpenWeatherMap /weather response dicts."""
    return {
        "weather": [{"id": condition_id, "main": condition_main, "description": condition_desc}],
        "main": {"temp": temp_kelvin, "feels_like": temp_kelvin - 2, "humidity": 60},
        "name": "TestCity",
        "cod": 200,
    }


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def weather_cache(mock_redis):
    return WeatherCache(redis=mock_redis)


@pytest.fixture
def weather_service(weather_cache):
    return WeatherService(api_key="test-key-123", cache=weather_cache)


# ---------------------------------------------------------------------------
# WeatherCache unit tests
# ---------------------------------------------------------------------------

class TestWeatherCacheSlugify:
    def test_simple_city(self):
        assert _slugify("Tokyo") == "tokyo"

    def test_city_with_spaces(self):
        assert _slugify("New York") == "new-york"

    def test_accented_city(self):
        result = _slugify("São Paulo")
        assert result == "sao-paulo"

    def test_already_slug(self):
        assert _slugify("paris") == "paris"

    def test_empty_string(self):
        assert _slugify("") == "unknown"

    def test_special_characters_stripped(self):
        result = _slugify("Ko'olau, Oahu!")
        assert "-" in result
        assert "'" not in result


class TestWeatherCacheKey:
    def test_key_format(self):
        key = _cache_key("Tokyo", hour_bucket="20260220_14")
        assert key == "weather:tokyo:20260220_14"

    def test_key_with_spaces(self):
        key = _cache_key("New York", hour_bucket="20260220_09")
        assert key == "weather:new-york:20260220_09"


class TestWeatherCacheGetSet:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, weather_cache, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        result = await weather_cache.get("Tokyo")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_parsed(self, weather_cache, mock_redis):
        payload = _make_owm_response(condition_id=501, condition_main="Rain")
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))

        result = await weather_cache.get("Tokyo")
        assert result is not None
        assert result["name"] == "TestCity"

    @pytest.mark.asyncio
    async def test_cache_set_calls_redis_with_ttl(self, weather_cache, mock_redis):
        payload = _make_owm_response()
        await weather_cache.set("Tokyo", payload)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        # Key should start with 'weather:tokyo:'
        key_arg = call_args[0][0]
        assert key_arg.startswith("weather:tokyo:")
        # TTL should be 3600
        assert call_args[1]["ex"] == 3600

    @pytest.mark.asyncio
    async def test_cache_redis_failure_on_get_returns_none(self, weather_cache, mock_redis):
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        result = await weather_cache.get("Tokyo")
        assert result is None  # Graceful degradation

    @pytest.mark.asyncio
    async def test_cache_redis_failure_on_set_does_not_raise(self, weather_cache, mock_redis):
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        # Should not raise
        await weather_cache.set("Tokyo", _make_owm_response())

    @pytest.mark.asyncio
    async def test_cache_none_redis_is_noop(self):
        cache = WeatherCache(redis=None)
        result = await cache.get("Tokyo")
        assert result is None
        await cache.set("Tokyo", {})  # Should not raise

    @pytest.mark.asyncio
    async def test_invalidate_calls_delete(self, weather_cache, mock_redis):
        await weather_cache.invalidate("Tokyo")
        mock_redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Pure function unit tests
# ---------------------------------------------------------------------------

class TestKelvinToCelsius:
    def test_freezing(self):
        assert _kelvin_to_celsius(273.15) == 0.0

    def test_boiling(self):
        assert _kelvin_to_celsius(373.15) == 100.0

    def test_room_temp(self):
        assert _kelvin_to_celsius(295.0) == 21.9

    def test_precision_rounded(self):
        result = _kelvin_to_celsius(295.123)
        # Should be rounded to 1 decimal place
        assert result == round(295.123 - 273.15, 1)


class TestIsBadWeather:
    def test_rain_light(self):
        assert _is_bad_weather(500) is True

    def test_rain_moderate(self):
        assert _is_bad_weather(501) is True

    def test_rain_heavy(self):
        assert _is_bad_weather(502) is True

    def test_storm_thunderstorm(self):
        assert _is_bad_weather(200) is True

    def test_drizzle(self):
        assert _is_bad_weather(300) is True

    def test_clear_sky(self):
        assert _is_bad_weather(800) is False

    def test_few_clouds(self):
        assert _is_bad_weather(801) is False

    def test_snow_not_bad_weather_trigger(self):
        # Snow codes (600+) are not in rain/storm/drizzle ranges
        assert _is_bad_weather(601) is False


class TestParseCondition:
    def test_clear_sky(self):
        owm = _make_owm_response(800, "Clear", "clear sky", 295.0)
        result = _parse_condition(owm)
        assert result["condition"] == "clear"
        assert result["code"] == 800
        assert result["temp_c"] == _kelvin_to_celsius(295.0)
        assert result["description"] == "clear sky"

    def test_rain(self):
        owm = _make_owm_response(501, "Rain", "moderate rain", 285.0)
        result = _parse_condition(owm)
        assert result["condition"] == "rain"
        assert result["code"] == 501

    def test_missing_weather_list_defaults(self):
        owm = {"weather": [], "main": {"temp": 290.0}}
        result = _parse_condition(owm)
        assert result["code"] == 800  # clear sky default


# ---------------------------------------------------------------------------
# WeatherService integration-style tests (mocking httpx)
# ---------------------------------------------------------------------------

class TestWeatherServiceGetWeather:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self, weather_service, weather_cache, mock_redis):
        """If cache returns data, the OWM API should never be called."""
        owm_payload = _make_owm_response(800, "Clear", "clear sky", 295.0)
        mock_redis.get = AsyncMock(return_value=json.dumps(owm_payload))

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await weather_service.get_weather("Tokyo")
            mock_client_cls.assert_not_called()

        assert result is not None
        assert result["condition"] == "clear"

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_caches(self, weather_service, mock_redis):
        """On cache miss, the OWM API is called, result is cached, parsed summary returned."""
        mock_redis.get = AsyncMock(return_value=None)
        owm_payload = _make_owm_response(501, "Rain", "moderate rain", 288.0)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=owm_payload)
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("services.api.weather.service.httpx.AsyncClient", return_value=mock_client):
            result = await weather_service.get_weather("Tokyo")

        assert result is not None
        assert result["condition"] == "rain"
        assert result["code"] == 501

        # Cache should have been written
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_http_error_returns_none(self, weather_service, mock_redis):
        """HTTP 401/429 from OWM should return None without raising."""
        import httpx as _httpx

        mock_redis.get = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=_httpx.HTTPStatusError(
                "401", request=MagicMock(), response=mock_response
            )
        )

        with patch("services.api.weather.service.httpx.AsyncClient", return_value=mock_client):
            result = await weather_service.get_weather("Tokyo")

        assert result is None

    @pytest.mark.asyncio
    async def test_api_network_failure_returns_none(self, weather_service, mock_redis):
        """Network errors return None — weather is best-effort."""
        import httpx as _httpx

        mock_redis.get = AsyncMock(return_value=None)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("DNS failure"))

        with patch("services.api.weather.service.httpx.AsyncClient", return_value=mock_client):
            result = await weather_service.get_weather("Tokyo")

        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none_without_call(self, weather_cache, mock_redis):
        """If no API key configured, skip the API call silently."""
        service = WeatherService(api_key="", cache=weather_cache)
        mock_redis.get = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await service.get_weather("Tokyo")
            mock_client_cls.assert_not_called()

        assert result is None


class TestWeatherServiceHelpers:
    def test_is_outdoor_slot_outdoors(self, weather_service):
        assert weather_service.is_outdoor_slot("outdoors") is True

    def test_is_outdoor_slot_active(self, weather_service):
        assert weather_service.is_outdoor_slot("active") is True

    def test_is_outdoor_slot_dining_false(self, weather_service):
        assert weather_service.is_outdoor_slot("dining") is False

    def test_is_outdoor_slot_culture_false(self, weather_service):
        assert weather_service.is_outdoor_slot("culture") is False

    def test_is_outdoor_slot_case_insensitive(self, weather_service):
        assert weather_service.is_outdoor_slot("Outdoors") is True

    def test_build_weather_context_none_weather(self, weather_service):
        result = weather_service.build_weather_context(None, "outdoors")
        assert result is None

    def test_build_weather_context_outdoor_rain(self, weather_service):
        summary = {"condition": "rain", "code": 501, "temp_c": 18.2}
        result = weather_service.build_weather_context(summary, "outdoors")
        parsed = json.loads(result)
        assert parsed["outdoor_risk"] is True
        assert parsed["condition"] == "rain"
        assert parsed["code"] == 501
        assert parsed["temp_c"] == 18.2

    def test_build_weather_context_indoor_rain(self, weather_service):
        summary = {"condition": "rain", "code": 501, "temp_c": 18.2}
        result = weather_service.build_weather_context(summary, "dining")
        parsed = json.loads(result)
        assert parsed["outdoor_risk"] is False  # Not outdoor -> no risk

    def test_build_weather_context_outdoor_clear(self, weather_service):
        summary = {"condition": "clear", "code": 800, "temp_c": 24.0}
        result = weather_service.build_weather_context(summary, "outdoors")
        parsed = json.loads(result)
        assert parsed["outdoor_risk"] is False  # Clear weather -> no risk

    def test_should_trigger_weather_pivot_rain_outdoors(self, weather_service):
        summary = {"condition": "rain", "code": 501, "temp_c": 17.0}
        assert weather_service.should_trigger_weather_pivot(summary, "outdoors") is True

    def test_should_trigger_weather_pivot_storm_active(self, weather_service):
        summary = {"condition": "thunderstorm", "code": 211, "temp_c": 22.0}
        assert weather_service.should_trigger_weather_pivot(summary, "active") is True

    def test_should_trigger_weather_pivot_clear_outdoors(self, weather_service):
        summary = {"condition": "clear", "code": 800, "temp_c": 25.0}
        assert weather_service.should_trigger_weather_pivot(summary, "outdoors") is False

    def test_should_trigger_weather_pivot_rain_dining(self, weather_service):
        summary = {"condition": "rain", "code": 501, "temp_c": 17.0}
        assert weather_service.should_trigger_weather_pivot(summary, "dining") is False

    def test_should_trigger_weather_pivot_none_weather(self, weather_service):
        assert weather_service.should_trigger_weather_pivot(None, "outdoors") is False
