# Data / Pipeline & Scrapers

## Sources
1. Blog RSS scrapers (curated seed list, authority scores)
2. Atlas Obscura scraper (HTML -> ActivityNode + hidden_gem signal)
3. Foursquare Places API (950/day -> ActivityNode with foursquareId)
4. Arctic Shift Reddit archive loader
5. NOT TripAdvisor, NOT Yelp

## Pipeline Steps
1. Scrape/ingest from sources
2. Entity resolution (canonical name + dedup chain + ActivityAlias)
3. Content hash dedup (SHA256)
4. LLM vibe tag extraction (Haiku batch -> ActivityNodeVibeTag)
5. Rule-based vibe inference (category->tag map)
6. Convergence scorer + authority scorer
7. Qdrant sync + embedding
8. Image validation (Cloud Vision, 4-tier waterfall)

## FastAPI Backend
- `apps/ml/` — FastAPI service for ML/scraping
- Health check, generated Pydantic models, CORS, Sentry

## Learnings
- (space for future compound learnings)
