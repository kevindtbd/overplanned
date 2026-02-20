# M-004: Arctic Shift Reddit Loader

## Description
Load Reddit travel recommendations from Arctic Shift Parquet dumps. Historical archive batch processing, not live scraping.

## Task
Create services/api/scrapers/arctic_shift.py:
- Download and parse Parquet files for target subreddits:
  - r/JapanTravel, r/solotravel, r/travel, r/foodtravel, city-specific subs
- Extract travel recommendations from posts and comments:
  - Venue name mentions, location context, sentiment
  - Score/upvote weighting for authority
- Feed extracted content into LLM extraction pipeline (same format as blog content)
- Batch job pattern: process all historical data, then incremental updates
- Output: QualitySignal rows with source: "reddit_arcticshift"

Deliverable: load r/JapanTravel archive → QualitySignal rows for Tokyo/Kyoto/Osaka venues.

## Output
services/api/scrapers/arctic_shift.py

## Zone
scrapers

## Dependencies
- M-000

## Priority
80

## Target Files
- services/api/scrapers/arctic_shift.py

## Files
- services/api/scrapers/base.py
- docs/plans/vertical-plans-v2.md
