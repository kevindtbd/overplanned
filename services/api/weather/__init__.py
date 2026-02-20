"""
Weather service package.

Provides OpenWeatherMap integration with per-city per-hour Redis caching.
Multiple trips share weather data — city + hour is the cache key.
"""

from services.api.weather.service import WeatherService
from services.api.weather.cache import WeatherCache

__all__ = ["WeatherService", "WeatherCache"]
