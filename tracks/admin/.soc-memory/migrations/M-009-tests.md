# M-009: Admin Tests

## Description
Full test suite for admin features.

## Task
1. Unit: admin auth guard, promotion safety gate, cost alerting thresholds
2. Integration: admin actions → DB state + AuditLog entries
3. Integration: AuditLog append-only (UPDATE/DELETE rejected at DB level)
4. E2E: admin login → navigate all surfaces → perform actions → verify AuditLog

## Output
services/api/tests/admin/conftest.py

## Zone
tests

## Dependencies
- M-008

## Priority
20

## Target Files
- services/api/tests/admin/conftest.py
- services/api/tests/admin/test_auth_guard.py
- services/api/tests/admin/test_model_promotion.py
- services/api/tests/admin/test_audit_log.py
- services/api/tests/admin/test_cost_alerting.py
- apps/web/__tests__/admin/AdminLayout.test.tsx
- apps/web/__tests__/e2e/admin.spec.ts

## Files
- docs/plans/vertical-plans-v2.md
