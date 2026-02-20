# M-002: Weather Service

## Description
OpenWeatherMap integration with Redis caching, per-city not per-trip.

## Task
1. OpenWeatherMap client (1000 free calls/day)
2. Cache per city per hour in Redis (multiple trips in same city share weather)
3. Check cached weather against outdoor activity slots
4. Populate BehavioralSignal.weatherContext from cache on signal writes

## Output
services/api/weather/service.py

## Zone
weather

## Dependencies
- M-001

## Priority
90

## Target Files
- services/api/weather/service.py
- services/api/weather/cache.py

## Files
- docs/plans/vertical-plans-v2.md
