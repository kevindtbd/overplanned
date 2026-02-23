# Landing Page Redesign — 2026-02-21

## Overview
Six targeted fixes to the landing page. No full rebuild — surgical edits to existing sections.

---

## 1. Globe (Hero) — Half-Globe with Spread Routes

**Problem:** Globe is too huge (`R = H * 0.58`), Japan cities cluster into a blob (Tokyo/Kyoto/Osaka within ~5 degrees).

**Changes to `GlobeCanvas.tsx`:**
- `R`: `H * 0.58` → `H * 0.42` (shrink ~28%)
- `cy`: `H * 0.52` → `H * 0.68` (push down, bottom ~26% clips below section)
- Keep `cx` at `Math.min(W, 1600) * 0.72`
- Creates "rising earth" feel — globe becomes a stage, not the whole show

**Route changes:**
- Current (too short): Tokyo→Seoul, Seoul→Taipei, Osaka→HCMC
- New (intercontinental arcs): Tokyo→Barcelona, Seoul→Lisbon, Osaka→Istanbul
- Creates dramatic sweeping arcs across the globe

**Card content — from "itinerary" to "places you've been":**
```
Tokyo:     eyebrow "TOKYO · 3 TRIPS"     title "14 days total"    desc "Last: Pontocho standing bar"
Kyoto:     eyebrow "KYOTO · 2 TRIPS"     title "8 days total"     desc "Favorite: Fushimi at dawn"
Seoul:     eyebrow "SEOUL · 1 TRIP"      title "5 days"           desc "Next: return in October"
Barcelona: eyebrow "BARCELONA · 2 TRIPS" title "11 days total"    desc "Most revisited: El Born"
Osaka:     eyebrow "OSAKA · 1 TRIP"      title "4 days"           desc "Dotonbori standing bar"
```

**Route index updates:**
```ts
// Old: [0,2] Tokyo→Seoul, [2,8] Seoul→Taipei, [4,9] Osaka→HCMC
// New: [0,3] Tokyo→Barcelona, [2,5] Seoul→Lisbon, [4,6] Osaka→Istanbul
```

---

## 2. "How It Works" / "The Plan You'd Make" — Three Cards Rework

**Kill:**
- Card 02: "Knows what kind of tired you are" — psychology/creepy
- Card 03: "system watched what you chose" — giving away ML sauce

**New cards (generic utility features, no sauce):**

```
Card 01 (KEEP, minor copy tweak):
  num: "01"
  title: "Finds the counter seat nobody put on a list"
  body: "The 8-seat ramen spot. The izakaya that only takes walk-ins before 18:00. The coffee bar that opened three months ago. Sources that don't show up on the usual apps."
  tag: "Local-First"
  tagClass: "bg-success-bg text-success"

Card 02 (NEW):
  num: "02"
  title: "Builds the plan you'd forget to make"
  body: "Auto-generated packing lists based on your destination and trip length. Budget estimates before you book. Offline access to your full itinerary — no signal required. The logistics layer that actually saves you time."
  tag: "Smart Planning"
  tagClass: "bg-info-bg text-info"

Card 03 (NEW):
  num: "03"
  title: "Adapts when the trip does"
  body: "Flight delayed. Restaurant closed. Rain all afternoon. The plan reshuffles one slot at a time — not a full rebuild. You approve every change before it happens."
  tag: "Real-Time"
  tagClass: "bg-accent-light text-accent-fg"
```

---

## 3. Local Sources — Three-Card Grid, No Sauce

**Kill:** All specific stats (8,100+, 12+, 3 months). No pipeline details.

**New section heading:**
- Eyebrow: "Local Sources, Not Aggregators" (keep)
- Headline: "Intelligence from the ground floor." (keep)
- Body: "Every recommendation traces back to a real source — not a five-star rating from someone who visited once. We pull from the places locals actually use."

**Three cards (feat-card style from Stripe template: icon + title + body + tag):**

```
Card 1:
  title: "Sourced where locals actually look"
  body: "Regional food blogs. Neighborhood review sites. The kind of places that don't have English translations but have decades of trust. We find them so you don't have to."
  tag: "Local-First"
  icon: globe/search SVG

Card 2:
  title: "Always current, never stale"
  body: "Closures caught before you show up. Hours that changed last week, already in your plan. Seasonal menus reflected in real time — not a snapshot from two years ago."
  tag: "Continuous Updates"
  icon: refresh/clock SVG

Card 3:
  title: "No pay-to-rank. No sponsored slots."
  body: "Every recommendation earns its place. No venue pays to appear in your itinerary. No aggregator scores. What you see is what locals actually recommend."
  tag: "Zero Sponsored Content"
  icon: shield/check SVG
```

**Format:** Switch from stat cards to feat-card style with icon boxes (40x40 accent-light rounded box with SVG icon). Same visual pattern as Stripe template `.feat-card`.

---

## 4. Group Trips — Expanded, Positive Only

**Keep:** The existing 2x2 GroupPhones grid (Agreed, Conflict, Votes Pending, Mid-Trip Pivot).

**Rework intro copy:**
- Headline: "Four people. One plan." (keep)
- New body: "Async voting before you leave. Shared packing lists so nobody brings three umbrellas. A budget that splits itself. And when the trip changes, everyone stays in sync."

**Add DotList below GroupPhones with positive features only:**
- "Shared packing list — see who's bringing what, avoid duplicates"
- "Split budget tracker — expenses logged per person, settled at the end"
- "Split days — everyone gets a half-day to do their own thing, then regroup"
- "Group chat built into the trip — no separate WhatsApp thread"

**Removed (per user direction):**
- No "compromise detection" / "notices who keeps giving in"
- No conflict-focused language
- Only surface positive, collaborative features

---

## 5. Trip Map — End Node + Legend Removal

**Changes to `TripMapCanvas.tsx`:**

1. **Remove `current: true` from Harajuku** — "You Are Here" makes no sense on a marketing page
2. **Proper end node on Roppongi:**
   - Larger radius: 7 → 11px
   - Double-ring: outer stroke ring + inner filled dot
   - Keeps accent color (terracotta)
3. **Remove bottom legend entirely** — this is a playful viz, not an informational map

**Changes to `page.tsx`:**
- Delete the map legend div (lines ~771-786)

**Stop data update:**
```ts
// Remove current from Harajuku
{ x: 0.48, y: 0.35, label: "Harajuku" },  // was current: true

// Roppongi end node gets visual emphasis in draw code, not data change
```

---

## 6. Component Reuse

- **DotList** — already exists, reuse in Group section
- **feat-card pattern** — create from Stripe template for Sources section (icon + title + body + tag)
- **Source chips** — reuse existing `Local`, `Tabelog` chip styles if needed

---

## Files to Modify

| File | Changes |
|------|---------|
| `apps/web/app/page.tsx` | Sections 2-5: card content, sources grid, group copy+DotList, map legend removal |
| `apps/web/components/landing/GlobeCanvas.tsx` | Section 1: R, cy, routes, card content |
| `apps/web/components/landing/TripMapCanvas.tsx` | Section 5: remove current, enhance end node, remove legend |

---

## Dispatch Plan — Parallel Agents

Three independent workstreams, no cross-dependencies:

**Agent 1: Globe (GlobeCanvas.tsx)**
- Shrink R, push cy down
- Update routes to intercontinental
- Update card content to "places you've been"

**Agent 2: Page Content (page.tsx)**
- How It Works cards rework
- Local Sources section rework
- Group Trips expansion
- Map legend removal

**Agent 3: Trip Map (TripMapCanvas.tsx)**
- Remove current from Harajuku
- Enhance end node on Roppongi
- Remove legend DOM from page.tsx (coordinate with Agent 2)

Note: Agent 2 handles the legend DOM removal in page.tsx since it's already editing that file.
