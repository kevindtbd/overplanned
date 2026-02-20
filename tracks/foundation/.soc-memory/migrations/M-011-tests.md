# M-011: Foundation Tests + E2E Wiring

## Description
Comprehensive test suite for all Foundation deliverables. Test infrastructure that all downstream tracks will use.

## Task
1. Test infrastructure setup:
   - Jest config for Next.js (apps/web/jest.config.ts)
   - Pytest config for FastAPI (services/api/pytest.ini)
   - Playwright config (playwright.config.ts)
   - docker-compose.test.yml: Postgres on RAM disk (tmpfs), Qdrant with tmpfs, Redis

2. Pytest conftest with testcontainers:
   - Auto-provision test database
   - Clean state between tests
   - Fixture factory pattern: one factory per core model
   - Factories handle nullable extension fields (Track 4/5 won't break Track 1 fixtures)

3. Contract tests:
   - Per-model schema parity: Prisma model ↔ JSON Schema ↔ Pydantic class ↔ TS type
   - Enum sync: SignalType, ActivityCategory, etc. match across all stacks
   - CI guard test: modify Prisma → run codegen check → assert fails if stale

4. Auth tests:
   - RBAC tier access (beta, lifetime, pro, free)
   - Session lifecycle (create, expire, idle timeout)
   - Concurrent session limit (6th session deletes oldest)
   - Google OAuth callback creates user with beta role

5. API tests:
   - Envelope shape: success/error/paginated formats
   - requestId present on every response
   - modelVersion field on ML endpoint responses
   - Rate limiting: verify limits per tier
   - /events/batch: dedup on clientEventId, body size limit, max batch size

6. Infrastructure tests:
   - Env var validation: missing vars → clear error on startup
   - Docker health checks: all services respond

7. Signal invariant helper: assert_signal_integrity(db)
   - Validates: no orphan signals, valid foreign keys, required fields present
   - Reusable across all tracks

8. Smoke E2E (Playwright):
   - Google OAuth mock → session created → protected route accessible → logout → session destroyed

Deliverable: `npm test` + `pytest` + `npx playwright test` all green. 20+ tests minimum.

## Output
services/api/tests/conftest.py

## Zone
tests

## Dependencies
- M-010

## Priority
40

## Target Files
- apps/web/jest.config.ts
- services/api/pytest.ini
- playwright.config.ts
- docker-compose.test.yml
- services/api/tests/conftest.py
- services/api/tests/test_contracts.py
- services/api/tests/test_auth.py
- services/api/tests/test_api.py
- services/api/tests/test_events.py
- services/api/tests/helpers/signal_invariants.py
- services/api/tests/helpers/factories.py
- apps/web/__tests__/e2e/smoke.spec.ts

## Files
- prisma/schema.prisma
- services/api/main.py
- apps/web/app/api/auth/[...nextauth]/route.ts
- docs/plans/vertical-plans-v2.md
