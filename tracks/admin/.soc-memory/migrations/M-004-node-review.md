# M-004: Activity Node Review Queue

## Description
Admin queue for flagged or low-convergence nodes.

## Task
1. List flagged/low-convergence nodes
2. Approve / edit / archive (all logged to AuditLog with before/after)
3. Alias management
4. Status changes logged (replaces StatusHistory for now)

## Output
apps/web/app/admin/nodes/page.tsx

## Zone
nodes

## Dependencies
- M-001

## Priority
70

## Target Files
- apps/web/app/admin/nodes/page.tsx
- apps/web/app/admin/nodes/components/NodeEditor.tsx
- services/api/routers/admin_nodes.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
