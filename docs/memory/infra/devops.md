# Infra / DevOps

## Hosting
- GCP Cloud Run for all services
- Docker compose for local dev (Postgres 16 + Qdrant)
- See `docs/overplanned-devops-playbook.md` for full playbook

## Monorepo Structure
- `apps/web/` — Next.js 14 frontend + API routes
- `apps/ml/` — FastAPI backend (ML/scraping)
- `packages/schemas/` — Shared JSON schemas
- `packages/shared-types/` — Shared TypeScript types
- `packages/db/` — Prisma client

## Environment
- `lib/env.ts` — Environment variable validation
- Env management via Cloud Run config

## Learnings
- (space for future compound learnings)
