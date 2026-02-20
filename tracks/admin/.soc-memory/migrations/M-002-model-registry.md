# M-002: Model Registry UI

## Description
Model management with promotion safety gates.

## Task
1. List models with stage badges
2. Promotion requires metrics comparison (new must beat current on primary metric)
3. Path: staging → ab_test → production (admin-only confirmation)
4. 2-minute cooldown between promotions
5. artifactHash verification display
6. All promotions logged to AuditLog

## Output
apps/web/app/admin/models/page.tsx

## Zone
models

## Dependencies
- M-001

## Priority
90

## Target Files
- apps/web/app/admin/models/page.tsx
- apps/web/app/admin/models/components/PromotionGate.tsx
- services/api/routers/admin_models.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
