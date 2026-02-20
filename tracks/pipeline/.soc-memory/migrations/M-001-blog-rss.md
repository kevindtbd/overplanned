# M-001: Blog RSS Scrapers

## Description
RSS feed parser for travel blogs. First concrete scraper using the base framework.

## Task
Create services/api/scrapers/blog_rss.py:
- Inherits BaseScraper
- RSS feed parsing (feedparser library)
- Seed list of feeds from docs/overplanned-blog-sources.md
- For each article: extract venue mentions, location, description
- Output: QualitySignal rows with source name, authority score, rawExcerpt (30-day retention)
- Handle: malformed RSS, empty feeds, encoding issues

Deliverable: scrape The Infatuation feed → QualitySignal rows in DB with correct authority scores.

## Output
services/api/scrapers/blog_rss.py

## Zone
scrapers

## Dependencies
- M-000

## Priority
90

## Target Files
- services/api/scrapers/blog_rss.py

## Files
- services/api/scrapers/base.py
- docs/overplanned-blog-sources.md
- docs/plans/vertical-plans-v2.md
