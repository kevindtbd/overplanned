# M-006: User Lookup + Persona Inspector

## Description
Search users, view history, manage feature flags and subscription tiers.

## Task
1. Search by email/name
2. View: signals, trips, tier, feature flags
3. Feature flag overrides (logged to AuditLog)
4. Subscription tier changes via admin (replaces SQL for lifetime)
5. All lookups logged to AuditLog (action: "user_lookup")

## Output
apps/web/app/admin/users/page.tsx

## Zone
users

## Dependencies
- M-001

## Priority
50

## Target Files
- apps/web/app/admin/users/page.tsx
- apps/web/app/admin/users/[id]/page.tsx
- services/api/routers/admin_users.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
