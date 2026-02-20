# Admin Track — Changelog

## [M-001] COMMIT - 2026-02-20 13:48:55
Implemented admin access control with systemRole check, separate admin layout navigation, and append-only audit logging capturing actorId, action, targetType, targetId, before/after state, IP address, and user agent for compliance tracking.
### Verified
- [x] apps/web/middleware/admin.ts
- [x] apps/web/app/admin/layout.tsx
- [x] services/api/middleware/audit.py

## [M-003] COMMIT_CONFLICT - 2026-02-20 13:51:10
City seeding admin page with cost estimate confirmation flow, Redis-backed rate limiting (2/min), progress dashboard polling every 5s with per-stage progress bars, audit logging on trigger.
### Verified
- [x] services/api/routers/admin_seeding.py
- [x] apps/web/app/admin/seeding/page.tsx
- [x] apps/web/app/admin/layout.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/app/admin/layout.tsx

## [M-002] COMMIT - 2026-02-20 13:51:49
Model management page with promotion safety gates: list with stage badges, metrics comparison gate, staging→ab_test→production path, 2-min cooldown, artifactHash display, audit logging
### Verified
- [x] services/api/routers/admin_models.py
- [x] apps/web/app/admin/models/components/PromotionGate.tsx
- [x] apps/web/app/admin/models/page.tsx

## [M-004] COMMIT - 2026-02-20 13:52:07
Admin node queue: FastAPI backend with 5 audit-logged endpoints, client-side page with filterable/sortable table, and modal editor with details/aliases/signals tabs. All mutations write before/after to AuditLog via existing audit_action contract.
### Verified
- [x] services/api/routers/admin_nodes.py
- [x] apps/web/app/admin/nodes/components/NodeEditor.tsx
- [x] apps/web/app/admin/nodes/page.tsx

## [M-006] COMMIT - 2026-02-20 13:55:14
Admin user management: search page with tier/email filters, detail page with signal/trip history, feature flag override editor with toggle UI, subscription tier changer (replaces manual SQL), all actions audit-logged
### Verified
- [x] apps/web/app/admin/users/page.tsx
- [x] apps/web/app/admin/users/[id]/page.tsx
- [x] services/api/routers/admin_users.py

## [M-007] COMMIT_CONFLICT - 2026-02-20 13:55:47
Pipeline health dashboard with 4 sections: LLM costs by model/date/stage, external API call counts per provider, pipeline job success/failure rates, and configurable cost alerting with threshold editing. Backend provides 5 endpoints (4 GET + 1 PUT) using raw SQL aggregations. Frontend renders parallel-fetched data in tables, stat cards, and progress bars matching the admin design system.
### Verified
- [x] services/api/routers/admin_pipeline.py
- [x] apps/web/app/admin/pipeline/page.tsx
- [x] apps/web/app/admin/layout.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/app/admin/layout.tsx

## [M-005] COMMIT_CONFLICT - 2026-02-20 13:56:01
Source freshness dashboard with scraper health monitoring, configurable staleness alerts, and audit-logged authority score management. Data aggregated from QualitySignal table — no schema changes needed.
### Verified
- [x] apps/web/app/admin/sources/page.tsx
- [x] services/api/routers/admin_sources.py
- [x] apps/web/app/admin/layout.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/app/admin/layout.tsx

## [M-008] COMMIT_CONFLICT - 2026-02-20 13:59:07
Trust & Safety admin panel: token management (view/revoke for SharedTripToken + InviteToken) and injection detection review queue (flagged prompt bar inputs from RawEvent). All actions audit-logged. Frontend matches existing admin design system.
### Verified
- [x] services/api/routers/admin_safety.py
- [x] apps/web/app/admin/safety/page.tsx
- [x] apps/web/app/admin/safety/components/TokenManager.tsx
- [x] apps/web/app/admin/safety/components/InjectionQueue.tsx
- [x] apps/web/app/admin/layout.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/app/admin/layout.tsx

## [M-009] COMMIT - 2026-02-20 14:05:49
Full admin test suite: 44+ test cases across unit (auth guard, promotion safety gate, cost alerting), integration (admin actions → AuditLog, append-only enforcement), component (AdminLayout), and E2E (Playwright full admin flow). Follows foundation track patterns with factory functions and mock Prisma.
### Verified
- [x] services/api/tests/__init__.py
- [x] services/api/tests/admin/__init__.py
- [x] services/api/tests/admin/conftest.py
- [x] services/api/tests/admin/test_auth_guard.py
- [x] services/api/tests/admin/test_model_promotion.py
- [x] services/api/tests/admin/test_audit_log.py
- [x] services/api/tests/admin/test_cost_alerting.py
- [x] apps/web/__tests__/admin/AdminLayout.test.tsx
- [x] apps/web/__tests__/e2e/admin.spec.ts
