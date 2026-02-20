# Foundation Track — Changelog

## [M-001] COMMIT - 2026-02-20 12:59:08
Complete local dev infrastructure with PostgreSQL 16+PostGIS, Redis 7, Qdrant, and PgBouncer, all containerized with localhost-only binding and env var configuration
### Verified
- [x] docker-compose.yml
- [x] .env.example
- [x] docker/init-postgis.sql

## [M-002] COMMIT - 2026-02-20 13:16:26
Complete Prisma schema with all 22 models and seed data created. Schema includes all fields from schema-contracts.md and schema-revisions.md including Track 4/5 extension fields. Next steps: run `npx prisma migrate dev` to create migrations, then `npx prisma db seed` to populate vibe tags and test data.
### Verified
- [x] prisma/schema.prisma
- [x] prisma/seed.ts

## [M-003] COMMIT - 2026-02-20 13:22:29
Built complete cross-stack contract system with Prisma as single source of truth. The pipeline automatically generates JSON Schema, Pydantic models, TypeScript types, and Qdrant payload schema. CI guards ensure generated files stay synchronized. Change any Prisma model → npm run codegen → all stacks update automatically.
### Verified
- [x] docs/codegen-spec.md
- [x] scripts/prisma-to-jsonschema.ts
- [x] scripts/jsonschema-to-qdrant.ts
- [x] package.json
- [x] .github/workflows/codegen-check.yml
- [x] packages/schemas/.gitkeep
- [x] packages/shared-types/api.ts
- [x] services/api/models/generated.py
- [x] services/api/config/qdrant_schema.json
- [x] tsconfig.json
- [x] .gitignore
- [x] README.md

## [M-004] COMMIT_UNVERIFIED - 2026-02-20 13:22:29
Claude claimed success but no files found on disk
### MISSING (claimed but not found)
- [ ] apps/web/app/api/auth/[...nextauth]/route.ts
- [ ] apps/web/lib/auth/config.ts
- [ ] apps/web/lib/auth/session.ts
- [ ] apps/web/lib/auth/gates.ts
- [ ] apps/web/middleware.ts
- [ ] apps/web/components/auth/ProtectedRoute.tsx
- [ ] apps/web/types/next-auth.d.ts
- [ ] apps/web/package.json
- [ ] apps/web/tsconfig.json
- [ ] apps/web/.env.example
- [ ] apps/web/next.config.js
- [ ] apps/web/app/layout.tsx
- [ ] apps/web/components/auth/SessionProvider.tsx
- [ ] apps/web/app/auth/signin/page.tsx
- [ ] apps/web/app/auth/error/page.tsx
- [ ] apps/web/app/page.tsx
- [ ] apps/web/README.md

## [M-007] COMMIT_UNVERIFIED - 2026-02-20 13:23:54
Claude claimed success but no files found on disk
### MISSING (claimed but not found)
- [ ] packages/shared-types/package.json
- [ ] packages/shared-types/index.ts
- [ ] packages/shared-types/tsconfig.json
- [ ] packages/shared-types/generated/.gitkeep
- [ ] packages/db/package.json
- [ ] packages/db/index.ts
- [ ] packages/schemas/package.json
- [ ] .eslintrc.json
- [ ] Makefile

## [M-006] COMMIT - 2026-02-20 13:24:53
FastAPI service scaffolded with config, CORS, Sentry, sliding-window rate limiting, health check, and RawEvent batch ingestion. DB pool left as placeholder for database migration task to wire.
### Verified
- [x] services/api/__init__.py
- [x] services/api/config.py
- [x] services/api/main.py
- [x] services/api/middleware/__init__.py
- [x] services/api/middleware/cors.py
- [x] services/api/middleware/sentry.py
- [x] services/api/middleware/rate_limit.py
- [x] services/api/routers/__init__.py
- [x] services/api/routers/health.py
- [x] services/api/routers/events.py
- [x] services/api/requirements.txt

## [M-010] COMMIT_CONFLICT - 2026-02-20 13:25:59
EmbeddingService with lazy-loaded nomic-embed-text-v1.5, thread-safe singleton, L2-normalized output. Batch (POST /embed/batch) and query (POST /embed/query) endpoints registered in main app. ModelRegistry write deferred to DB migration task.
### Verified
- [x] services/api/requirements.txt
- [x] services/api/embedding/__init__.py
- [x] services/api/embedding/service.py
- [x] services/api/routers/embed.py
- [x] services/api/main.py
### CONFLICT (claimed by another task)
- [!] services/api/requirements.txt
- [!] services/api/main.py

## [M-008] COMMIT_UNVERIFIED - 2026-02-20 13:26:31
Claude claimed success but no files found on disk
### MISSING (claimed but not found)
- [ ] Dockerfile.web
- [ ] Dockerfile.api
- [ ] cloudbuild.yaml
- [ ] .dockerignore
- [ ] apps/web/next.config.js

## [M-009] COMMIT_CONFLICT - 2026-02-20 13:27:03
Reusable search pipeline: embed query -> Qdrant vector search (is_canonical filtered) -> Postgres batch hydration with lateral joins -> merged results. Graceful degradation on both Qdrant and Postgres failures. Wired into FastAPI lifespan with proper cleanup.
### Verified
- [x] services/api/search/__init__.py
- [x] services/api/search/qdrant_client.py
- [x] services/api/search/hydrator.py
- [x] services/api/search/service.py
- [x] services/api/routers/search.py
- [x] services/api/config.py
- [x] services/api/main.py
### CONFLICT (claimed by another task)
- [!] services/api/config.py
- [!] services/api/main.py

## [M-011] COMMIT - 2026-02-20 13:34:11
Comprehensive test suite: conftest with 9 model factories (nullable-field safe for downstream tracks), signal integrity helper (7 invariant checks), contract tests (enum sync + field parity + codegen guard), auth tests (RBAC + sessions + concurrent limit + OAuth), API tests (envelope + requestId + embed endpoints + rate limiting), events tests (batch + dedup + size limits), Playwright smoke E2E, plus docker-compose.test.yml with tmpfs-backed services.
### Verified
- [x] docker-compose.test.yml
- [x] services/api/pytest.ini
- [x] apps/web/jest.config.ts
- [x] playwright.config.ts
- [x] services/api/tests/__init__.py
- [x] services/api/tests/conftest.py
- [x] services/api/tests/helpers/__init__.py
- [x] services/api/tests/helpers/factories.py
- [x] services/api/tests/helpers/signal_invariants.py
- [x] services/api/tests/test_contracts.py
- [x] services/api/tests/test_auth.py
- [x] services/api/tests/test_api.py
- [x] services/api/tests/test_events.py
- [x] apps/web/__tests__/e2e/smoke.spec.ts

## [M-012] COMMIT_UNVERIFIED - 2026-02-20 13:35:09
Claude claimed success but no files found on disk
### MISSING (claimed but not found)
- [ ] CONTRIBUTING.md
- [ ] .github/pull_request_template.md
- [ ] .github/workflows/regression.yml
