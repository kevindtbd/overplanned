# M-001: Prisma Singleton

## Description
Create a shared PrismaClient singleton and replace all 9 per-module `new PrismaClient()` instances. Connection pool exhaustion risk — P0 priority.

## Task
Create `apps/web/lib/prisma.ts` with the standard Next.js singleton pattern:
- Use `globalThis` to persist across hot reloads in dev
- Log queries/warnings in dev, errors-only in production
- Export named `prisma` constant

Replace `new PrismaClient()` in ALL of these files with `import { prisma } from "@/lib/prisma"`:
1. `apps/web/lib/auth/session.ts` (line 3)
2. `apps/web/lib/auth/config.ts` (line 7)
3. `apps/web/app/api/events/raw/route.ts` (line 18)
4. `apps/web/app/api/discover/feed/route.ts` (line 14)
5. `apps/web/app/api/signals/behavioral/route.ts` (line 14)
6. `apps/web/app/api/slots/[slotId]/swap/route.ts` (line 15)
7. `apps/web/app/trip/[id]/calendar/page.tsx` (line 7)
8. `apps/web/app/api/trips/[id]/route.ts` (line 12)
9. `apps/web/app/api/trips/route.ts` (line 13)

For each file: remove the `import { PrismaClient } from "@prisma/client"` line and the `const prisma = new PrismaClient()` line. Replace with `import { prisma } from "@/lib/prisma"`.

Verify: `npx tsc --noEmit` passes. All existing tests still pass.

## Output
apps/web/lib/prisma.ts

## Zone
infra

## Dependencies
none

## Priority
100

## Target Files
- apps/web/lib/prisma.ts
- apps/web/lib/auth/session.ts
- apps/web/lib/auth/config.ts
- apps/web/app/api/events/raw/route.ts
- apps/web/app/api/discover/feed/route.ts
- apps/web/app/api/signals/behavioral/route.ts
- apps/web/app/api/slots/[slotId]/swap/route.ts
- apps/web/app/trip/[id]/calendar/page.tsx
- apps/web/app/api/trips/[id]/route.ts
- apps/web/app/api/trips/route.ts

## Files
- docs/plans/dashboard-audit-compound.md
