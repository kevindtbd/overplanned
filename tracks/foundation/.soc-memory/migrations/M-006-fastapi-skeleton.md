# M-006: FastAPI Skeleton

## Description
Set up the Python FastAPI service for ML/scraping/search endpoints. Rate limiting, CORS, Sentry, RawEvent ingestion endpoint.

## Task
1. Project structure under services/api/:
   - main.py (FastAPI app, lifespan, middleware)
   - routers/ (health, events)
   - models/generated.py (from codegen)
   - middleware/ (cors, rate_limit, sentry)
   - config.py (pydantic-settings for env var validation)

2. Health check: GET /health returns API envelope:
   ```json
   {"success": true, "data": {"status": "healthy", "version": "0.1.0"}, "requestId": "<uuid>"}
   ```

3. CORS middleware: restrict origins to overplanned.app + localhost:3000 (dev). No wildcards.

4. Sentry instrumentation:
   - Server-side only
   - before_send hook strips Authorization headers and cookies from breadcrumbs

5. Rate limiting middleware (Redis-backed):
   - Anonymous: 10 req/min
   - Authenticated: 60 req/min general
   - LLM-triggering endpoints: 5 req/min per user
   - /events/batch: 60 req/min per user
   - Use sliding window algorithm

6. POST /events/batch endpoint:
   - Accepts array of RawEvent payloads (max 1000 per batch)
   - clientEventId-based dedup: ON CONFLICT (userId, clientEventId) DO NOTHING
   - Request body size limit: 1MB
   - Returns count of inserted vs skipped (deduped)

7. API response envelope on ALL endpoints:
   - Success: { success: true, data: ..., requestId: "uuid" }
   - Error: { success: false, error: { code: "...", message: "..." }, requestId: "uuid" }
   - ML responses add: modelVersion field

Deliverable: curl localhost:8000/health → 200 with envelope. Rate limits enforced.

## Output
services/api/main.py

## Zone
backend

## Dependencies
- M-003

## Priority
70

## Target Files
- services/api/main.py
- services/api/routers/health.py
- services/api/routers/events.py
- services/api/middleware/cors.py
- services/api/middleware/rate_limit.py
- services/api/middleware/sentry.py
- services/api/config.py
- services/api/requirements.txt

## Files
- prisma/schema.prisma
- packages/schemas/
- docs/plans/vertical-plans-v2.md
