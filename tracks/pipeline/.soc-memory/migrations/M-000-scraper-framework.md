# M-000: Scraper Framework

## Description
Base scraper class with retry, backoff, dead letter queue, and alerting. All scrapers inherit from this.

## Task
Create services/api/scrapers/base.py with:
- BaseScraper abstract class
- retry decorator: exponential backoff, max 3 attempts
- Dead letter queue: failed items stored in dead_letter table or JSON log
- Rate limiting: configurable per-source (requests per minute)
- Respectful User-Agent header
- Source registry pattern: each scraper registers its name, URL, authority score, scrape frequency
- Alert hook: 3+ consecutive failures → log.warning + Sentry capture
- Abstract methods: scrape(), parse(), store()

Unit tests with mock HTTP: verify retry fires on 500, dead letter on permanent failure, rate limiting works.

## Output
services/api/scrapers/base.py

## Zone
scraper-framework

## Dependencies
none

## Priority
100

## Target Files
- services/api/scrapers/base.py
- services/api/scrapers/__init__.py

## Files
- docs/plans/vertical-plans-v2.md
