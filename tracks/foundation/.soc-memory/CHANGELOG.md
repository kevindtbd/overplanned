# Foundation Track — Changelog

## M-001: Docker + PostGIS + Redis — 2026-02-20

### Added
- `docker-compose.yml` — All 4 services containerized: Postgres 16 with PostGIS (port 5432), Redis 7 Alpine with password auth (port 6379), Qdrant with API key auth (ports 6333/6334), PgBouncer connection pooler (port 6432) — all bound to localhost only with named volumes
- `.env.example` — Documents all required environment variables (POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_USER, REDIS_PASSWORD, QDRANT_API_KEY) — no secret defaults
- `docker/init-postgis.sql` — Init script enabling PostGIS on first boot via `CREATE EXTENSION IF NOT EXISTS postgis`

---

## M-002: Prisma Schema (22 models) — 2026-02-20

### Added
- `prisma/schema.prisma` — Complete 22-model schema as single source of truth: core models (User, Session, Account, VerificationToken, Trip with timezone, TripMember, ItinerarySlot); world knowledge (ActivityNode with coarse ActivityCategory enum, foursquareId, googlePlaceId, canonicalName, convergenceScore, authorityScore; VibeTag; ActivityNodeVibeTag junction; ActivityAlias; QualitySignal with 30-day purge); signals (BehavioralSignal with composite indexes, IntentionSignal, RawEvent append-only firehose with clientEventId dedup and @@unique on userId+clientEventId); ML + admin (ModelRegistry with artifactHash, PivotEvent, AuditLog append-only); tokens (SharedTripToken 90-day expiry, InviteToken single-use 7-day expiry member-only)
- `prisma/seed.ts` — Seeds 42 vibe tags from constant, 1 beta-tier test user, 1 admin test user

---

## M-003: Codegen Pipeline — 2026-02-20

### Added
- `docs/codegen-spec.md` — Specification mapping every Prisma type to JSON Schema output, edge case handling for Json fields, String[], optionals, enums, and default values
- `scripts/prisma-to-jsonschema.ts` — Parses Prisma schema via @mrleebo/prisma-ast, outputs one JSON Schema file per model to packages/schemas/
- `scripts/jsonschema-to-qdrant.ts` — Reads ActivityNode JSON Schema, generates Qdrant payload schema config at services/api/config/qdrant_schema.json
- `packages/schemas/.gitkeep` — Placeholder for generated JSON Schema files (output of codegen pipeline)
- `packages/shared-types/api.ts` — Generated TypeScript API boundary types via json-schema-to-typescript
- `services/api/models/generated.py` — Generated Pydantic models via datamodel-code-generator
- `tsconfig.json` — Root TypeScript config for the monorepo
- `.gitignore` — Root gitignore
- `README.md` — Project README
- `.github/workflows/codegen-check.yml` — CI guard: on PR runs codegen, diffs generated files, fails if stale

---

## M-004: Auth + Session Management — 2026-02-20

### Note
COMMIT_UNVERIFIED — files were not found on disk at verification time. Intended deliverables:

### Added (planned)
- `apps/web/app/api/auth/[...nextauth]/route.ts` — NextAuth.js handler: Google OAuth only, Prisma adapter, database session strategy (not JWT), maxAge 30 days, updateAge 7 days; creates User with role: 'beta' on first OAuth login
- `apps/web/lib/auth/config.ts` — NextAuth configuration with concurrent session limit (max 5 per user, oldest deleted on 6th login)
- `apps/web/lib/auth/session.ts` — Session utilities and auth middleware: verifies session on protected routes, updates User.lastActiveAt on each authenticated request
- `apps/web/lib/auth/gates.ts` — `getEffectiveTier()` utility and FEATURE_GATES config; access check: ['beta', 'lifetime', 'pro'].includes(user.role)
- `apps/web/middleware.ts` — Next.js middleware for route-level session verification
- `apps/web/components/auth/ProtectedRoute.tsx` — Client-side protected route wrapper
- `apps/web/components/auth/SessionProvider.tsx` — Session context provider
- `apps/web/app/auth/signin/page.tsx` — Sign-in page
- `apps/web/app/auth/error/page.tsx` — Auth error page
- `apps/web/app/page.tsx` — Root page
- `apps/web/app/layout.tsx` — Root layout
- `apps/web/package.json` — Next.js app package manifest
- `apps/web/tsconfig.json` — App-level TypeScript config
- `apps/web/next.config.js` — Next.js config
- `apps/web/.env.example` — App-level env var documentation
- `apps/web/types/next-auth.d.ts` — NextAuth type augmentation

---

## M-005: App Shell + Design System — 2026-02-20

### Note
Not recorded in conductor run — deliverables merged into M-004 output or pending.

### Added (planned)
- `apps/web/app/layout.tsx` — Root layout: Sora (headings, eager) + DM Mono (data/labels, eager) + Lora (detail/post-trip, lazy) via next/font
- `apps/web/app/globals.css` — Global CSS with :root custom properties for all design tokens (light + dark mode), spacing scale, border radius, shadows
- `apps/web/tailwind.config.ts` — Tailwind config with design tokens: terracotta (#C4694F), warm-background, warm-surface, warm-border mapped from docs/overplanned-design-v4.html
- `apps/web/components/nav/MobileNav.tsx` — Bottom tab bar (Home / Trips / Explore / Profile), mobile-first
- `apps/web/components/nav/DesktopSidebar.tsx` — Sidebar nav for desktop (1024px+ breakpoint)
- `apps/web/components/layout/AppShell.tsx` — Responsive layout wrapper: mobile bottom nav + desktop sidebar + context panel
- `apps/web/lib/env.ts` — Zod schema validating required env vars at build time; crashes with clear error if vars missing
- `apps/web/next.config.js` — Security headers: strict CSP, HSTS, X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Referrer-Policy: strict-origin-when-cross-origin, Permissions-Policy (camera/microphone/geolocation restricted)

---

## M-006: FastAPI Skeleton — 2026-02-20

### Added
- `services/api/__init__.py` — Package marker
- `services/api/main.py` — FastAPI app with lifespan and all middleware; API envelope on ALL endpoints (success: {success, data, requestId}, error: {success, error, requestId}, ML adds modelVersion); DB pool placeholder for later wiring
- `services/api/config.py` — pydantic-settings config class validating all required env vars at startup
- `services/api/middleware/__init__.py` — Package marker
- `services/api/middleware/cors.py` — CORS restricted to overplanned.app and localhost:3000; no wildcards
- `services/api/middleware/rate_limit.py` — Redis-backed sliding window rate limiter: anonymous 10 req/min, authenticated 60 req/min, LLM-triggering endpoints 5 req/min, /events/batch 60 req/min
- `services/api/middleware/sentry.py` — Sentry instrumentation (server-side only) with before_send hook stripping Authorization headers and cookies from breadcrumbs
- `services/api/routers/__init__.py` — Package marker
- `services/api/routers/health.py` — GET /health returning {success, data: {status, version}, requestId}
- `services/api/routers/events.py` — POST /events/batch: accepts up to 1000 RawEvent payloads, clientEventId dedup via ON CONFLICT DO NOTHING, 1MB body size limit, returns inserted vs skipped counts
- `services/api/requirements.txt` — Python dependencies: fastapi, uvicorn, pydantic-settings, sentry-sdk, redis, asyncpg, sentence-transformers

---

## M-007: Monorepo Wiring — 2026-02-20

### Note
COMMIT_UNVERIFIED — files were not found on disk at verification time. Intended deliverables:

### Added (planned)
- `packages/shared-types/package.json` — Package manifest for @overplanned/shared-types
- `packages/shared-types/index.ts` — Re-exports all generated TS API boundary types (no Prisma relation types)
- `packages/shared-types/tsconfig.json` — Package-level TypeScript config
- `packages/db/package.json` — Package manifest for @overplanned/db
- `packages/db/index.ts` — Prisma client export
- `packages/schemas/package.json` — Package manifest for @overplanned/schemas
- `.eslintrc.json` — no-restricted-imports rule banning @prisma/client in apps/web/ (frontend must use @overplanned/shared-types)
- `Makefile` — Polyglot build orchestration: `make codegen`, `make dev`, `make test`, `make docker-up`, `make docker-down`

---

## M-008: Deploy Skeleton — 2026-02-20

### Note
COMMIT_UNVERIFIED — files were not found on disk at verification time. Intended deliverables:

### Added (planned)
- `Dockerfile.web` — Multi-stage Next.js image (deps → build → production): pinned node:20-alpine digest, non-root nextjs:nodejs user, standalone output mode, HEALTHCHECK via wget on /api/health
- `Dockerfile.api` — Multi-stage FastAPI image (deps → production): pinned python:3.11-slim digest, non-root user, HEALTHCHECK via Python urllib
- `cloudbuild.yaml` — GCP Cloud Run config: builds both images, pushes to Artifact Registry, deploys web as public service, deploys api as internal-only (IAM-authenticated, no public ingress); GCP Secret Manager references for all API keys
- `.dockerignore` — Excludes node_modules, .env, .git, tests from both service images
- `apps/web/next.config.js` — Next.js config with standalone output mode

---

## M-009: ActivitySearchService — 2026-02-20

### Added
- `services/api/search/__init__.py` — Package marker
- `services/api/search/service.py` — ActivitySearchService class: search(query, city, filters, limit) → List[HydratedActivityNode]; pipeline: embed query → Qdrant search (is_canonical: true always applied, configurable score threshold) → batch Postgres hydration → merge; graceful degradation (Qdrant timeout → empty + warning, Postgres timeout → Qdrant-only results)
- `services/api/search/qdrant_client.py` — Qdrant client wrapper: API key auth from env, connection pooling, 3s query timeout
- `services/api/search/hydrator.py` — Batch Postgres hydrator: fetches ActivityNode + VibeTag junction + QualitySignal in one lateral join query, returns enriched objects
- `services/api/routers/search.py` — GET /search?q=...&city=...&category=...&limit=20: uses ActivitySearchService, returns API envelope with hydrated results

### Note
COMMIT_CONFLICT — services/api/config.py and services/api/main.py had merge conflicts with M-006 output; resolved in favor of later write.

---

## M-010: Embedding Infrastructure — 2026-02-20

### Added
- `services/api/embedding/__init__.py` — Package marker
- `services/api/embedding/service.py` — EmbeddingService class: nomic-embed-text-v1.5 (768 dimensions), thread-safe singleton, lazy model load on first use (~270MB), embed_single(text) → 768-dim L2-normalized vector, embed_batch(texts, batch_size=32) → List of 768-dim vectors; integrated with ActivitySearchService fast path
- `services/api/routers/embed.py` — POST /embed/batch (up to 100 texts → 768-dim vectors) and POST /embed/query (single text fast path); ModelRegistry entry for nomic-embed-text-v1.5 (type: embedding, stage: production)

### Note
COMMIT_CONFLICT — services/api/requirements.txt and services/api/main.py had merge conflicts with M-006 output; resolved in favor of later write.

---

## M-011: Foundation Tests + E2E Wiring — 2026-02-20

### Added
- `docker-compose.test.yml` — Test infrastructure: Postgres on RAM disk (tmpfs), Qdrant with tmpfs, Redis — fully isolated from dev volumes
- `services/api/pytest.ini` — Pytest configuration for FastAPI test suite
- `apps/web/jest.config.ts` — Jest configuration for Next.js test suite
- `playwright.config.ts` — Playwright E2E test configuration
- `services/api/tests/__init__.py` — Package marker
- `services/api/tests/conftest.py` — Pytest fixtures with testcontainers: auto-provision test database, clean state between tests, factory pattern for all 9 core models with nullable extension fields handled (Track 4/5 won't break Track 1 fixtures)
- `services/api/tests/helpers/__init__.py` — Package marker
- `services/api/tests/helpers/factories.py` — Model factory helpers for all core models
- `services/api/tests/helpers/signal_invariants.py` — Reusable `assert_signal_integrity(db)`: 7 invariant checks (no orphan signals, valid foreign keys, required fields present) — shared across all tracks
- `services/api/tests/test_contracts.py` — Per-model schema parity tests: Prisma model ↔ JSON Schema ↔ Pydantic class ↔ TS type; enum sync for SignalType, ActivityCategory, etc.; CI codegen guard test
- `services/api/tests/test_auth.py` — Auth tests: RBAC tier access (beta/lifetime/pro/free), session lifecycle (create, expire, idle timeout), concurrent session limit (6th session deletes oldest), Google OAuth callback creates user with beta role
- `services/api/tests/test_api.py` — API envelope tests: success/error/paginated shapes, requestId on every response, modelVersion on ML responses, rate limiting per tier, embed endpoint validation
- `services/api/tests/test_events.py` — /events/batch tests: clientEventId dedup, 1MB body size limit enforcement, max 1000 batch size
- `apps/web/__tests__/e2e/smoke.spec.ts` — Playwright smoke E2E: Google OAuth mock → session created → protected route accessible → logout → session destroyed

---

## M-012: Migration Merge Protocol — 2026-02-20

### Note
COMMIT_UNVERIFIED — files were not found on disk at verification time. Intended deliverables:

### Added (planned)
- `CONTRIBUTING.md` — Schema change protocol: PR requirements for schema.prisma changes (codegen run + commit generated files, all track tests pass, at least one other track owner review); branch strategy (track/* branches, schema extensions to main first, rebase after); conflict resolution (earlier-numbered track merges first)
- `.github/pull_request_template.md` — PR checklist for schema changes: codegen run, contract tests pass, no breaking changes, affected models/fields/indexes listed
- `.github/workflows/regression.yml` — On every PR to main: runs ALL track test suites; track owning the regression is responsible for the fix
