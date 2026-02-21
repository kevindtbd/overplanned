# Trip UX Gaps — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the critical UX gaps that make the trip planning flow non-functional — empty itineraries, missing navigation, no way to add activities, and broken day scrolling.

**Architecture:** Deterministic itinerary generation from seeded ActivityNodes with async LLM narrative enrichment. LLM-only fallback for unseeded cities. New generation module in `lib/generation/` keeps logic testable and swappable.

**Tech Stack:** Next.js 14 API routes, Prisma ORM, Claude Haiku (narrative enrichment), Zod validation.

---

## 1. Navigation Fix

**Files:**
- Edit: `components/nav/DesktopSidebar.tsx`
- Edit: `components/nav/MobileNav.tsx`

### Changes

Uncomment nav items in both components. Final `NAV_ITEMS` array:

```typescript
const NAV_ITEMS: NavItem[] = [
  { label: "Trips",   href: "/dashboard", Icon: TripsIcon },
  { label: "Explore", href: "/discover",  Icon: ExploreIcon },
];
```

- "Home" renamed to "Trips" (the dashboard IS the trip list)
- Profile stays commented out (no page exists)
- Icons already exist in both files — just wire them into the array

---

## 2. Add Activity Button (Trip Detail Page)

**Files:**
- Edit: `app/trip/[id]/page.tsx`

### FAB Component

Floating action button in bottom-right corner of the trip detail page. Terracotta circle, `+` icon. Links to Discover with trip context:

```
/discover?city={trip.city}&tripId={trip.id}
```

Positioning:
- Mobile: `bottom-20` (above MobileNav's `h-16` + safe area)
- Desktop: `bottom-8 right-8`
- Only visible to organizers (check `myRole === "organizer"` from the API response)

### Empty State Upgrade

Replace the passive empty state text with an actionable CTA:

```
No plans yet for Day {n}
[Browse activities →]  ← links to /discover?city=...&tripId=...
```

The existing `DayView` component likely has the empty state. If it's in `DayView`, edit there; if inline in the page, edit the page.

---

## 3. Trip DNA Enhancements

**Files:**
- Edit: `app/onboarding/components/TripDNAStep.tsx`
- Edit: `app/onboarding/components/TemplateStep.tsx`
- Edit: `app/onboarding/page.tsx` (wire new state)

### 3a. Free-form Vibes Textarea

New section at the bottom of TripDNAStep, after food preferences:

- Label: "Anything else?"
- Helper: "Tell us what you're into — hidden gems, local markets, avoiding crowds, whatever"
- `<textarea>` with 300 char max, 3 rows
- Stored in `personaSeed.freeformVibes`
- Optional — does NOT gate the Continue button
- Passed to LLM narrative layer during generation

New prop on TripDNAStep:
```typescript
freeformVibes: string;
onFreeformChange: (value: string) => void;
```

Wire in `app/onboarding/page.tsx` with new `freeformVibes` state, include in `personaSeed` on submit.

### 3b. More Templates

Add 4 new templates to the `TEMPLATES` array in `TemplateStep.tsx`:

| ID | Name | Description | Icon |
|---|---|---|---|
| `night-owl` | Night Owl | Late starts, evening-heavy, nightlife + late-night eats | Moon icon |
| `local-immersion` | Local Immersion | Neighborhoods over landmarks, markets over museums | Map pin icon |
| `first-timer` | First Timer | Must-sees mixed with local picks for newcomers | Star icon |
| `weekend-sprint` | Weekend Sprint | Optimized for 2-3 days, tight routing, no downtime | Zap icon |

Templates encode category weights + pace modifiers (used by generation engine):

```typescript
const TEMPLATE_WEIGHTS: Record<string, TemplateConfig> = {
  "foodie-weekend":   { dining: 0.35, drinks: 0.20, culture: 0.10, outdoors: 0.10, experience: 0.15, nightlife: 0.10, paceModifier: 0 },
  "culture-deep-dive":{ dining: 0.15, drinks: 0.05, culture: 0.40, outdoors: 0.15, experience: 0.15, nightlife: 0.05, shopping: 0.05, paceModifier: 0 },
  "adventure":        { dining: 0.10, drinks: 0.05, culture: 0.05, outdoors: 0.35, active: 0.30, experience: 0.10, wellness: 0.05, paceModifier: 1 },
  "chill":            { dining: 0.20, drinks: 0.15, culture: 0.10, outdoors: 0.15, wellness: 0.20, experience: 0.10, shopping: 0.10, paceModifier: -1 },
  "night-owl":        { dining: 0.20, drinks: 0.25, nightlife: 0.30, culture: 0.05, experience: 0.10, entertainment: 0.10, paceModifier: 0 },
  "local-immersion":  { dining: 0.25, drinks: 0.10, culture: 0.15, outdoors: 0.10, experience: 0.25, shopping: 0.10, wellness: 0.05, paceModifier: 0 },
  "first-timer":      { dining: 0.20, drinks: 0.10, culture: 0.25, outdoors: 0.15, experience: 0.15, entertainment: 0.10, nightlife: 0.05, paceModifier: 0 },
  "weekend-sprint":   { dining: 0.20, drinks: 0.10, culture: 0.20, outdoors: 0.15, experience: 0.25, nightlife: 0.10, paceModifier: 1 },
};
```

`paceModifier` adjusts the base pace: +1 means one extra slot/day, -1 means one fewer.

### 3c. Trip-Length Aware Templates

The generator uses trip duration to adjust behavior:

- **Short trips (1-3 days):** Concentrate highest-scored nodes. No repeat categories on the same day. Weekend Sprint template gets priority routing (minimize transit between slots).
- **Medium trips (4-7 days):** Standard distribution. One "rest" slot every 3rd day for Moderate/Relaxed pace.
- **Long trips (8+ days):** Spread dining across neighborhoods. Insert implicit rest/free slots. Avoid scheduling the same category more than twice in any 3-day window. Chill template on a 14-day trip auto-downgrades to 1-2 planned activities/day with the rest left as open slots.

### 3d. Dynamic Food Chips (Future Enhancement)

Not for this implementation — hardcoded chips stay. But the architecture supports querying city-specific vibe tags from ActivityNodeVibeTag later. The chip list would become:

```typescript
const chips = cityVibeData.length > 0
  ? cityVibeData.map(v => v.name)
  : DEFAULT_FOOD_CHIPS;
```

---

## 4. Itinerary Generation Engine

**Files:**
- Create: `lib/generation/generate-itinerary.ts` (core logic)
- Create: `lib/generation/scoring.ts` (node scoring)
- Create: `lib/generation/slot-placement.ts` (time-of-day heuristics)
- Create: `lib/generation/llm-enrichment.ts` (async LLM narrative)
- Create: `lib/generation/types.ts` (shared types)
- Edit: `app/api/trips/route.ts` (call generator after trip creation)

### 4a. Generation Pipeline Overview

```
POST /api/trips
  → Create Trip + TripMember (existing)
  → generateItinerary(trip, personaSeed)
      → Step 1: Score & select ActivityNodes (deterministic)
      → Step 2: Place into day/time slots (deterministic)
      → Step 3: Create ItinerarySlots via createMany
  → Return trip WITH populated slots
  → Fire async: enrichWithLLM(tripId, slots, personaSeed)
      → Claude Haiku reorders + adds narrative hints
      → Update slots in DB
```

### 4b. Step 1 — Node Scoring (`scoring.ts`)

```typescript
interface ScoredNode {
  node: ActivityNode;
  score: number;
  category: string;
}

function scoreNodes(
  nodes: ActivityNode[],
  templateWeights: Record<string, number>,
  vibeTags: string[],  // from food preferences
): ScoredNode[]
```

Scoring formula per node:
1. **Template category weight** (0-0.40): How well does this node's category match the template?
2. **Vibe tag overlap** (0-0.30): How many of the node's vibe tags match user preferences?
3. **Authority score** (0-0.15): Quality signal from the node's `authorityScore` field
4. **Diversity bonus** (0-0.15): Bonus for categories/neighborhoods not yet selected

Sort descending. Take top N nodes where N = `slotsPerDay * totalDays`.

If a city has fewer nodes than needed, use what's available and leave remaining slots empty (user fills via Discover).

### 4c. Step 2 — Slot Placement (`slot-placement.ts`)

```typescript
function placeSlots(
  scoredNodes: ScoredNode[],
  totalDays: number,
  slotsPerDay: number,
  morningPreference: "early" | "mid" | "late",
): PlacedSlot[]
```

Time-of-day heuristic per slot position in a day:

| Slot # | Packed (5-6) | Moderate (3-4) | Relaxed (2-3) |
|--------|-------------|---------------|--------------|
| 1 | Morning activity | Late morning | Brunch/late start |
| 2 | Lunch (dining) | Lunch (dining) | Afternoon activity |
| 3 | Afternoon activity | Afternoon activity | Dinner (dining) |
| 4 | Late afternoon | Dinner (dining) | — |
| 5 | Dinner (dining) | — | — |
| 6 | Evening/nightlife | — | — |

Category-to-time preferences:
- `dining` → meal slots (breakfast/lunch/dinner times)
- `culture`, `outdoors`, `active` → morning/afternoon
- `drinks`, `nightlife`, `entertainment` → evening
- `wellness` → morning (early bird) or afternoon (late riser)

Morning preference shifts all times:
- `early`: first slot at 07:30
- `mid`: first slot at 09:00
- `late`: first slot at 10:30

### 4d. Step 3 — Slot Creation

After scoring and placement, create all slots in one transaction:

```typescript
await prisma.$transaction([
  prisma.itinerarySlot.createMany({
    data: placedSlots.map((s, i) => ({
      id: uuidv4(),
      tripId,
      activityNodeId: s.nodeId,
      dayNumber: s.dayNumber,
      sortOrder: s.sortOrder,
      slotType: mapCategoryToSlotType(s.category),
      status: "proposed",
      startTime: s.startTime,
      endTime: s.endTime,
      durationMinutes: s.durationMinutes,
      isLocked: false,
    })),
  }),
  // Log generation as a behavioral signal
  prisma.behavioralSignal.create({
    data: {
      id: uuidv4(),
      userId: trip.userId,
      tripId,
      signalType: "soft_positive",
      signalValue: 1.0,
      tripPhase: "pre_trip",
      rawAction: `itinerary_generated:${placedSlots.length}_slots`,
    },
  }),
]);
```

Category → SlotType mapping:
- `dining` → `meal`
- `drinks`, `nightlife` → `flex`
- `culture`, `outdoors`, `active`, `entertainment`, `experience`, `shopping`, `wellness`, `group_activity` → `anchor`

### 4e. LLM Narrative Enrichment (`llm-enrichment.ts`)

Async — fires after the HTTP response is sent. Uses Claude Haiku for cost/speed.

```typescript
async function enrichWithLLM(
  tripId: string,
  slots: GeneratedSlot[],
  personaSeed: PersonaSeed,
  city: string,
): Promise<void>
```

Prompt structure (system):
```
You are a local travel expert for {city}. Given a generated itinerary
and the traveler's preferences, provide:
1. A suggested reordering if any day's sequence is suboptimal
   (e.g., backtracking across the city)
2. A short narrative hint per slot (1 sentence, max 80 chars)
   explaining WHY this activity fits at this time

Traveler preferences: {personaSeed summary + freeformVibes}

Respond as JSON: { reorder: [{slotId, newSortOrder}], hints: [{slotId, hint}] }
```

Model: `claude-haiku-4-5-20251001`
Max tokens: 1000
Temperature: 0.3

On response:
- Apply reordering via batch update
- Write hints to each slot's `voteState` JSON field (repurposed as metadata until we add a dedicated field)
- Log the LLM call: model version, prompt version, latency, token count

If LLM fails → no-op. The deterministic itinerary stands on its own.

### 4f. Unseeded City Fallback

When `ActivityNode.count({ where: { city } }) === 0`:

1. **Log the city request** — write to a new `CityRequest` model (or append to an existing tracking table):
   ```
   { city, country, userId, requestedAt, status: "pending" }
   ```
   This becomes the scraping priority queue.

2. **LLM-only generation** — send the full itinerary generation to Claude Sonnet (not Haiku, since it's doing heavier lifting):
   - System prompt includes city/country, trip dates, personaSeed, template
   - Ask for structured JSON: array of slots with name, category, lat/lng, timeLabel, description
   - Create ItinerarySlots WITHOUT activityNodeId (null) but WITH the LLM-provided names/descriptions stored in `voteState` JSON
   - These slots are flagged by having `activityNodeId: null` — the UI can show a subtle "AI-suggested" badge
   - When we eventually scrape and seed that city, a backfill job matches LLM slots to real nodes

---

## 5. Day Navigation Scroll Fix

**Files:**
- Edit: `components/trip/DayNavigation.tsx`

### Changes

1. **Auto-scroll active tab into view**: When `currentDay` changes, scroll the active tab button into the visible area:

```typescript
// Add ref to each tab button
const tabRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

// After day change, scroll into view
useEffect(() => {
  const activeTab = tabRefs.current.get(currentDay);
  if (activeTab) {
    activeTab.scrollIntoView({
      behavior: "smooth",
      inline: "center",
      block: "nearest",
    });
  }
}, [currentDay]);
```

2. **Allow native horizontal scroll on mobile**: Remove `scrollbar-none` class on small screens. Keep it hidden on desktop. Add `overscroll-behavior-x: contain` to prevent page hijack.

```tsx
className="
  flex-1 overflow-x-auto
  scrollbar-none sm:scrollbar-none
  scroll-smooth
  overscroll-x-contain
"
```

Actually — keep `scrollbar-none` everywhere (matches design system) but ensure touch scroll works natively alongside the swipe-to-change-day gesture. The swipe handler has a 50px threshold, so small scrolls won't trigger day changes.

---

## Implementation Order

1. **Nav fix** — 10 min, zero risk, immediate UX improvement
2. **Day nav scroll fix** — 15 min, isolated component
3. **Trip DNA enhancements** — 30 min, onboarding-only changes
4. **Add Activity FAB** — 20 min, trip detail page only
5. **Generation engine** — 2-3 hours, new module + API integration
   - 5a: Types + scoring logic
   - 5b: Slot placement heuristics
   - 5c: Wire into POST /api/trips
   - 5d: LLM enrichment (async)
   - 5e: Unseeded city fallback + CityRequest tracking

## Data Requirements

- **Seeded cities with nodes:** Mexico City (73), New York (72), Tokyo (20)
- **Minimum viable generation:** Need at least ~15 nodes per city to fill a 3-day Relaxed trip (2-3 slots/day = 6-9 nodes). Tokyo's 20 nodes is tight for longer trips.
- **Vibe tag coverage:** 15 distinct tags across 165 nodes. Sparse but usable for scoring.
- **No new Prisma models needed** except optionally `CityRequest` for the scraping queue.

## Success Criteria

1. Creating a trip for Mexico City/New York/Tokyo populates slots immediately
2. LLM narrative hints appear within 5-10 seconds of landing on trip page
3. Unseeded cities get LLM-generated itineraries (flagged as AI-suggested)
4. User can add activities via FAB → Discover → Shortlist → Add to trip
5. Day tabs scroll to active day on 14-day trips
6. Nav shows Trips + Explore on both mobile and desktop
