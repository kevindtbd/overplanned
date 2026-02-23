# Infra / Testing

## Stack
- **Vitest** (NOT Jest — old jest.config.ts was deleted)
- Config: `apps/web/vitest.config.ts` + `apps/web/vitest.setup.ts`
- Playwright: mobile (iPhone 13), tablet (iPad gen 7), desktop viewports

## Current Stats
- 716 tests passing across 46 files

## Mock Strategy
- `__mocks__/prisma.ts` — Prisma mock
- `__mocks__/auth.ts` — Auth mock
- `__tests__/helpers/request.ts` — NextRequest factory
- `__tests__/helpers/render.tsx` — Custom render with providers
- `__tests__/fixtures/` — Shared test fixtures

## Critical Patterns
- `vi.resetAllMocks()` > `vi.clearAllMocks()` — clear doesn't reset mockResolvedValueOnce queues
- Non-UUID test IDs fail Zod before business logic — always use valid UUIDs
- Module-level `new Anthropic()` breaks jsdom — vi.mock before import
- Rate limiter: 3 tiers (configured per route)

## Test Organization
- `__tests__/api/` — API route tests
- `__tests__/settings/` — Settings component tests
- `__tests__/trip/` — Trip component tests

## Learnings
- TripLeg migration test pattern: mock payloads need `legs: [{ city, ... }]`, mock prisma needs `tripLeg.createMany`, assertions change from flat to `legs[0]`
