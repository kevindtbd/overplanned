# Feature Units Sprint — MANIFEST

## Dependency Graph

```
M-001 (schema) ──────┬──> M-002 (votestate-migration)
                      ├──> M-003 (infrastructure)
                      └──> M-014 (signal-whitelist)

M-002 + M-003 ───────┬──> M-004 (invite-api)
                      ├──> M-005 (vote-api)
                      ├──> M-006 (share-api)
                      ├──> M-007 (reflection-api)
                      ├──> M-008 (packing-api)
                      └──> M-009 (pivot-api)

M-004 ───────────────> M-010 (wire-invite-page)
M-006 ───────────────> M-011 (wire-share-page)
M-007 ───────────────> M-012 (wire-reflection-page)
M-005 + M-008 + M-009 > M-013 (wire-trip-detail)

M-010 + M-011 + M-012 + M-013 + M-014 > M-015 (integration-tests)
```

## Zone Breakdown

| Zone | Migrations | IDs |
|------|-----------|-----|
| schema | 1 | M-001 |
| infra | 3 | M-002, M-003, M-014 |
| api | 6 | M-004, M-005, M-006, M-007, M-008, M-009 |
| ui | 4 | M-010, M-011, M-012, M-013 |
| test | 1 | M-015 |

## Parallelism Analysis

**Wave 1 (no deps):** M-001 — 1 task (GATE)
**Wave 2 (deps on M-001):** M-002, M-003, M-014 — 3 tasks parallel
**Wave 3 (deps on M-002 + M-003):** M-004, M-005, M-006, M-007, M-008, M-009 — 6 tasks parallel
**Wave 4 (deps on respective Wave 3):** M-010, M-011, M-012, M-013 — 4 tasks parallel
**Wave 5 (deps on all Wave 4):** M-015 — 1 task

**Max parallelism: 6 (Wave 3)**
**Total: 15 migrations**
