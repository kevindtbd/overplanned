# Feature Units Sprint — CHANGELOG

## Initialized
- Date: 2026-02-22
- Plan: docs/plans/2026-02-22-feature-units-sprint.md
- Review: docs/plans/2026-02-22-feature-units-review-notes.md
- Tracks: 15 migrations across 5 waves

## [M-003] COMMIT - 2026-02-22 23:07:14
Infrastructure work complete: rate limiting middleware with 3 tiers, NextAuth redirect validation, and test helpers for transactions and auth mocking
### Verified
- [x] apps/web/lib/rate-limit.ts
- [x] apps/web/lib/auth/config.ts
- [x] apps/web/__tests__/helpers/transaction-mock.ts
- [x] apps/web/__tests__/helpers/auth-factory.ts

## [M-001] INTERRUPT - 2026-02-22 23:07:21
Schema file is being concurrently modified by 3 parallel conductor processes (PIDs 136167, 136169, 136172). All processes started at 23:05 and are executing feature-units-sprint tracks. Detected changes to BackfillTrip model and addition of BackfillLeg model between read attempts, indicating active concurrent writes.
- prisma/schema.prisma

## [M-002] COMMIT - 2026-02-22 23:07:46
Fixed architect blocker B1 by separating LLM hints (ownerTip) from voting data (voteState)
### Verified
- [x] scripts/migrate-vote-state.ts
- [x] apps/web/lib/generation/llm-enrichment.ts

## [M-005] COMMIT - 2026-02-22 23:08:14
Track 2 complete: vote endpoint with Zod schema, quorum logic, 70% yes-only threshold, behavioral signal logging, and 24 passing tests
### Verified
- [x] apps/web/lib/validations/vote.ts
- [x] apps/web/app/api/slots/[slotId]/vote/route.ts
- [x] apps/web/__tests__/api/vote.test.ts

## [M-004] COMMIT - 2026-02-22 23:09:21
Track 1 backend complete: 3 invite endpoints (preview, join, create) with Zod validation, atomic TOCTOU prevention, auth guards, and 35 tests covering happy paths, error states, and schema validation
### Verified
- [x] apps/web/lib/validations/invite.ts
- [x] apps/web/app/api/invites/preview/[token]/route.ts
- [x] apps/web/app/api/trips/[id]/join/route.ts
- [x] apps/web/app/api/trips/[id]/invite/route.ts
- [x] apps/web/__tests__/api/invite.test.ts

## [M-014] COMMIT - 2026-02-22 23:09:52
Extended VALID_SIGNAL_TYPES whitelist with 9 new behavioral signal enum values for feature completeness
### Verified
- [x] apps/web/app/api/signals/behavioral/route.ts

## [M-007] COMMIT - 2026-02-22 23:11:31
Track 4 reflection API: validation schema with HTML strip, route handler with read-merge-write + atomic signal logging, comprehensive test suite
### Verified
- [x] apps/web/lib/validations/reflection.ts
- [x] apps/web/app/api/trips/[id]/reflection/route.ts
- [x] apps/web/__tests__/api/reflection.test.ts

## [M-009] COMMIT - 2026-02-22 23:12:30
Track 6 pivot creation + resolution endpoints with Zod schemas, scoring, caps enforcement, vote reset on swap, and comprehensive test suite
### Verified
- [x] apps/web/lib/validations/pivot.ts
- [x] apps/web/app/api/trips/[id]/pivot/route.ts
- [x] apps/web/app/api/trips/[id]/pivot/[pivotId]/route.ts
- [x] apps/web/__tests__/api/pivot.test.ts

## [M-008] COMMIT - 2026-02-22 23:12:51
Track 5 complete: Zod schemas, POST (LLM generation with sanitization + validation) + PATCH (item toggle with signal logging), PackingList.tsx component with design system compliance, 33 tests covering auth/validation/LLM edge cases/schema units
### Verified
- [x] apps/web/lib/validations/packing.ts
- [x] apps/web/app/api/trips/[id]/packing/route.ts
- [x] apps/web/components/trip/PackingList.tsx
- [x] apps/web/__tests__/api/packing.test.ts

## [M-006] COMMIT - 2026-02-22 23:12:59
Track 3 complete: 3 share endpoints (create token, public view, import) + Zod validation + 28 tests. Import clones Trip+Legs+Slots with fresh UUIDs, enforces 1-import-per-user limit via JSON path query.
### Verified
- [x] apps/web/lib/validations/share.ts
- [x] apps/web/app/api/trips/[id]/share/route.ts
- [x] apps/web/app/api/shared/[token]/route.ts
- [x] apps/web/app/api/shared/[token]/import/route.ts
- [x] apps/web/__tests__/api/share.test.ts

## [M-010] COMMIT - 2026-02-22 23:13:31
Updated invite page to consume unwrapped API response from new /api/invites/preview route
### Verified
- [x] apps/web/app/invite/[token]/page.tsx

## [M-012] COMMIT - 2026-02-22 23:14:05
Removed client-side signal logging and wired reflection page to new server-side API endpoint
### Verified
- [x] apps/web/app/trip/[id]/reflection/page.tsx

## [M-011] COMMIT - 2026-02-22 23:15:11
Wired shared trip page to new API routes with import CTA supporting both signed-in and signed-out states
### Verified
- [x] apps/web/app/s/[token]/page.tsx
- [x] apps/web/app/s/[token]/ImportButton.tsx

## [M-015] COMMIT - 2026-02-22 23:15:18
Created cross-track integration tests verifying feature unit boundaries work correctly. Tests cover invite→vote, import→reflection, vote quorum adjustment, and pivot voteState reset scenarios.
### Verified
- [x] apps/web/__tests__/api/feature-units-integration.test.ts

## [M-013] COMMIT - 2026-02-22 23:16:34
Single-pass wiring of VotePanel, PackingList, share/invite into trip detail page. All group-mode and organizer-only gating applied. No new files created — all additions in the existing page component.
### Verified
- [x] apps/web/app/trip/[id]/page.tsx
