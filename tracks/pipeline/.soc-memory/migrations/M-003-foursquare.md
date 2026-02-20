# M-003: Foursquare Places Integration

## Description
Foursquare Places API client for structured venue data.

## Task
Create services/api/scrapers/foursquare.py:
- Inherits BaseScraper
- Foursquare Places API v3 client
- Rate limit: respect 950 free calls/day (track daily usage)
- Search by city + category
- Map to ActivityNode: name, lat/lng, priceLevel, hours, category mapping to ActivityCategory enum, foursquareId
- Create QualitySignal with source: "foursquare"

Category mapping: Foursquare categories → our 11 coarse ActivityCategory enum values.

Deliverable: query "restaurants in Austin" → ActivityNode rows with Foursquare IDs and mapped categories.

## Output
services/api/scrapers/foursquare.py

## Zone
scrapers

## Dependencies
- M-000

## Priority
85

## Target Files
- services/api/scrapers/foursquare.py

## Files
- services/api/scrapers/base.py
- docs/plans/vertical-plans-v2.md
