# M-009: ActivitySearchService

## Description
Build the reusable search service that all downstream consumers use: Qdrant vector search → Postgres batch hydration → merge. Used by itinerary generation, discover, pivot alternatives, micro-stops.

## Task
1. Create services/api/search/service.py — ActivitySearchService class:
   - search(query: str, city: str, filters: dict, limit: int) → List[HydratedActivityNode]
   - Steps: embed query → Qdrant search → get IDs → Postgres batch hydrate → merge payload + DB fields
   - Always apply is_canonical: true filter on Qdrant queries
   - Configurable score threshold

2. Qdrant client wrapper (services/api/search/qdrant_client.py):
   - API key auth from env var
   - Connection pooling
   - Timeout: 3s per query

3. Postgres hydration (services/api/search/hydrator.py):
   - Batch fetch ActivityNode + VibeTag junction + QualitySignal in one query
   - Return enriched objects

4. Search endpoint: GET /search?q=...&city=...&category=...&limit=20
   - Uses ActivitySearchService
   - Returns API envelope with hydrated results

5. Error handling:
   - Qdrant timeout → return empty with warning in response
   - Postgres timeout → return Qdrant-only results (less enriched)

Deliverable: search("quiet coffee shop", city="austin") returns hydrated ActivityNode results with vibe tags and quality signals.

## Output
services/api/search/service.py

## Zone
search

## Dependencies
- M-006

## Priority
60

## Target Files
- services/api/search/service.py
- services/api/search/qdrant_client.py
- services/api/search/hydrator.py
- services/api/routers/search.py

## Files
- prisma/schema.prisma
- services/api/main.py
- docs/plans/vertical-plans-v2.md
