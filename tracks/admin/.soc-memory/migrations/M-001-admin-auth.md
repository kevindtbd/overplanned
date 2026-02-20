# M-001: Admin Auth Guard + AuditLog

## Description
Admin middleware, layout, and AuditLog writes on every action.

## Task
1. systemRole: admin check middleware for all /admin routes
2. Admin layout (separate from user app shell)
3. AuditLog write on every admin action (append-only)
4. Captures: actorId, action, targetType, targetId, before/after, ipAddress, userAgent

## Output
apps/web/app/admin/layout.tsx

## Zone
auth

## Dependencies
none

## Priority
100

## Target Files
- apps/web/app/admin/layout.tsx
- apps/web/middleware/admin.ts
- services/api/middleware/audit.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
