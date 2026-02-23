# Infrastructure Vertical — Memory Bank

## Sub-topic Files
- `devops.md` — GCP Cloud Run, Docker, monorepo, CI/CD
- `testing.md` — Vitest, Playwright, test patterns, mock strategies
- `conductor.md` — SOC execution patterns, conductor config, wave-based execution

## Stack
- Hosting: GCP Cloud Run
- DB: PostgreSQL 16 + PostGIS, PgBouncer
- Cache: Redis 7
- Vector: Qdrant (Docker locally, Cloud Run in prod)
- Monorepo: workspaces (packages/schemas, packages/shared-types, packages/db)
- Errors: Sentry
- Email: Resend
