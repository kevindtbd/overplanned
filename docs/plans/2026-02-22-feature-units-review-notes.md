# Feature Units Sprint — Deepening Review Notes

**Date:** 2026-02-22

## Issues Found & Resolutions

### 1. Invite endpoint mismatch (Critical)
**Issue:** Plan creates `POST /api/invites/[token]/accept`, but `InviteJoinButton.tsx` already calls `POST /api/trips/${tripId}/join?token=${token}`. These don't match.
**Resolution:** Create `POST /api/trips/[id]/join` with token as query param. Zero changes needed to InviteJoinButton.tsx — it already works this way. Update plan Track 1 file list accordingly.

### 2. API response wrapper mismatch (Critical)
**Issue:** Both invite page (line 56) and shared trip page (line 133) expect `{ success: true, data: { ... } }` wrapper in API responses. Plan's response shapes are flat JSON without this wrapper.
**Resolution:** Unwrap both UIs — update the page fetch logic to read `json` directly instead of `json.data`. Cleaner pattern, aligns with all other existing API routes (trips, slots) which return flat JSON.

### 3. Signal logging duplication & whitelist gap (Medium)
**Issue:** The existing `/api/signals/behavioral` route has a `VALID_SIGNAL_TYPES` whitelist that doesn't include the 8 new enum values (vote_cast, packing_checked, etc.). Also, the reflection page fires signals client-side AND the plan wants server-side logging — double-write risk.
**Resolution:**
- New API routes (vote, reflection, packing, pivot) log signals **server-side** in their `$transaction` blocks. Atomic with the write.
- Remove client-side signal logging from reflection page (server is source of truth).
- Update `VALID_SIGNAL_TYPES` in the behavioral signal route to include new enum values, so other client components can use them if needed later.
- Existing client-side logging in PivotDrawer, SwipeDeck, etc. stays untouched.

### 4. Vote quorum with late joiners (Medium)
**Issue:** If a new member joins via invite (Track 1) while voting is in progress, their absence skews the "all members voted" check.
**Resolution:** Count joined members **at vote time** (query TripMember WHERE status=joined at each vote). New joiners see existing votes but aren't counted in quorum until they cast their own vote. No retroactive recalculation needed.

### 5. Packing list regeneration (Medium)
**Issue:** Plan says "idempotent: if packingList exists, return it" — but trip details can change after generation (date shift summer→winter, destination change).
**Resolution:** POST /api/trips/[id]/packing accepts optional `{ regenerate: true }` flag. UI shows a "Regenerate" button. Regeneration clears all checked states. Default behavior (no flag) still returns existing list.

### 6. Imported trip mode (Low)
**Issue:** Plan doesn't specify what `mode` the imported trip gets. Original might be "group" but importer is solo.
**Resolution:** Imported trips always start as `mode: "solo"`. Importer is sole organizer. They can switch to group mode and invite others later.

### 7. Trip detail page.tsx merge conflicts (Medium)
**Issue:** Tracks 2 (VotePanel), 5 (PackingList), and 6 (mood trigger) all modify `trip/[id]/page.tsx`. Three parallel tracks editing the same file = merge conflict hell.
**Resolution:** Split execution into two phases:
- **Phase 1** (parallel): All API routes + validation schemas + standalone components (Tracks 1-6 backend work)
- **Phase 2** (sequential): Trip detail page.tsx UI integration — wire VotePanel, PackingList, and mood trigger button in a single pass

### 8. Pivot LLM fallback (Deferred)
**Issue:** For unseeded cities, pivot returns empty alternatives array. LLM fallback could generate alternatives and produce valuable training data.
**Resolution:** Empty array is fine for MVP — PivotDrawer shows "No alternatives available" message. LLM fallback noted as fast-follow: creates ActivityNodes on-the-fly, adds ~2-3s latency, needs ephemeral vs persistent node decision. Worth doing after deterministic path is stable.

## Updated Track Layout

```
Phase 1 — Parallel (API + Backend):
  Track 0: Schema migration (must run first)
  Track 1: Invite API (POST /api/trips/[id]/join, GET /api/invites/preview/[token], POST /api/trips/[id]/invite)
  Track 2: Vote API (POST /api/slots/[slotId]/vote)
  Track 3: Share API (GET /api/shared/[token], POST /api/shared/[token]/import, POST /api/trips/[id]/share)
  Track 4: Reflection API (POST /api/trips/[id]/reflection)
  Track 5: Packing API + PackingList.tsx component (POST + PATCH /api/trips/[id]/packing)
  Track 6: Pivot API (POST /api/trips/[id]/pivot, PATCH /api/trips/[id]/pivot/[pivotId])

Phase 2 — Sequential (UI Wiring):
  Track 7: Wire all UI
    - Update invite page fetch URL + unwrap response
    - Update shared trip page fetch URL + unwrap response + add import CTA
    - Wire reflection page submit handler
    - Wire VotePanel into trip detail (group mode)
    - Wire PackingList into trip detail
    - Wire mood trigger button into trip detail
    - Update /api/signals/behavioral VALID_SIGNAL_TYPES whitelist
```

## Agent Review Findings (2026-02-22)

### Architect Review

**Blockers:**
- **B1: voteState field collision.** LLM enrichment writes `{ narrativeHint: "..." }` to `ItinerarySlot.voteState`. Vote API would overwrite with `{ state: "voting", votes: {...} }`. Data loss bug.
  - **Fix in Track 0:** Copy `voteState.narrativeHint` → new `ownerTip` field for existing slots. Update `lib/generation/llm-enrichment.ts` to write to `ownerTip` instead of `voteState`. Set `voteState = null` on migrated slots.
- **B2: Enum migration must be strict gate.** Track 0 must complete before ANY other track starts. Enforce as conductor dependency, not just ordering.

**Concerns (incorporated):**
- C1: Vote route should return `{ success: true, data: {...} }` to match slot-family convention (status, move, swap routes all use this wrapper).
- C3: Add `@@index([tripId, status])` on TripMember for vote quorum queries.
- C5: Add `slot_moved` to SignalType enum while we're touching it (fixes existing `as never` hack).
- C7: Use `prisma migrate dev --name feature-units-schema` instead of `db push` to maintain migration chain.

### Security Review

**Critical:**
- **V1: Invite accept TOCTOU race on usedCount/maxUses.** Two simultaneous accepts both pass `usedCount < maxUses` check. Fix: atomic `UPDATE ... SET usedCount = usedCount + 1 WHERE usedCount < maxUses RETURNING *` via `$queryRaw` inside transaction.

**High:**
- **V2:** Use `crypto.randomBytes(32).toString('base64url')` (256 bits) instead of `crypto.randomUUID()` (122 bits) for tokens.
- **V3:** Add `redirect` callback to NextAuth config to prevent open redirect (pre-existing gap).
- **V4:** Vote route must resolve slot→trip from DB (existing pattern), never from request body.
- **V5:** Zero rate limiting in codebase. Add basic in-memory rate limiter in Track 0: 30 req/min public, 10 req/min authenticated writes, 3 req/hour LLM calls.

**Medium (incorporated into track specs):**
- V6: Sanitize LLM inputs for packing list, validate output schema, cap text at 100 chars.
- V7: Strip HTML from reflection feedback via Zod transform.
- V8: reflectionData userId key MUST come from session, never request body.
- V9: Limit 1 import per user per shared token.
- V10: Vote voteState read-modify-write needs serializable transaction.
- V11: Cap 3 active pivots per trip, 1 per slot.

**Low (deferred):**
- V12: Consider removing tripId from unauthenticated preview.
- V13: Truncate organizerName to first name only in preview.
- V14: CSRF token validation (acceptable for beta with default same-origin CORS).
- V15: Strip ActivityNode IDs from shared trip response.

### Test Engineer Review

**Test estimate correction:** 130-150 tests, not 100. Plan underscoped by ~50%.

**Infrastructure gaps (add in Track 0):**
- Extract shared `$transaction` mock helper.
- Extract auth+membership mock factory.
- Add Zod schema unit tests for all 5 new schemas.
- Add test that `VALID_SIGNAL_TYPES` whitelist stays in sync with Prisma enum.

**Top 5 highest-risk tests:**
1. "Maybe" vote threshold ambiguity — does 70% mean 70% "yes" or 70% "not no"? **Decision: 70% means yes-only. Maybe counts as neither yes nor no for threshold.**
2. Multi-user reflection JSONB merge — must read-merge-write, not blind overwrite.
3. Concurrent invite accepts exceeding maxUses (covered by V1 fix).
4. Pivot selectedNodeId must be validated against alternativeIds array.
5. Cloned trip must generate new UUIDs for all entities.

**Cross-track integration tests needed:**
- Invite → Vote (new member can immediately vote)
- Import → Reflection (reflection works on cloned trips)
- Vote quorum after invite (confirmed slots stay confirmed)
- Pivot on voted slot (voteState resets after swap)

## Updated Track 0 Scope

Track 0 now includes:
1. Schema migration (`prisma migrate dev`): new fields, enum values, TripMember index
2. voteState → ownerTip data migration + llm-enrichment.ts update
3. Basic rate limiting middleware
4. Test helpers (transaction mock, auth factory)
5. Add `slot_moved` to SignalType enum
6. Add `redirect` callback to NextAuth config

## No Issues Found With:
- Schema changes (packingList, reflectionData as JSONB — correct for single-unit read/write)
- Auth patterns (correctly copies existing IDOR prevention + membership checks)
- New SignalType enum values (all represent real user actions, not system events)
- ownerTip on ItinerarySlot (harmless nullable string for ML future)
- Deterministic scoring for pivot alternatives (no LLM dependency in real-time path)
- Two-phase execution (parallel API + sequential UI wiring)
- CSP headers on shared trip page
- Import data isolation (new IDs, no cross-trip leakage)
