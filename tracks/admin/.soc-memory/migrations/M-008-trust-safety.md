# M-008: Trust & Safety

## Description
Token management and injection detection review queue.

## Task
1. SharedTripToken management: view, revoke (logged)
2. InviteToken management: view, revoke
3. Injection detection queue (flagged prompt bar inputs)

## Output
apps/web/app/admin/safety/page.tsx

## Zone
safety

## Dependencies
- M-001

## Priority
35

## Target Files
- apps/web/app/admin/safety/page.tsx
- apps/web/app/admin/safety/components/TokenManager.tsx
- apps/web/app/admin/safety/components/InjectionQueue.tsx
- services/api/routers/admin_safety.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
