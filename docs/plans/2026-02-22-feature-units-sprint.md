# Feature Units Sprint — UI <-> API Wiring + ML Scaffolding

**Date:** 2026-02-22
**Scope:** 6 functional units wiring existing UI to new Next.js API routes
**Philosophy:** MVP with future-proof schema scaffolding. No ML training. No new UI components (almost everything exists).
**Review status:** Brainstorm complete, deepened (8 issues), agent-reviewed (architect + security + test-engineer)

---

## Executive Summary

Most UI components already exist (VotePanel, PivotDrawer, Reflection page, Invite page, Share page). This sprint is primarily:
- **New API routes** to back the existing UI
- **Wiring** existing components to those routes
- **Schema additions** for packing list + reflection storage + ML scaffolding
- **One new UI**: Packing list tab (only greenfield component)
- **Infrastructure**: Rate limiting, test helpers, auth hardening

---

## Two-Phase Execution

**Phase 1 — Parallel (API + Backend):**
```
Track 0: Schema migration + infrastructure (GATE — must complete before all others)
Track 1: Invite API (POST /api/trips/[id]/join, GET /api/invites/preview/[token], POST /api/trips/[id]/invite)
Track 2: Vote API (POST /api/slots/[slotId]/vote)
Track 3: Share API (GET /api/shared/[token], POST /api/shared/[token]/import, POST /api/trips/[id]/share)
Track 4: Reflection API (POST /api/trips/[id]/reflection)
Track 5: Packing API + PackingList.tsx component (POST + PATCH /api/trips/[id]/packing)
Track 6: Pivot API (POST /api/trips/[id]/pivot, PATCH /api/trips/[id]/pivot/[pivotId])
```

**Phase 2 — Sequential (UI Wiring):**
```
Track 7: Wire all UI into existing pages
  - Update invite page fetch URL + unwrap response
  - Update shared trip page fetch URL + unwrap response + add import CTA
  - Wire reflection page submit handler + remove client-side signal logging
  - Wire VotePanel into trip detail (group mode)
  - Wire PackingList into trip detail
  - Wire mood trigger button into trip detail
  - Update /api/signals/behavioral VALID_SIGNAL_TYPES whitelist
```

**Why two phases:** Tracks 2, 5, and 6 all modify `trip/[id]/page.tsx`. Parallel edits to the same file = merge conflict hell. Phase 1 does all API routes + standalone components in parallel. Phase 2 wires everything into the shared page.tsx in a single sequential pass.

---

## Schema Changes (Single Migration)

All schema changes in one migration to avoid conflicts between parallel tracks.

### New Fields on Trip
```prisma
model Trip {
  // ... existing fields ...
  packingList     Json?      // LLM-generated checklist, stored as { items: PackingItem[] }
  reflectionData  Json?      // Post-trip ratings + feedback, keyed by userId: { "user-abc": { ratings, feedback, submittedAt } }
}
```

### New Field on ItinerarySlot
```prisma
model ItinerarySlot {
  // ... existing fields ...
  ownerTip        String?    // LLM-generated local tip per slot (migrated from voteState.narrativeHint)
}
```

### New Index on TripMember
```prisma
model TripMember {
  // ... existing fields ...
  @@index([tripId, status])  // Vote quorum queries: count joined members per trip
}
```

### New SignalType Enum Values
```prisma
enum SignalType {
  // ... existing ...
  vote_cast           // Group voting signal
  invite_accepted     // Invite flow signal
  invite_declined     // Invite flow signal
  trip_shared         // Share action signal
  trip_imported       // Import from shared link
  packing_checked     // Packing list interaction
  packing_unchecked   // Packing list interaction
  mood_reported       // User mood pivot trigger
  slot_moved          // Fixes existing `as never` hack in codebase
}
```

### No New Tables
Everything fits into existing models. `packingList` and `reflectionData` are JSONB because they're read/written as single units, never queried individually, and future ML reads the full blob.

---

## Track 0: Schema Migration + Infrastructure (GATE)

**Must complete before ANY other track starts. Enforced as conductor dependency.**

### 0a. Schema Migration
- `prisma/schema.prisma` — add new fields, enum values, TripMember index
- Run `npx prisma migrate dev --name feature-units-schema` (maintain migration chain, not db push)

### 0b. voteState -> ownerTip Data Migration
- **Problem (B1):** LLM enrichment writes `{ narrativeHint: "..." }` to `ItinerarySlot.voteState`. Vote API would overwrite this. Data loss bug.
- **Fix:** Write a migration script that:
  1. Reads all slots where `voteState` contains `narrativeHint`
  2. Copies `voteState.narrativeHint` -> `ownerTip` field
  3. Sets `voteState = null` on those slots
- Update `lib/generation/llm-enrichment.ts` to write `ownerTip` instead of `voteState.narrativeHint`

### 0c. Rate Limiting Middleware
- **Problem (V5):** Zero rate limiting in codebase.
- **Fix:** Basic in-memory rate limiter (`lib/rate-limit.ts`):
  - 30 req/min for public endpoints (invite preview, shared trip view)
  - 10 req/min for authenticated write endpoints
  - 3 req/hour for LLM-calling endpoints (packing generation)
- Token bucket or sliding window, Map-based (no Redis needed for beta)

### 0d. NextAuth Redirect Callback
- **Problem (V3):** No `redirect` callback in NextAuth config. Open redirect vulnerability.
- **Fix:** Add `redirect` callback to `lib/auth/config.ts` that validates redirect URLs against allowed origins.

### 0e. Test Infrastructure
- Extract shared `$transaction` mock helper to `__tests__/helpers/transaction-mock.ts`
- Extract auth+membership mock factory to `__tests__/helpers/auth-factory.ts`
- Add test that `VALID_SIGNAL_TYPES` whitelist stays in sync with Prisma enum

### Files
- `prisma/schema.prisma` — modified
- `prisma/migrations/YYYYMMDD_feature_units_schema/migration.sql` — new (generated)
- `apps/web/lib/generation/llm-enrichment.ts` — modified (ownerTip)
- `apps/web/lib/rate-limit.ts` — new
- `apps/web/lib/auth/config.ts` — modified (redirect callback)
- `apps/web/__tests__/helpers/transaction-mock.ts` — new
- `apps/web/__tests__/helpers/auth-factory.ts` — new
- `scripts/migrate-vote-state.ts` — new (one-time data migration)

---

## Track 1: Group Invite Flow

**Goal:** Wire the existing `/invite/[token]/page.tsx` to Next.js API routes.

### API Routes

**GET /api/invites/preview/[token]** (public — no auth required)
- Validates token format (regex + 64 char limit)
- Looks up InviteToken, checks not expired/revoked, usedCount < maxUses
- Returns flat JSON: `{ tripId, destination, city, country, startDate, endDate, memberCount, valid, organizerName }`
- Does NOT expose member list or itinerary (public endpoint)
- Rate limited: 30 req/min (public tier)

**POST /api/trips/[id]/join** (auth required)
- **Token via query param:** `?token=xxx` (matches existing InviteJoinButton.tsx — zero UI changes needed)
- Validates token (same checks as preview)
- Checks user isn't already a TripMember
- **Atomic accept (V1):** Uses `$queryRaw` inside `$transaction`:
  ```sql
  UPDATE "InviteToken" SET "usedCount" = "usedCount" + 1
  WHERE token = $1 AND "usedCount" < "maxUses" AND "revokedAt" IS NULL AND "expiresAt" > NOW()
  RETURNING *
  ```
  If returns 0 rows -> 409 (token exhausted/expired)
- Creates TripMember with `role: token.role, status: "joined", joinedAt: now()`
- Logs BehavioralSignal: `invite_accepted` (server-side, atomic in transaction)
- Returns flat JSON: `{ tripId }` (client redirects to `/trip/[tripId]`)
- **Token security (V2):** Create invite uses `crypto.randomBytes(32).toString('base64url')` (256 bits)

**POST /api/trips/[id]/invite** (auth required, organizer only)
- Creates InviteToken with secure random token, maxUses (default: 10), expiresAt (default: 7 days)
- Only works for group mode trips
- Returns: `{ token, inviteUrl, expiresAt }`

### Auth Pattern
- Preview: no auth, rate limited
- Join: auth required (creates membership)
- Create invite: organizer + joined + group mode

### Files
- `apps/web/app/api/invites/preview/[token]/route.ts` — new
- `apps/web/app/api/trips/[id]/join/route.ts` — new (was `/api/invites/[token]/accept` in original plan)
- `apps/web/app/api/trips/[id]/invite/route.ts` — new
- `apps/web/lib/validations/invite.ts` — new (Zod schemas)

---

## Track 2: Group Voting

**Goal:** Create vote API endpoint. VotePanel component already exists.

### API Routes

**POST /api/slots/[slotId]/vote** (auth required, joined member)
- Body: `{ vote: "yes" | "no" | "maybe" }`
- **Auth (V4):** Resolve slot -> trip from DB via nested query (existing pattern from slot status route). Never trust tripId from request body.
- **Serializable transaction (V10):** Read-modify-write on `voteState` JSON needs serializable isolation:
  1. Read current `voteState`
  2. Merge new vote: `voteState.votes[userId] = vote`
  3. Count quorum: query `TripMember WHERE tripId AND status = 'joined'` (count at vote time, not cached)
  4. If all joined members voted: check threshold
  5. Write updated `voteState` + maybe update `slot.status`
- **Threshold rule:** 70% means yes-only. Maybe counts as neither yes nor no.
- Auto-confirm: all voted AND yes% >= 70% -> `voteState.state = "confirmed"`, `slot.status = "confirmed"`
- Auto-contest: all voted AND yes% < 70% -> `voteState.state = "contested"`
- Logs BehavioralSignal: `vote_cast` with signalValue (yes=1.0, maybe=0.5, no=-1.0)
- **Response wrapper (C1):** Returns `{ success: true, data: { voteState, slotStatus } }` to match slot-family convention

### Vote State Machine
```
proposed -> voting   (first vote cast)
voting -> confirmed  (all voted, >= 70% yes)
voting -> contested  (all voted, < 70% yes)
contested -> voting  (organizer resets — future feature, not in MVP)
```

### Files
- `apps/web/app/api/slots/[slotId]/vote/route.ts` — new
- `apps/web/lib/validations/vote.ts` — new (Zod schema)

---

## Track 3: Shared Trips

**Goal:** Wire the existing `/s/[token]/page.tsx` to Next.js API routes. Add import flow.

### API Routes

**GET /api/shared/[token]** (public — no auth required)
- Validates token format
- Looks up SharedTripToken, checks not expired/revoked
- Increments `viewCount`
- Returns flat JSON (trip preview + slots grouped by day)
- Strips: member PII, internal IDs, voteState, behavioral data
- Rate limited: 30 req/min (public tier)

**POST /api/shared/[token]/import** (auth required)
- Creates a new Trip cloned from the shared trip (new UUIDs for ALL entities)
- **Import mode:** Always `mode: "solo"`. Importer is sole organizer. Can switch to group later.
- Clones ItinerarySlots (new IDs, reset status to "proposed", clear voteState)
- Does NOT clone members, votes, or behavioral signals
- **Import limit (V9):** 1 import per user per shared token. Check existing trips with matching source metadata.
- Increments `importCount` on SharedTripToken
- Logs BehavioralSignal: `trip_imported`
- Returns: `{ tripId }` (client redirects to new trip)

**POST /api/trips/[id]/share** (auth required, organizer only)
- Creates SharedTripToken with secure random token (256-bit), expiresAt (default: 30 days)
- Returns: `{ token, shareUrl, expiresAt }`

### Files
- `apps/web/app/api/shared/[token]/route.ts` — new
- `apps/web/app/api/shared/[token]/import/route.ts` — new
- `apps/web/app/api/trips/[id]/share/route.ts` — new
- `apps/web/lib/validations/share.ts` — new (Zod schema)

---

## Track 4: Post-Trip Reflection

**Goal:** Wire the existing reflection page's submit handler to persist data.

### API Routes

**POST /api/trips/[id]/reflection** (auth required, joined member)
- Body:
  ```json
  {
    "ratings": [
      { "slotId": "...", "rating": "loved" | "skipped" | "missed" }
    ],
    "feedback": "Free text, max 500 chars"
  }
  ```
- **Feedback sanitization (V7):** Zod transform strips HTML tags from feedback field
- **UserId from session (V8):** `reflectionData` userId key MUST come from `session.user.id`, never request body
- Validates trip status is "completed" or "active"
- **Read-merge-write:** Reads existing `reflectionData`, merges new user's entry, writes back (never blind overwrite):
  ```json
  {
    "user-abc": { "ratings": [...], "feedback": "...", "submittedAt": "2026-..." },
    "user-def": { "ratings": [...], "feedback": "...", "submittedAt": "2026-..." }
  }
  ```
- Logs BehavioralSignals server-side in `$transaction` for each rating (post_loved/post_skipped/post_missed)
- Returns flat JSON: `{ submitted: true }`

### Files
- `apps/web/app/api/trips/[id]/reflection/route.ts` — new
- `apps/web/lib/validations/reflection.ts` — new (Zod schema with HTML strip transform)

---

## Track 5: Packing List

**Goal:** LLM-generated packing list stored on trip, with checklist UI.

### API Routes

**POST /api/trips/[id]/packing** (auth required, joined member)
- Generates packing list using Claude Haiku (classification task, ~400 tokens)
- **Input sanitization (V6):** Sanitize all LLM inputs (destination, template name, persona values). Validate output schema. Cap item text at 100 chars.
- Prompt inputs: destination, dates, trip duration, template, personaSeed
- Output shape stored in `Trip.packingList`:
  ```json
  {
    "items": [
      { "id": "uuid", "text": "Sunscreen SPF 50+", "category": "essentials", "checked": false }
    ],
    "generatedAt": "2026-...",
    "model": "claude-haiku-4-5-20251001"
  }
  ```
- Categories: essentials, clothing, documents, tech, toiletries, misc
- **Regeneration:** Accepts optional `{ regenerate: true }` flag. Regeneration clears all checked states. Default (no flag) returns existing list if present.
- Rate limited: 3 req/hour (LLM tier)
- Returns: `{ packingList }`

**PATCH /api/trips/[id]/packing** (auth required, joined member)
- Body: `{ itemId: string, checked: boolean }`
- Updates `checked` field on specific item in JSONB array
- Logs BehavioralSignal: `packing_checked` or `packing_unchecked`
- Returns: `{ packingList }`

### UI Component (New)
- **`components/trip/PackingList.tsx`** — new component
- Tab or expandable section on trip detail page
- Categorized checklist with checkboxes
- "Generate packing list" button if none exists, "Regenerate" button if exists
- Progress indicator: "12/18 packed"
- Only visible for trips in planning/active status

### Files
- `apps/web/app/api/trips/[id]/packing/route.ts` — new
- `apps/web/lib/validations/packing.ts` — new (Zod schema)
- `apps/web/components/trip/PackingList.tsx` — new

---

## Track 6: Pivot Trigger (User Mood)

**Goal:** Let users trigger a pivot via mood input. Wire PivotDrawer to show alternatives.

### API Routes

**POST /api/trips/[id]/pivot** (auth required, joined member)
- Body: `{ slotId: string, trigger: "user_mood" | "user_request", reason?: string }`
- Validates: slot belongs to trip, slot is in confirmed/active status, trip is active
- **Pivot caps (V11):** Max 3 active pivots per trip, max 1 per slot. Return 409 if exceeded.
- Fetches alternative ActivityNodes (same city, same category or adjacent, not already in trip)
- Scoring: authorityScore (40%) + vibe tag overlap with personaSeed (40%) + random jitter (20%)
- Returns top 3 alternatives (empty array is fine for unseeded cities — PivotDrawer shows "No alternatives available")
- Creates PivotEvent: `{ tripId, slotId, triggerType, originalNodeId, alternativeIds, status: "proposed" }`
- Logs BehavioralSignal: `mood_reported`
- Returns: `{ pivotEvent, alternatives: SwapCandidate[] }`

**PATCH /api/trips/[id]/pivot/[pivotId]** (auth required, joined member)
- Body: `{ outcome: "accepted" | "rejected", selectedNodeId?: string }`
- **Validate selectedNodeId (test risk #4):** Must exist in PivotEvent.alternativeIds array
- Updates PivotEvent status + resolvedAt + responseTimeMs + selectedNodeId
- If accepted: updates ItinerarySlot (swap activityNodeId, set wasSwapped, swappedFromId)
- **Pivot on voted slot:** If slot had voting, reset voteState to null after swap
- Logs BehavioralSignal: `pivot_accepted` or `pivot_rejected`
- Returns: `{ pivotEvent, updatedSlot? }`

### Files
- `apps/web/app/api/trips/[id]/pivot/route.ts` — new (POST create)
- `apps/web/app/api/trips/[id]/pivot/[pivotId]/route.ts` — new (PATCH resolve)
- `apps/web/lib/validations/pivot.ts` — new (Zod schema)

---

## Track 7: UI Wiring (Phase 2 — Sequential)

**Depends on:** All Phase 1 tracks complete.

### 7a. Invite Page
- `apps/web/app/invite/[token]/page.tsx` — change fetch URL to `/api/invites/preview/${token}`, unwrap response (read `json` directly, not `json.data`)

### 7b. Shared Trip Page
- `apps/web/app/s/[token]/page.tsx` — change fetch URL to `/api/shared/${token}`, unwrap response, add "Import this trip" CTA button

### 7c. Reflection Page
- `apps/web/app/trip/[id]/reflection/page.tsx` — wire submit handler to POST `/api/trips/[id]/reflection`, remove client-side `sendBehavioralSignal` calls (server is source of truth)

### 7d. Trip Detail Page (Single Pass)
- `apps/web/app/trip/[id]/page.tsx` — in ONE sequential pass:
  - Render VotePanel for each slot when `trip.mode === "group"` and slot is in voting/proposed state
  - Add PackingList section (below slots, above settings, planning/active only)
  - Add "Not feeling it?" mood trigger button on each slot card (active trips only)
  - Add "Invite" button in header (organizer, group mode)
  - Add "Share" button in header (organizer)

### 7e. Signal Whitelist
- `apps/web/app/api/signals/behavioral/route.ts` — add 9 new enum values to `VALID_SIGNAL_TYPES`

### Files Modified
- `apps/web/app/invite/[token]/page.tsx`
- `apps/web/app/s/[token]/page.tsx`
- `apps/web/app/trip/[id]/reflection/page.tsx`
- `apps/web/app/trip/[id]/page.tsx`
- `apps/web/app/api/signals/behavioral/route.ts`

---

## Cross-Cutting Concerns

### Auth Pattern (Copy from existing routes)
All authed endpoints follow:
1. `getServerSession(authOptions)` -> 401 if null
2. `prisma.tripMember.findUnique({ where: { tripId_userId } })` -> 404 if null
3. Check `membership.status === "joined"` -> 404 if not
4. Check `membership.role === "organizer"` -> 403 if needed

### Signal Logging
- All new endpoints log signals **server-side** in `$transaction` blocks (atomic with write)
- Reflection page: REMOVE existing client-side signal logging (dedup)
- PivotDrawer, SwipeDeck etc: existing client-side logging stays untouched

### Validation
- All body parsing uses Zod schemas in `lib/validations/`
- 6 new schemas: invite, vote, reflection, packing, pivot-create, pivot-resolve
- Zod schema unit tests for all 6

### Token Security
- All new tokens (invite, share) use `crypto.randomBytes(32).toString('base64url')` (256-bit)
- Not `crypto.randomUUID()` (only 122 bits)

### Error Handling
- All routes wrap in try/catch with `console.error` + 500 response
- Specific error codes: 400 (validation), 401 (no session), 403 (wrong role), 404 (not found/not member), 409 (invalid state/race condition)

---

## Files Created/Modified Summary

### Track 0 (Schema + Infrastructure) — 8 files
- `prisma/schema.prisma` — modified
- `apps/web/lib/generation/llm-enrichment.ts` — modified
- `apps/web/lib/rate-limit.ts` — new
- `apps/web/lib/auth/config.ts` — modified
- `apps/web/__tests__/helpers/transaction-mock.ts` — new
- `apps/web/__tests__/helpers/auth-factory.ts` — new
- `scripts/migrate-vote-state.ts` — new

### Tracks 1-6 (API Routes) — 15 files
- 10 API route files (new)
- 6 validation schema files (new) in `lib/validations/`
- 1 UI component (PackingList.tsx, new) — built in Track 5

### Track 7 (UI Wiring) — 5 files modified
- invite page, shared trip page, reflection page, trip detail page, signal route

### Total: ~28 files (18 new, 10 modified)

---

## Test Strategy

**Estimated: 130-150 tests** (corrected from original 100 — underscoped by ~50%).

Each track gets:
1. **API route tests** — auth guards, validation, state machine, happy path, error paths
2. **Zod schema unit tests** — all 6 new schemas
3. **Integration checks** — signal logging, JSONB shape, membership checks

### Highest-Risk Tests (Must Not Skip)
1. "Maybe" vote threshold — 70% means yes-only, maybe is neither
2. Multi-user reflection JSONB merge — read-merge-write, not blind overwrite
3. Concurrent invite accepts exceeding maxUses — atomic SQL
4. Pivot selectedNodeId validated against alternativeIds array
5. Cloned trip generates new UUIDs for all entities

### Cross-Track Integration Tests
- Invite -> Vote (new member can immediately vote)
- Import -> Reflection (reflection works on cloned trips)
- Vote quorum after invite (confirmed slots stay confirmed)
- Pivot on voted slot (voteState resets after swap)

### Test Infrastructure (Track 0)
- Shared `$transaction` mock helper
- Auth+membership mock factory
- `VALID_SIGNAL_TYPES` sync test with Prisma enum

---

## Design Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Vote threshold: 70% yes-only | "Maybe" is indecisive, shouldn't count as approval |
| D2 | Imported trips: always solo mode | Original might be group, but importer starts fresh |
| D3 | Response wrappers: flat JSON for new routes | Matches existing trips/slots convention. Unwrap invite+share UIs |
| D4 | Vote route wrapper: `{ success, data }` | Matches slot-family convention (status, move, swap) |
| D5 | Signal logging: server-side only for new routes | Atomic with write, no dedup needed |
| D6 | Packing regeneration: explicit flag | Trip details can change (summer->winter), need manual refresh |
| D7 | Pivot fallback: empty array for unseeded cities | LLM fallback is a fast-follow, not MVP |
| D8 | Quorum: members at vote time | Late joiners don't retroactively affect existing votes |

---

## What This Sprint Does NOT Include
- ML training or model updates
- Notification delivery (email/push) — just signal logging
- Real-time updates (WebSocket/SSE for live voting) — polling is fine for MVP
- Organizer vote reset (contested -> voting) — future feature
- LLM-powered pivot alternatives — deterministic scoring only (LLM fallback is fast-follow)
- Packing list editing (add/remove items) — just check/uncheck + regenerate
- Photo upload for reflections — just ratings + text
- CSRF token validation — acceptable for beta with default same-origin CORS (V14)

---

## Security Findings (Full List)

See `docs/plans/2026-02-22-feature-units-review-notes.md` for complete agent review findings including:
- V1-V15 security vulnerabilities (V1 critical, V2-V5 high, V6-V11 medium, V12-V15 low/deferred)
- B1-B2 architect blockers (both addressed in Track 0)
- C1-C7 architect concerns (all incorporated)
- Test engineer infrastructure gaps (all addressed in Track 0)
