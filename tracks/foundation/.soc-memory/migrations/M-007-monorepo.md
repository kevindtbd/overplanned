# M-007: Monorepo Wiring

## Description
Set up npm workspaces for the monorepo structure. Wire packages so frontend imports from shared-types, not directly from Prisma client.

## Task
1. Root package.json with npm workspaces:
   - workspaces: ["apps/*", "packages/*", "services/*"]

2. packages/schemas/ — generated JSON Schemas (from codegen)

3. packages/shared-types/ — generated TS types (API boundary shapes only, no Prisma relations)
   - package.json with name: "@overplanned/shared-types"

4. packages/db/ — Prisma schema + client
   - package.json with name: "@overplanned/db"
   - Exports Prisma client

5. ESLint rule: no-restricted-imports
   - Ban @prisma/client imports in apps/web/ (frontend must use @overplanned/shared-types)
   - This prevents Prisma relation types from leaking to the frontend

6. Makefile for polyglot build orchestration:
   - `make codegen` — runs npm codegen + Python codegen in one command
   - `make dev` — starts both Next.js and FastAPI in dev mode
   - `make test` — runs all test suites
   - `make docker-up` — docker compose up -d
   - `make docker-down` — docker compose down

Deliverable: apps/web imports from @overplanned/shared-types, types resolve correctly, ESLint rule prevents @prisma/client imports in frontend.

## Output
package.json

## Zone
monorepo

## Dependencies
- M-003

## Priority
60

## Target Files
- package.json
- packages/shared-types/package.json
- packages/shared-types/index.ts
- packages/db/package.json
- packages/db/index.ts
- Makefile
- .eslintrc.json

## Files
- scripts/prisma-to-jsonschema.ts
- packages/schemas/
- docs/plans/vertical-plans-v2.md
