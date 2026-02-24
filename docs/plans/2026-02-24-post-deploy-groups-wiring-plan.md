# Post-Deploy Sprint: Implementation Plan

**Design**: `2026-02-24-post-deploy-groups-wiring-design.md`
**Review notes**: `post-deploy-groups-wiring-review-notes.md`
**Canonical schema**: `/prisma/schema.prisma`

---

## Phase 1: Schema Migration + Data File

**Depends on**: nothing
**Blocks**: Phases 5, 6, 7

### 1.1 Prisma Schema Changes

File: `/prisma/schema.prisma`

Add to Trip model:
```prisma
currency    String    @default("USD")
messages    Message[]
expenses    Expense[]
```

Add to User model:
```prisma
messages      Message[]
paidExpenses  Expense[]
```

Add to ItinerarySlot model:
```prisma
assignedTo  String[]  @default([])
messages    Message[]
```

Add new models (Message, Expense) exactly as specified in design doc.

Run: `npx prisma migrate dev --name add-chat-expenses-split`
Verify migration SQL. Confirm it targets the root schema.

### 1.2 Climate Averages Data File

File: `data/climate_averages.json`

Create static JSON with monthly data for 7 cities. Structure:
```json
{
  "tokyo": {
    "1":  { "tempLowC": 2, "tempHighC": 10, "rainDays": 5, "conditions": "dry, cold" },
    "2":  { "tempLowC": 2, "tempHighC": 11, "rainDays": 6, "conditions": "dry, cold" },
    ...
  },
  "kyoto": { ... },
  "osaka": { ... },
  "seoul": { ... },
  "barcelona": { ... },
  "new_york": { ... },
  "sydney": { ... }
}
```

Source from Wikipedia climate tables. Key by lowercase city slug (matching
the city seeding pipeline's slugification).

### 1.3 Zod Validation Schemas

File: `apps/web/lib/validations/messages.ts`
```ts
messageCreateSchema = z.object({
  body: z.string().max(2000),
  slotRefId: z.string().uuid().optional(),
}).refine(
  d => d.slotRefId || (d.body && d.body.trim().length > 0),
  { message: "Body required when no slot reference" }
)

messageCursorSchema = z.object({
  cursor: z.string().uuid().optional(),
  limit: z.coerce.number().int().min(1).max(50).default(50),
})
```

File: `apps/web/lib/validations/expenses.ts`
```ts
expenseCreateSchema = z.object({
  description: z.string().min(1).max(200).trim(),
  amountCents: z.number().int().positive().max(10_000_000),
  splitWith: z.array(z.string().uuid()).max(20).optional(),
  slotId: z.string().uuid().optional(),
})
```

File: `apps/web/lib/validations/mood.ts`
```ts
moodSchema = z.object({
  mood: z.enum(["high", "medium", "low"]),
})
```

Extend `apps/web/lib/validations/packing.ts`:
```ts
packingClaimSchema = z.object({
  itemId: z.string().uuid(),
  claimedBy: z.string().uuid().nullable(),
})
```

### Checkpoint
- [ ] Migration runs clean
- [ ] `npx prisma generate` succeeds
- [ ] Climate data file has all 7 cities x 12 months
- [ ] All Zod schemas exported
- [ ] Existing tests still pass (`vitest run --exclude '.claude/**'`)

---

## Phase 2: Packing Claims (small, no migration dependency)

**Depends on**: Phase 1.3 (Zod schema only)
**Parallel with**: Phases 3, 4

### 2.1 Extend PATCH handler

File: `apps/web/app/api/trips/[id]/packing/route.ts`

In the PATCH handler, detect whether the body matches `packingCheckSchema` or
`packingClaimSchema`. Route to the appropriate logic:

**Claim logic:**
1. Parse body with `packingClaimSchema`
2. Load trip.packingList
3. Find item by itemId (404 if not found)
4. Validate permission matrix:
   - `claimedBy !== null && claimedBy !== userId` → 403
   - `claimedBy === null && item.claimedBy !== userId` → 403
5. Update item.claimedBy
6. Write packingList back + log BehavioralSignal in transaction

### 2.2 Update PackingList UI

File: `apps/web/components/trip/PackingList.tsx`

Add claim pill to each item row:
- Unclaimed: dashed border, "claim" text, onClick → PATCH with claimedBy
- Claimed by you: avatar + "you", onClick → PATCH with claimedBy: null
- Claimed by other: avatar + first name, not interactive

Need trip members list for avatar/name resolution. Pass via props or fetch
from trip context.

### 2.3 Tests

File: `apps/web/__tests__/api/packing.test.ts` (extend existing)

New describe block: `"PATCH /api/trips/[id]/packing — claims"`
- Claim own item → 200, claimedBy set
- Unclaim own item → 200, claimedBy null
- Claim as different userId → 403
- Unclaim someone else's item → 403
- Item not found → 404
- packingList null → 404
- Claim doesn't change checked state
- Check doesn't change claimedBy
- Old items without claimedBy field → treated as unclaimed
- Zod validation: invalid UUID, missing itemId

### Checkpoint
- [ ] All new packing tests pass
- [ ] Existing packing tests still pass
- [ ] Manual: claim/unclaim in UI works

---

## Phase 3: Packing + Weather Wiring (small)

**Depends on**: Phase 1.2 (climate data file)
**Parallel with**: Phases 2, 4

### 3.1 Climate lookup utility

File: `apps/web/lib/climate.ts`

```ts
export function getClimateContext(city: string, month: number): string | null
```

Pure function. Load and cache the JSON. Lookup by city slug + month number.
Return formatted string or null if city not found.

### 3.2 Wire into packing route

File: `apps/web/app/api/trips/[id]/packing/route.ts`

Before the `anthropic.messages.create()` call, after building `destination`
and `startDate`:

```ts
const month = trip.startDate.getMonth() + 1;
const climate = getClimateContext(city.toLowerCase(), month);
// Append to LLM user message if climate is non-null
```

### 3.3 Tests

File: `apps/web/__tests__/lib/climate.test.ts` (new)
- Known city + month → formatted string
- Unknown city → null
- Month boundaries (1, 12)

File: `apps/web/__tests__/api/packing.test.ts` (extend)
- Mock climate module, verify LLM prompt includes weather line
- Unknown city → prompt has no weather line (existing behavior)

### Checkpoint
- [ ] Climate utility tests pass
- [ ] Packing POST with known city includes weather in prompt
- [ ] Packing POST with unknown city still works (no weather)

---

## Phase 4: Booking State Derivation + Mood Capture (small x2)

**Depends on**: Phase 1 (mood needs migration for schema, booking needs nothing)
**Parallel with**: Phases 2, 3

### 4.1 Booking hint helper

File: `apps/web/lib/booking-hint.ts`

```ts
export function deriveBookingHint(node: {
  phoneNumber?: string | null;
  websiteUrl?: string | null;
  hours?: unknown;
} | null): string
```

Pure function implementing the priority chain from the design doc.

### 4.2 Wire into slot serializer

Find where slots are serialized in trip detail / slot list API responses.
Add `bookingHint: deriveBookingHint(slot.activityNode)` to the response shape.

### 4.3 Booking hint tests

File: `apps/web/__tests__/lib/booking-hint.test.ts` (new)
- Phone only → "call ahead"
- URL with /reserve → "reservable online"
- URL with /book → "reservable online"
- URL with /menu (no keyword) → "check website"
- Both phone + non-booking URL → "check website"
- Keyword in domain not path → "check website" (not false positive)
- Hours < 4h window → "limited hours"
- Hours null / empty / malformed → skip gracefully
- No ActivityNode (null) → "walk-in"
- No phone, no URL, no hours → "walk-in"

### 4.4 Mood endpoint

File: `apps/web/app/api/trips/[id]/mood/route.ts` (new)

Standard pattern: session check → membership check → trip.status check →
Zod validate → transaction (create BehavioralSignal + update energyProfile) →
return 200.

### 4.5 Mood UI

File: `apps/web/components/trip/MoodPulse.tsx` (new)

Render conditionally when trip.status === "active". Three tappable states.
Check energyProfile.updatedAt client-side for 12h throttle.

### 4.6 Mood tests

File: `apps/web/__tests__/api/mood.test.ts` (new)
- 4-test auth gate (no session, no member, invited, joined)
- Trip not active → 400
- Valid mood "high" → 200, signal created with value 1.0
- Valid mood "medium" → 200, signal created with value 0.5
- Valid mood "low" → 200, signal created with value 0.0
- Invalid mood "exhausted" → 400
- Missing mood field → 400
- energyProfile merge (don't clobber existing fields)
- Two rapid POSTs both succeed (no server rate limit)

### Checkpoint
- [ ] All booking hint tests pass
- [ ] Booking hints appear in slot API responses
- [ ] All mood tests pass
- [ ] MoodPulse renders only on active trips

---

## Phase 5: Trip Chat + Slot Sharing (medium)

**Depends on**: Phase 1 (Message table)
**Parallel with**: Phase 6

### 5.1 Message route handlers

File: `apps/web/app/api/trips/[id]/messages/route.ts` (new)

**GET handler:**
1. Session + membership check
2. Parse cursor/limit with messageCursorSchema
3. Query messages with keyset pagination:
   `WHERE tripId = :tripId AND (createdAt, id) < (:cursor_created, :cursor_id)`
   `ORDER BY createdAt DESC, id DESC LIMIT :limit`
4. Hydrate user (name, avatarUrl) and slotRef (name, category, dayNumber,
   startTime, isStale) via include/join
5. isStale = slot.wasSwapped || slot.status === "skipped"
6. If slot was deleted (SetNull), slotRef is null — return null in response

**POST handler:**
1. Session + membership check
2. Rate limit: `rateLimitPresets.authenticated` keyed by `chat:${userId}`
3. Validate with messageCreateSchema
4. Sanitize body (HTML strip + control chars)
5. If slotRefId provided: verify `WHERE id = slotRefId AND tripId = tripId`
6. Transaction: create Message + create BehavioralSignal (if slotRefId, log
   share_action)
7. Return created message with hydrated relations

**DELETE handler:**

File: `apps/web/app/api/trips/[id]/messages/[messageId]/route.ts` (new)

1. Session + membership check
2. Find message: `WHERE id = messageId AND tripId = tripId AND userId = userId`
3. If not found → 404
4. Hard delete
5. Return 200

### 5.2 Chat UI

File: `apps/web/components/trip/TripChat.tsx` (new)

- Chat drawer component with message list, input, send button
- Poll every 30s when open (useEffect with setInterval)
- Optimistic send: insert message into local state immediately
- Slot embed card: compact inline widget, muted if isStale
- "Share to chat" action wired from SlotCard (pass callback via context or
  props)

### 5.3 SlotCard share action

File: modify `apps/web/components/trip/SlotCard.tsx` (or equivalent)

Add share icon/button. On click: open chat drawer with slotRefId pre-filled.

### 5.4 Tests

File: `apps/web/__tests__/api/messages.test.ts` (new)

**Auth gate (4 tests)**
**GET tests:**
- Empty messages → empty array
- Returns messages with user info
- Slot ref hydrated with isStale flag
- Deleted slot ref → slotRef null in response
- Cursor pagination: first page, next page, invalid cursor
- Limit clamped (0 → 400, 10000 → clamped to 50)

**POST tests:**
- Valid message → 201
- Empty body with slotRefId → 201
- Empty body without slotRefId → 400
- Whitespace-only body without slotRefId → 400
- Body at 2000 chars → 201
- Body at 2001 chars → 400
- SlotRefId from different trip → 400
- Non-existent slotRefId → 400
- BehavioralSignal created for slot share
- Rate limit exceeded → 429

**DELETE tests:**
- Author deletes own → 200
- Non-author deletes → 404
- Non-existent message → 404

**Zod validation block:**
- messageCreateSchema: body types, slotRefId format
- messageCursorSchema: limit bounds, cursor format

### Checkpoint
- [ ] All 20+ message tests pass
- [ ] Chat drawer opens, sends, receives
- [ ] Slot share from SlotCard works
- [ ] Stale slots render with badge

---

## Phase 6: Expense Tracker + Settle-Up (medium)

**Depends on**: Phase 1 (Expense table)
**Parallel with**: Phase 5

### 6.1 Settle-up utility

File: `apps/web/lib/settle.ts` (new)

```ts
interface Settlement { fromId: string; toId: string; amountCents: number }

export function computeSettlements(
  expenses: { paidById: string; amountCents: number; splitWith: string[] }[],
  allMemberIds: string[]
): Settlement[]
```

Pure function. Handles:
- Empty expenses → empty settlements
- Single member → empty settlements
- Rounding remainder → assign to last payer
- Invariant: sum of all settlement amounts from debtors = sum to creditors

### 6.2 Expense route handlers

File: `apps/web/app/api/trips/[id]/expenses/route.ts` (new)

**GET handler**: Membership check. Query all expenses for trip, include
paidBy user info. Return ordered by createdAt desc.

**POST handler**:
1. Session + membership check
2. Validate with expenseCreateSchema
3. Set paidById = session.user.id (NEVER from body)
4. If splitWith non-empty: validate every userId is a joined TripMember.
   Deduplicate. Reject non-members → 400.
5. If slotId provided: verify belongs to same trip
6. Create expense
7. Return created expense

File: `apps/web/app/api/trips/[id]/expenses/[expenseId]/route.ts` (new)

**DELETE handler**:
1. Session + membership check
2. Find: `WHERE id = expenseId AND tripId = tripId AND paidById = userId`
3. If not found → 404
4. Log to AuditLog (action: "expense_delete", before: expense data)
5. Hard delete
6. Return 200

File: `apps/web/app/api/trips/[id]/expenses/settle/route.ts` (new)

**GET handler**:
1. Session + membership check
2. Fetch all expenses for trip
3. Fetch all joined member IDs
4. Call `computeSettlements(expenses, memberIds)`
5. Hydrate names from member list
6. Return `{ settlements, currency: trip.currency }`

### 6.3 Currency lock

In trip update endpoint (PATCH trip), add check: if trip has any expenses,
reject currency change → 400 "Cannot change currency with existing expenses."

### 6.4 Expense UI

File: `apps/web/components/trip/ExpenseTracker.tsx` (new)

- Expense list with formatted amounts (use currency decimal lookup for display)
- Add expense form: description, amount input, optional slot dropdown
- Settle-up section: debt cards with avatars

### 6.5 Tests

File: `apps/web/__tests__/lib/settle.test.ts` (new, ~20 tests)
- 2 members: A pays $100, split equally → A owed $50
- 3 members: odd split (1000 / 3 = 333 + remainder)
- 4 members: verify fewer transfers than naive pairwise
- 5 members: complex scenario
- All expenses by same person → n-1 settlements
- Zero expenses → empty array
- Single member → empty array
- Sum-to-zero invariant on every test
- Idempotency: same input → same output
- Delete expense then recompute → correct result
- 1 cent expense split 3 ways

File: `apps/web/__tests__/api/expenses.test.ts` (new)
**Auth gate (4 tests per endpoint = 12)**
**POST tests:**
- Valid expense → 201
- paidById in body ignored → paidById = session user
- splitWith with non-member → 400
- splitWith with duplicate IDs → deduplicated
- amountCents 0 → 400
- amountCents negative → 400
- amountCents > 10M → 400
- description empty → 400
- description > 200 chars → 400
- slotId from different trip → 400

**DELETE tests:**
- Author deletes own → 200, AuditLog created
- Non-author → 404
- ExpenseId from different trip → 404

**Settle GET tests:**
- Membership required (non-member → 404)
- Empty expenses → empty settlements
- Basic 2-person settle
- Currency from trip

**Zod validation block**

### Checkpoint
- [ ] All settle unit tests pass (20+)
- [ ] All expense route tests pass (25+)
- [ ] Currency lock tested
- [ ] UI renders expenses and settle-up

---

## Phase 7: Split Days UI (small-medium)

**Depends on**: Phase 1 (assignedTo field), Phase 5 (chat for non-organizer suggest)

### 7.1 Split-day fork endpoint

File: `apps/web/app/api/trips/[id]/split-day/route.ts` (new)

**POST handler:**
1. Session + membership check
2. Verify role === "organizer" (else 403)
3. Validate body: `{ dayNumber, subgroups }`
4. Write `assignedTo` on target slots
5. Log BehavioralSignal
6. Return 200

### 7.2 SplitDayCard component

File: `apps/web/components/trip/SplitDayCard.tsx` (new)

- Call split detector when viewing a group day with 4+ unsettled flex slots
- Render subgroup bubbles if detector returns suggestion
- Organizer: "Split up" button → POST to fork endpoint
- Non-organizer: "Suggest split" → POST chat message with slot refs
- "Stay together" → dismiss, log signal, store in trip.logisticsState

### 7.3 Itinerary slot filtering

Modify day view rendering to filter slots by `assignedTo`:
- `assignedTo` empty or includes current userId → show
- `assignedTo` non-empty and doesn't include userId → hide

### 7.4 Tests

File: `apps/web/__tests__/api/split-day.test.ts` (new)
- Auth gate (4 tests)
- Organizer can fork → assignedTo written on slots
- Non-organizer fork attempt → 403
- Invalid dayNumber → 400

File: `apps/web/__tests__/components/SplitDayCard.test.tsx` (new)
- Detector returns suggestion → card rendered
- Detector returns null → card not rendered
- Organizer sees "Split up" button
- Non-organizer sees "Suggest split" button
- "Stay together" dismisses card

### Checkpoint
- [ ] Fork endpoint tests pass
- [ ] Component tests pass
- [ ] Slot filtering works (assigned slots show for correct members)
- [ ] Non-organizer suggest creates chat message

---

## Phase 8: Integration + Polish

**Depends on**: all previous phases

### 8.1 Full integration test

Run all tests:
```bash
cd apps/web && npx vitest run --exclude '.claude/**'
cd services/api && python -m pytest
```

### 8.2 Manual QA checklist

- [ ] Create group trip with 3 members
- [ ] Generate packing list → weather context in items
- [ ] Claim/unclaim packing items
- [ ] Send chat messages with and without slot references
- [ ] Share a slot to chat from SlotCard
- [ ] Slot gets swapped by pivot → chat message shows stale badge
- [ ] Add expenses, verify settle-up math
- [ ] Delete expense, verify settle-up recalculates
- [ ] Mood capture on active trip
- [ ] Booking hints appear on slot cards
- [ ] Split day card appears for divergent group preferences (if detector fires)

### 8.3 Compound learnings

After the sprint, capture learnings to memory files:
- `server/` — new API patterns (chat polling, settle-up compute-on-read)
- `ui/` — chat drawer pattern, share-to-chat flow
- `schema-contracts.md` — new models, currency lock pattern
- `product/decisions.md` — equal-only splits, no websockets, claim last-write-wins

---

## Parallelization Map

```
Phase 1 (migration + data + zod)
  |
  ├── Phase 2 (packing claims)     ─┐
  ├── Phase 3 (weather wiring)      │  All parallel
  ├── Phase 4 (booking + mood)     ─┘
  |
  ├── Phase 5 (trip chat)          ─┐  Parallel with each other
  ├── Phase 6 (expense tracker)    ─┘
  |
  └── Phase 7 (split days)           Needs Phase 1 + 5
        |
        Phase 8 (integration)
```

Phases 2-4 can run as parallel worktree agents.
Phases 5-6 can run as parallel worktree agents after Phase 1.
Phase 7 is sequential (needs chat for suggest flow).
