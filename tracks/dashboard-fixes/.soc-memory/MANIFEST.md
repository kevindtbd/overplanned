# Dashboard Fixes — MANIFEST

## Dependency Graph

```
M-001 (prisma-singleton) ─────┬──> M-003 (email-pii-fix)
                               ├──> M-007 (fix-type-casts) ──> M-013 (api-route-tests)
                               └──────────────────────────────> M-013

M-002 (middleware-auth-fix)    [independent]

M-004 (fix-nav-routes) ──────> M-005 (trip-back-button)

M-006 (font-lora-fix) ────────┬──> M-011 (error-boundaries)
                               └──> M-012 (dashboard-tests)

M-008 (city-photos-dedup) ───> M-012 (dashboard-tests)

M-009 (progress-bar-aria) ───> M-012 (dashboard-tests)

M-010 (persona-seed-constraint) [independent]

M-012 (dashboard-tests) ─────> M-014 (edge-case-tests)
M-013 (api-route-tests) ─────> M-014 (edge-case-tests)
```

## Zone Breakdown

| Zone | Migrations | IDs |
|------|-----------|-----|
| infra | 1 | M-001 |
| security | 2 | M-002, M-003 |
| ui | 5 | M-004, M-005, M-006, M-009, M-011 |
| api | 2 | M-007, M-010 |
| test | 3 | M-012, M-013, M-014 |

## Parallelism Analysis

**Wave 1 (no deps):** M-001, M-002, M-004, M-006, M-008, M-009, M-010 — 7 tasks
**Wave 2 (deps on wave 1):** M-003, M-005, M-007, M-011 — 4 tasks
**Wave 3 (deps on wave 2):** M-012, M-013 — 2 tasks
**Wave 4 (deps on wave 3):** M-014 — 1 task
