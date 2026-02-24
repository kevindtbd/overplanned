# Post-Deploy Sprint: Groups + Wiring

**Date**: 2026-02-24
**Status**: Design (reviewed by architect, security, test-engineer)
**Scope**: 7 deliverables — 3 group features, 4 wiring items
**Canonical schema**: `/prisma/schema.prisma` (1038 lines, has TripLeg)
  — NOT `/packages/db/prisma/schema.prisma` (outdated)

## Context

Landing page promises features that aren't built yet. This sprint closes the
gaps that matter for beta users, specifically group trip functionality and
low-effort wiring that connects existing systems.

**Out of scope**: iOS/Android, source attribution display, offline/PWA,
share-as-image, busy window signals, budget estimates (no cost data),
websockets, custom expense splits, chat reactions/threads, expense editing
(delete + recreate is fine for beta).

---

## 1. Trip Chat + Slot Sharing

### What
Single flat message stream per trip. Members can send plain text messages and
optionally embed a slot reference — a compact inline activity card rendered
inside the message. The "share to chat" action lives on every SlotCard,
matching the iOS share-sheet mental model (you're looking at a slot, you share
it into the trip conversation).

### Schema

```prisma
model Message {
  id        String         @id @default(uuid())
  tripId    String
  trip      Trip           @relation(fields: [tripId], references: [id], onDelete: Cascade)
  userId    String
  user      User           @relation(fields: [userId], references: [id])
  body      String         // plain text, max 2000 chars, HTML-stripped before storage
  slotRefId String?        // optional embedded slot reference
  slotRef   ItinerarySlot? @relation(fields: [slotRefId], references: [id], onDelete: SetNull)
  createdAt DateTime       @default(now())

  @@index([tripId, createdAt])
}
```

Add `messages Message[]` relation to Trip, User, and ItinerarySlot models.

**Key decisions:**
- `onDelete: SetNull` on slotRef — if a slot is deleted, message degrades to
  text-only. No orphaned foreign keys.
- Body is sanitized server-side: strip HTML tags + control chars before storage
  (same `sanitize()` pattern from the packing route).
- Body can be empty string IF slotRefId is provided (pure slot share, no
  comment). Body must be >= 1 char if no slotRefId.
- Stale slot references shown gracefully: when hydrating slotRef, if
  `wasSwapped: true` or `status: skipped`, add `isStale: true` to response.
  Messages are historical context.

### API

| Method | Route | Body / Params | Notes |
|--------|-------|---------------|-------|
| GET | `/api/trips/[id]/messages` | `?cursor=<id>&limit=50` | Keyset pagination on `(createdAt DESC, id DESC)`. Returns messages with user `{ name, avatarUrl }` + hydrated slot ref `{ name, category, dayNumber, startTime, isStale }`. Limit clamped to 1-50. |
| POST | `/api/trips/[id]/messages` | `{ body: string, slotRefId?: string }` | Validates membership (joined). Sanitizes body (HTML strip, max 2000). Validates slotRefId belongs to same trip: `WHERE id = slotRefId AND tripId = tripId`. Rate limited: `rateLimitPresets.authenticated` keyed by `chat:${userId}`. |
| DELETE | `/api/trips/[id]/messages/[messageId]` | — | Author-only. Hard delete. |

No websockets for beta. Poll every 30s when chat drawer is open. Optimistic UI
for sent messages (show immediately, confirm with server response).

### UI: `components/trip/TripChat.tsx`

- Drawer/panel on trip page, not a separate route
- Message bubbles with avatar + name + relative timestamp
- Slot reference renders as compact card inline: activity name, category pill,
  day/time. Muted with "swapped" badge if `isStale: true`. Tappable to scroll
  to that slot in the itinerary.
- Text input at bottom with send button
- "Share to chat" action on every SlotCard — opens chat drawer with that slot
  pre-attached, user adds optional comment and sends

### Behavioral Signals

- `share_action` signal logged when a slot is shared into chat
  (already exists in SignalType enum)

---

## 2. Expense Tracker + Settle-Up

### What
Members log expenses as they happen. System tracks who paid, splits equally
among participants, and computes minimum transfers to settle all debts at the
end. No custom split amounts — equal only for beta.

### Schema

```prisma
model Expense {
  id          String   @id @default(uuid())
  tripId      String
  trip        Trip     @relation(fields: [tripId], references: [id], onDelete: Cascade)
  paidById    String
  paidBy      User     @relation(fields: [paidById], references: [id])
  description String   // "Dinner at Ichiran", max 200 chars
  amountCents Int      // stored in smallest currency unit (cents for USD, yen for JPY)
  splitWith   String[] // userIds included in split; empty = all joined members
  slotId      String?  // optional link to an itinerary slot
  createdAt   DateTime @default(now())

  @@index([tripId, createdAt])
}
```

No `SplitMode` enum — hardcode equal split for beta. No per-expense `currency`
— currency lives on the Trip.

Add `expenses Expense[]` relation to Trip model.
Add `paidExpenses Expense[]` relation to User model.
Add `currency String @default("USD")` to Trip model. Lock currency once the
first expense is created (reject currency change with existing expenses).

**Zero-decimal currency handling**: `amountCents` means "smallest currency
unit." Use a lookup for decimal places: USD=2, EUR=2, JPY=0, KRW=0, GBP=2.
UI converts user input accordingly (e.g., for JPY, 4200 input = 4200 stored;
for USD, 42.50 input = 4250 stored).

### API

| Method | Route | Body / Params | Notes |
|--------|-------|---------------|-------|
| GET | `/api/trips/[id]/expenses` | — | All expenses for trip, ordered by createdAt desc. Includes paidBy `{ name, avatarUrl }`. Membership required. |
| POST | `/api/trips/[id]/expenses` | `{ description, amountCents, splitWith?, slotId? }` | `paidById` is ALWAYS set from session — never accepted from request body. `description` min 1 / max 200 chars, trimmed. `amountCents` must be positive int, max 10,000,000. `splitWith`: every userId must be a joined TripMember — validate, deduplicate, UUID format, cap at member count. `slotId` must belong to same trip if provided. |
| DELETE | `/api/trips/[id]/expenses/[expenseId]` | — | Triple-condition: `WHERE id = expenseId AND tripId = tripId AND paidById = userId`. Log deletion to AuditLog with expense data in `before` field. |
| GET | `/api/trips/[id]/expenses/settle` | — | Membership required. Computed: returns `{ settlements: [{ fromId, fromName, toId, toName, amountCents }], currency }` |

### Settle-Up Algorithm

Lives in `lib/settle.ts` as a pure function (isolated unit tests).

1. Net each member's balance (total paid minus total owed)
2. Separate into creditors (positive balance) and debtors (negative balance)
3. Greedily pair largest debtor with largest creditor
4. Repeat until all balances are zero
5. Remainder from odd splits assigned to the last payer (1 cent goes somewhere)

Computed on read, not stored. O(n log n) where n = members. Invariant:
`sum(all settlements) === 0`.

Note: greedy is not truly minimum-transfers for 6+ people but is correct for
balances. Acceptable for beta group sizes.

### UI: `components/trip/ExpenseTracker.tsx`

- Tab or collapsible section on trip page
- Expense list: description, formatted amount, who paid, member count in split
- "Add expense" form: description input, amount input (decimal for USD/EUR,
  integer for JPY/KRW), optional slot link (dropdown of trip slots)
- Settle-up section at bottom: debt cards showing "You owe Sarah $23" with
  member avatars. Rendered from the settle endpoint.

---

## 3. Packing Claims

### What
Extend existing shared packing list so members can claim items. One shared
list, items start unclaimed. Tap to claim ("I'll bring this"). Others see
who claimed what. Can only unclaim your own items.

### Schema Change

No migration needed. Extend the existing JSONB shape on `Trip.packingList`:

```ts
// Current: { id, text, category, checked }
// New:     { id, text, category, checked, claimedBy?: string | null }
// claimedBy = userId or null/undefined (unclaimed)
```

Backward compatible: existing items without `claimedBy` treated as unclaimed.

### API Change

Extend existing `PATCH /api/trips/[id]/packing` to accept:

```ts
{ itemId: string, claimedBy: string | null }
// claimedBy = current userId to claim, null to unclaim
```

Validation (exact permission matrix):
- `claimedBy === session.user.id` → claim (allowed)
- `claimedBy === null` AND item's current `claimedBy === session.user.id` →
  unclaim own (allowed)
- `claimedBy === null` AND item's current `claimedBy !== session.user.id` →
  unclaim someone else's item (REJECT 403)
- `claimedBy === someOtherUserId` → claim as someone else (REJECT 403)

Last-write-wins race condition accepted for beta (groups of 2-6).

Log `BehavioralSignal` with `signalType: share_action` and
`rawAction: packing_claim:<itemId>` or `packing_unclaim:<itemId>`

### UI Change: modify `PackingList.tsx`

- Each item shows a claim pill next to the checkbox
- Unclaimed: dashed border pill, "claim" text
- Claimed by you: your avatar + "you" label, tappable to unclaim
- Claimed by someone else: their avatar + first name, not tappable
- Claim state is orthogonal to checked state — you can claim an unchecked item

---

## 4. Packing + Weather Wiring

### What
Inject climate context into packing list generation so Haiku produces
weather-appropriate items.

### Change

Use static climate averages (zero API calls, zero cost), not live weather.
Create `data/climate_averages.json` with monthly data for the 7 seeded cities
(Tokyo, Kyoto, Osaka, Seoul, Barcelona, NYC, Sydney). Source: Wikipedia
climate tables.

In `apps/web/app/api/trips/[id]/packing/route.ts`, before the LLM call:

1. Load climate data for the trip's primary leg city
2. Look up the month from `trip.startDate`
3. If city found, append to prompt:
   ```
   Typical weather for {city} in {month}: {temp_low}-{temp_high}C,
   {rain_days} rainy days typical. {conditions}.
   ```
4. If city not in dataset, skip — generate without weather context (current
   behavior). If spanning two months, use the start month.

Fallback: if climate data file can't be read, silently skip. Don't block on
weather.

### Size
~30 lines changed in packing route + climate data file.

---

## 5. Booking State Derivation

### What
Populate booking hints on slots at read time, derived from ActivityNode fields.

### Logic

Extract to pure helper function `deriveBookingHint(node: ActivityNode)` in
`lib/booking-hint.ts` (isolated unit tests).

Priority order:
1. `websiteUrl` path contains /reserve, /book, /reservation → `"reservable online"`
2. `websiteUrl` exists but no booking keywords → `"check website"`
3. `phoneNumber` exists, no `websiteUrl` → `"call ahead"`
4. Both `phoneNumber` AND `websiteUrl` (no booking keywords) → `"check website"`
5. `hours` JSON has any window < 4 hours → `"limited hours"`
6. No ActivityNode linked → `"walk-in"`
7. None of the above → `"walk-in"`

URL keyword matching: check the URL **path** only, not domain. Matching
"reserved-dining.com" would be a false positive.

Hours parsing: null, empty object, or malformed → skip, don't error.

Computed field on the API response, not a stored column.

### Size
~40 lines: helper function + wiring in the slot serializer.

---

## 6. Mid-Trip Mood Capture

### What
Lightweight mood check-in during active trips. Three-state tap (high / medium
/ low energy). Fires a behavioral signal and updates the member's energy
profile.

### API

| Method | Route | Body | Notes |
|--------|-------|------|-------|
| POST | `/api/trips/[id]/mood` | `{ mood: "high" \| "medium" \| "low" }` | Validates trip.status === "active" (else 400), user is joined member. No server-side rate limit — frequency managed client-side. |

Handler:
1. Create `BehavioralSignal` with `signalType: pace_signal`,
   `signalValue: { high: 1.0, medium: 0.5, low: 0.0 }[mood]`,
   `tripPhase: "active"`
2. Merge into `TripMember.energyProfile` JSON:
   `{ ...existing, lastMood: mood, updatedAt: now }` — don't clobber existing
   fields
3. Return 200

### UI: `components/trip/MoodPulse.tsx`

- Renders only when `trip.status === "active"`
- Three tappable states: high / medium / low — simple icons or labels
- Shows once per ~12 hours (check `energyProfile.updatedAt` client-side)
- After tap: brief confirmation, then hides until next window
- No text input, no explanation. One tap and done.

### Size
Small — one endpoint, one component.

---

## 7. Split Days UI

### What
Surface the existing split detector's suggestions in the itinerary UI.

### Schema Addition

Add to ItinerarySlot:
```prisma
assignedTo String[] @default([])  // empty = everyone; non-empty = subgroup member IDs
```

Both `null` and `[]` treated as "everyone" in application code.

### Backend

The split detector at `services/api/subflows/split_detector.py` already does
bimodal clustering and returns subgroup assignments + reunion point hint.

New endpoint needed for the fork action:

| Method | Route | Body | Notes |
|--------|-------|------|-------|
| POST | `/api/trips/[id]/split-day` | `{ dayNumber, subgroups: { memberIds: string[], slotIds: string[] }[] }` | Organizer-only (role === "organizer"). Writes `assignedTo` on target slots. |

Non-organizers see "Suggest split" which posts a chat message with the
suggestion — no slot modification.

### Frontend Integration

1. On group trip day views with 4+ unsettled flex slots, call the split
   detector endpoint
2. If detector returns a split suggestion, render `SplitDayCard`
3. Card shows: two subgroups with member avatars, "Split the afternoon?" prompt
4. Organizer: "Split up" action writes `assignedTo` via the fork endpoint
5. Non-organizer: "Suggest split" sends a chat message
6. "Stay together" action: dismisses card, logs BehavioralSignal, won't
   re-suggest for this day (dismissal stored in trip logisticsState)

### UI: `components/trip/SplitDayCard.tsx`

- Inline card in the day timeline
- Subgroup bubbles with member avatars
- Two action buttons: "Split up" / "Suggest split" (accent, role-dependent) +
  "Stay together" (ghost)
- Dismissible — once dismissed, stores preference in trip state

### Size
Small-Medium — frontend component + one API endpoint + detector integration.

---

## Implementation Order

1. **Schema migration** — Message + Expense + Trip.currency + ItinerarySlot.assignedTo
2. **Climate data file** — static JSON for 7 cities (dependency for item 4)
3. **Packing claims** — extend existing endpoint, no migration
4. **Packing + weather** — wire climate averages into LLM prompt
5. **Booking state derivation** — pure helper + slot serializer wiring
6. **Mood capture** — new endpoint + component
7. **Trip chat + slot sharing** — Message CRUD + drawer UI + slot embed
8. **Expense tracker + settle-up** — Expense CRUD + settle algorithm + UI
9. **Split days UI** — fork endpoint + frontend component + detector integration

Items 3-6 are parallelizable (independent).
Items 7-8 are parallelizable (both depend on step 1).
Item 9 depends on steps 1 and 7 (chat for non-organizer suggest).

---

## Testing Strategy

### Cross-cutting (all new endpoints)
- 4-test auth gate: no session → 401, no member → 404, invited-not-joined →
  404, joined member → proceeds
- Malformed JSON body → 400
- Zod schema validation as separate describe blocks
- Transaction failure handling where applicable

### Per-feature

- **Chat**: empty body + slotRef rule, stale slot hydration (isStale flag),
  deleted slot ref (slotRefId null after SetNull cascade), cursor boundaries
  (empty, invalid, deleted mid-page), cross-trip slotRefId rejection, body at
  exactly 2000/2001 chars, rate limiting
- **Expenses**: `lib/settle.ts` isolated unit tests (15-20 cases: 2/3/4/5
  members, rounding remainder, zero expenses, single-member, all-by-one-person,
  delete-then-recalculate, sum-to-zero invariant). Route tests: paidById
  never from body, splitWith non-member rejection, amountCents 0 and max,
  triple-condition delete, settle-up membership gate, currency from Trip
- **Packing claims**: null packingList with claim payload, already-claimed
  override (last-write-wins verified), impersonation attempt → 403,
  claim/check orthogonality, backward compat (old items without claimedBy)
- **Weather wiring**: city not in dataset → no weather in prompt, prompt
  format snapshot, climate JSON malformed → graceful fallback
- **Booking states**: `lib/booking-hint.ts` unit tests — phone only, URL with
  booking keyword, URL without keyword ("check website"), both phone+URL, hours
  null/empty/malformed, null ActivityNode, keyword in domain vs path
- **Mood**: non-active trip → 400, invalid mood value → 400, signal value
  mapping correctness, energyProfile merge (don't clobber), rapid duplicates
  accepted
- **Split days**: organizer can fork (assignedTo written), non-organizer
  gets "suggest" (chat message, no slot change), dismiss persistence, detector
  returns no suggestion → card not rendered
