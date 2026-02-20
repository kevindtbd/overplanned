# M-002: Atlas Obscura Scraper

## Description
HTML scraper for Atlas Obscura hidden gems.

## Task
Create services/api/scrapers/atlas_obscura.py:
- Inherits BaseScraper
- HTML parsing (BeautifulSoup)
- Extract: name, coordinates, description, hidden-gem signal
- Map to ActivityNode with status: pending
- Create QualitySignal with source: "atlas_obscura", authority score per source registry
- Rate limit: 1 request per 3 seconds (be respectful)

Deliverable: scrape 1 city → ActivityNode rows with hidden_gem QualitySignals.

## Output
services/api/scrapers/atlas_obscura.py

## Zone
scrapers

## Dependencies
- M-000

## Priority
85

## Target Files
- services/api/scrapers/atlas_obscura.py

## Files
- services/api/scrapers/base.py
- docs/plans/vertical-plans-v2.md
