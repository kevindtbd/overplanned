# Post-Deploy Groups + Wiring — Review Notes

**Plan**: `2026-02-24-post-deploy-groups-wiring-design.md`
**Reviewed**: 2026-02-24

## Decisions Made During Review

### 1. Single currency per trip
Expense `currency` field is redundant — currency lives on the Trip, set at
creation. All expenses use the trip's currency. No FX conversion, no rate
APIs. Users mentally convert before logging.

**Action**: Remove `currency` from Expense model. Add `currency` to Trip if
not present. Settle-up outputs in trip currency.

### 2. Stale slot references shown gracefully
When a slot referenced in a chat message gets swapped by a pivot event, show
the original slot card as-is with a subtle "swapped" badge. Messages are
historical context — they were relevant when sent. Don't tombstone or cascade.

**Action**: When hydrating slotRef, check slot status. If `wasSwapped: true`
or `status: skipped`, add `isStale: true` to the response. UI renders a
muted badge.

### 3. Accept packing claim race condition for beta
JSONB last-write-wins on concurrent claims is acceptable for groups of 2-6
people. If it happens, someone re-claims. Revisit with optimistic locking if
this becomes a real issue.

**Action**: No change. Ship as designed.

### 4. Climate averages instead of live forecast for packing
OpenWeatherMap free tier only covers current conditions and 5-day forecast.
Packing lists are generated weeks before travel. Use static climate averages
per seeded city (monthly temp ranges, rain probability).

**Action**: Create a static JSON dataset with monthly climate data for each
seeded city (Tokyo, Barcelona, NYC, Sydney, Kyoto, Osaka, Seoul). Source
from publicly available climate normals. Inject into the LLM prompt as:
"Typical weather for {city} in {month}: {temp_range}, {rain_info}."

Zero API calls. Zero cost. Upgrade to live 5-day forecast later if needed.

### 5. Tag slots with `assignedTo` for split days
Add optional `assignedTo String[]` on ItinerarySlot. Empty array = everyone.
When split, slots get tagged with the subgroup's member IDs. UI filters by
"is my userId in assignedTo, or is assignedTo empty."

**Action**: Add `assignedTo String[]` to ItinerarySlot schema migration
(same migration as Message + Expense). Existing slots have empty array
(everyone).

### 6. Booking hint: try keyword match, fall back to "check website"
Check websiteUrl path for /reserve, /book, /reservation. If match:
"reservable online". If URL exists but no match: "check website". If phone
only: "call ahead". If hours < 4h window: "limited hours". If nothing:
"walk-in".

**Action**: Implement as designed with the "check website" fallback.

---

## Gaps Identified

### G1. Trip.currency field doesn't exist yet
Schema has no `currency` on Trip. Needs to be added in the migration.
Default: "USD". Should be settable at trip creation and editable in settings.

### G2. Message.body — empty messages allowed?
Plan says max 2000 chars but doesn't specify minimum. A message with only a
slotRefId and empty body should be valid (pure slot share, no comment). A
message with no body AND no slotRefId should be rejected.

**Resolution**: `body` can be empty string IF `slotRefId` is provided.
Otherwise `body` must be at least 1 char.

### G3. Expense deletion cascading
If an expense is deleted, the settle-up recalculates automatically (computed
on read). But there's no edit endpoint — if someone logs the wrong amount,
they have to delete and re-create. Is that acceptable for beta?

**Resolution**: Yes. Delete + re-create is fine. Edit adds complexity for
a rare case.

### G4. Climate data source for weather wiring
Need a static JSON file with monthly averages for 7 cities. This is a small
one-time data task but it's a dependency for the weather wiring feature.

**Resolution**: Create `data/climate_averages.json` with monthly data for
the 7 seeded cities. Can be hand-curated from Wikipedia climate tables in
~30 minutes.

### G5. Chat polling frequency
Plan says "poll on focus / pull-to-refresh" but doesn't specify interval.
No polling interval means the chat only updates when you manually refresh or
switch tabs.

**Resolution**: Poll every 30 seconds when chat drawer is open. Stop when
closed. Simple setInterval, no complexity.

### G6. Split days — who initiates the split?
Plan says "Split action forks afternoon slots" but doesn't say who has
permission. Can any member split the day, or only the organizer?

**Resolution**: Any joined member can trigger a split suggestion, but the
actual fork requires organizer approval (role: organizer). Non-organizers
see "Suggest split" which sends a chat message with the suggestion.

---

## Risks

### R1. Chat without real-time could feel broken
Users expect chat to be instant. Polling every 30s means up to 30s delay
on new messages. This is a known tradeoff — shipping without websockets is
the right call for beta, but early feedback may flag it.

**Mitigation**: Optimistic UI — show the message immediately after send
(client-side), confirm with server response. Polling catches others'
messages. Feels responsive for your own messages.

### R2. Expense amounts in cents — user input friction
Users think in dollars/yen, not cents. The API takes `amountCents` but the
UI needs to handle the conversion. Risk of off-by-100x bugs.

**Mitigation**: UI accepts decimal input (e.g., "42.50"), converts to cents
before API call. Validate that amountCents is a positive integer server-side.

---

## Revised Implementation Order

1. **Schema migration** — Message + Expense + Trip.currency + ItinerarySlot.assignedTo
2. **Climate data file** — static JSON for 7 cities (dependency for item 4)
3. **Packing claims** — extend existing endpoint, no migration
4. **Packing + weather** — wire climate averages into LLM prompt
5. **Booking state derivation** — computed field on slot read
6. **Mood capture** — new endpoint + component
7. **Trip chat + slot sharing** — Message CRUD + drawer UI + slot embed
8. **Expense tracker + settle-up** — Expense CRUD + settle algorithm + UI
9. **Split days UI** — frontend component + detector integration

Items 3-6 are parallelizable.
Items 7-8 are parallelizable (both depend on step 1).
Item 9 depends on step 1 (assignedTo field).
