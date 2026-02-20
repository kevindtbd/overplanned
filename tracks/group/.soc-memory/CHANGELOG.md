# Group Trip Track — Changelog

## M-001: Schema Extension — 2026-02-20

### Verified
- `Trip`: `fairnessState Json?`, `affinityMatrix Json?`, `logisticsState Json?` — already present
- `ItinerarySlot`: `voteState Json?`, `isContested Boolean @default(false)` — already present
- `TripMember`: `personaSeed Json?`, `energyProfile Json?` — already present
- `InviteToken` and `SharedTripToken` models — already present

---

## M-002: Invite Flow — 2026-02-20

### Added
- `services/api/routers/invites.py` — 4 endpoints: create, list, revoke, join (all organizer-gated except join)
- `apps/web/app/invite/[token]/page.tsx` — Server component: invite preview with destination card
- `apps/web/app/invite/[token]/InviteJoinButton.tsx` — Client component: OAuth-aware join flow
- `apps/web/app/api/trips/[id]/join/route.ts` — Proxy route: strips token, injects X-User-Id, proxies to FastAPI
- `services/api/routers/invites.py` preview endpoint — public, no auth, no PII

### Security
- 32-byte CSPRNG token, maxUses=1, 7-day expiry
- Identical 404 for expired/revoked/nonexistent/maxed (no enumeration)
- Role hard-coded to member (never organizer via invite)

---

## M-003: Group Generation Engine — 2026-02-20

### Added
- `services/api/generation/preference_merger.py` — Merges N persona seeds with fairness-weighted Qdrant query
- `services/api/generation/group_engine.py` — Full group generation pipeline (same 9-step structure as solo)

### Design
- Base weight = 1/N, fairness boost up to +0.20 for high-debt members
- GROUP_CANDIDATE_POOL_SIZE = 40 (vs solo's 20)
- Slots inserted with voteState='proposed', isContested=false
- RawEvent payload carries memberScores per candidate

---

## M-004: Async Voting — 2026-02-20

### Added
- `apps/web/components/group/voting/VotePanel.tsx` — Per-slot yes/maybe/no voting UI
- `apps/web/components/group/voting/CampDetector.tsx` — Split detection (60% quorum, 25% camp minimum)
- `apps/web/components/group/voting/ConflictResolver.tsx` — Alternative voting with group-fit bars

---

## M-005: Fairness Engine — 2026-02-20

### Added
- `services/api/group/fairness.py` — Deterministic debt tracking: delta = member_rank - group_rank, clamps at +/-10.0
- `services/api/group/abilene_detector.py` — Triggers dissent prompt when all enthusiasm < 0.4
- `services/api/group/__init__.py` — Package export

---

## M-006: Shared Trip Links — 2026-02-20

### Added
- `services/api/routers/shared_trips.py` — Create (organizer, 90-day expiry) + view (public, sanitized)
- `apps/web/app/s/[token]/page.tsx` — Public read-only view with CSP, X-Frame-Options, no PII

### Security
- Per-IP rate limit: 30 req/min via Redis sorted-set sliding window
- CSP: script-src 'none', X-Frame-Options: DENY
- Images only from images.unsplash.com
- robots: noindex, nofollow

---

## M-007: Group Social Surface — 2026-02-20

### Added
- `apps/web/components/group/social/GroupDashboard.tsx` — 3-tab layout (Energy/Pulse/Affinity)
- `apps/web/components/group/social/PulseLine.tsx` — SVG line+area chart, zero external deps
- `apps/web/components/group/social/EnergyBars.tsx` — Per-member energy bars with debt badges
- `apps/web/components/group/social/AffinityMatrix.tsx` — N*N heatmap with split suggestions

---

## M-008: Group Tests — 2026-02-20

### Added
- `services/api/tests/group/__init__.py` — Package marker
- `services/api/tests/group/conftest.py` — 3 users, group trip, invite/token state fixtures
- `services/api/tests/group/test_voting.py` — 26 tests: voting, approval, camps, conflict, Abilene, quorum
- `services/api/tests/group/test_invites.py` — 21 tests: token gen, validation, enumeration prevention
- `services/api/tests/group/test_shared_links.py` — 26 tests: create, view tracking, expiry, rate limiting
- `apps/web/__tests__/group/GroupDashboard.test.tsx` — ~40 tests: rendering, energy, affinity, pulse
- `apps/web/__tests__/e2e/group.spec.ts` — 26 tests: full group lifecycle E2E

### Invariants
- All rejection errors produce identical error codes (no enumeration)
- Fairness engine is zero-sum: sum(all debts) == 0
- Determinism: same inputs always produce same outputs
