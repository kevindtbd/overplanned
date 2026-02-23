# Dashboard Empty State & Trip Collection UX

**Goal:** Replace the dead-end empty dashboard with an action-forward launchpad that guides users to their first trip, then gracefully transitions to a trip collection as they create more.

**Architecture:** New `QuickStartGrid` component for zero-state, conditional header CTA for 1+ trips, query-param shortcut into onboarding. No new API routes or DB changes.

**Tech Stack:** Next.js 14 (App Router), existing design system tokens, existing `getCityPhoto()` utility.

**Review Status:** Deepened + architect + security + test-engineer reviewed (2026-02-22). All 4 blockers resolved below.

---

## 1. Empty State -- QuickStartGrid

**Files:**
- Create: `components/dashboard/QuickStartGrid.tsx`
- Edit: `app/dashboard/page.tsx`

### QuickStartGrid Component

Renders when `trips.length === 0`. Replaces the current `EmptyState` usage.

City data derives from `LAUNCH_CITIES` (imported from `@/app/onboarding/components/DestinationStep`), filtered to the 3 seeded cities with ActivityNode data:

```tsx
import { LAUNCH_CITIES } from "@/app/onboarding/components/DestinationStep";

const FEATURED_CITY_NAMES = ["Tokyo", "New York", "Mexico City"];
const FEATURED_CITIES = LAUNCH_CITIES.filter(c => FEATURED_CITY_NAMES.includes(c.city));
```

> **Why these 3?** Tokyo (20 nodes), New York (72), Mexico City (73) are the only cities with seeded ActivityNode data. Adding a city without data produces an empty itinerary. Update this list when new cities are seeded.

Layout:

```tsx
<section aria-labelledby="quickstart-heading">
  <h2 id="quickstart-heading" className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
    Where to?
  </h2>
  <div className="mt-3 grid grid-cols-2 gap-3">
    {FEATURED_CITIES.map(city => (
      <CityCard key={city.city} {...city} />
    ))}
    <SomewhereElseCard />
  </div>
</section>
```

### CityCard Anatomy

- Wrapper: `<Link>` with `group relative block h-[140px] overflow-hidden rounded-xl`
- Background: `getCityPhoto(city, 600, 75)` via `next/image` with `fill`, `sizes="(max-width: 640px) 50vw, 300px"`, `object-cover`
- Warm overlay: `<div className="photo-overlay-warm absolute inset-0" aria-hidden="true" />`
- Bottom-left text stack:
  - Country: `font-dm-mono text-[10px] text-white/60 uppercase tracking-wider`
  - City: `font-sora text-lg font-medium text-white leading-tight`
- Hover: `group-hover:scale-[1.03]` on the image (matches TripHeroCard)
- Accessibility: `aria-label={`Plan a trip to ${city}, ${country}`}`
- Focus: `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2` on the link

### CityCard Link Target

Simplified query params -- only `city` and `step` needed since onboarding looks up full LaunchCity by city name:

```
/onboarding?city=Tokyo&step=dates
```

URL construction uses `encodeURIComponent` for city names with spaces (Mexico City):

```tsx
const href = `/onboarding?city=${encodeURIComponent(city)}&step=dates`;
```

### "Somewhere Else" Card

Same dimensions as CityCard. Dashed border pattern:

```tsx
<Link
  href="/onboarding"
  aria-label="Plan a trip to a different city"
  className="flex h-[140px] flex-col items-center justify-center gap-2
             rounded-xl border-2 border-dashed border-accent/40 bg-raised
             transition-colors hover:border-accent/60
             focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
>
  <PlusIcon className="h-6 w-6 text-accent" />
  <span className="font-sora text-sm text-ink-300">Somewhere else</span>
</Link>
```

`PlusIcon` is an inline SVG defined in QuickStartGrid.tsx (project pattern: no icon libraries, single-file components).

### Dashboard Integration

```tsx
{fetchState === "success" && trips.length === 0 && (
  <QuickStartGrid />
)}
```

Remove: `EmptyState` import, `CompassIcon` function (dead code after swap).

---

## 2. Dashboard with Trips (1+ Trips)

**Files:**
- Edit: `app/dashboard/page.tsx`

### Header with "+ New trip" Button

When `trips.length > 0`, add a button to the header row. Use inline Tailwind instead of `btn-ghost` (which is 10px uppercase mono -- wrong for this context):

```tsx
<header className="flex items-baseline justify-between">
  <div>
    <h1 className="font-sora text-2xl font-medium text-ink-100 sm:text-3xl">
      Your trips
    </h1>
    <p className="mt-1 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
      Plan, track, and relive
    </p>
  </div>
  {fetchState === "success" && trips.length > 0 && (
    <Link
      href="/onboarding"
      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-sora text-sm
                 text-accent transition-colors hover:bg-accent/10"
    >
      <PlusIcon className="h-4 w-4" />
      New trip
    </Link>
  )}
</header>
```

`PlusIcon` defined inline in dashboard page (same SVG as QuickStartGrid, duplicated per single-file-component rule).

### Section Label Conditional Logic

Labels only appear when needed to distinguish categories:

```tsx
const showLabels = activeTrips.length > 0 && pastTrips.length > 0;
```

| Active trips | Past trips | Show labels? |
|---|---|---|
| Yes | No | No labels -- just the cards |
| No | Yes | No labels -- just the rows |
| Yes | Yes | "Active" + "Past trips" labels |

Replace current always-on `<h2>` elements (lines 117-119 and 134-136) with conditional rendering:

```tsx
{showLabels && (
  <h2 id="active-trips-heading" className="sec-label mb-4">Active</h2>
)}
```

---

## 3. Onboarding Query Param Handling

**Files:**
- Edit: `app/onboarding/page.tsx`

### Suspense Boundary (REQUIRED for Next.js 14 App Router)

`useSearchParams()` requires a `<Suspense>` boundary. Restructure following the existing auth/signin pattern:

```tsx
// app/onboarding/page.tsx
import { Suspense } from "react";

function OnboardingContent() {
  // All current OnboardingPage logic moves here
  const searchParams = useSearchParams();
  // ... rest of component
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-base" />}>
      <OnboardingContent />
    </Suspense>
  );
}
```

### Reading Quick-Start Params

Inside `OnboardingContent`, read params and validate against `LAUNCH_CITIES`:

```typescript
import { LAUNCH_CITIES } from "./components/DestinationStep";
import { useSearchParams } from "next/navigation";

const searchParams = useSearchParams();
const prefilledCity = searchParams.get("city");
const startStep = searchParams.get("step");
```

### Validation

```typescript
// SECURITY: Only use values from the matched LAUNCH_CITIES entry.
// Never use raw query param values directly.
const matchedDest = LAUNCH_CITIES.find(
  d => d.city.toLowerCase() === prefilledCity?.toLowerCase()
);
```

### State Pre-fill (in initializer or effect)

Use a lazy initializer ref to run once on mount (idempotent under React 18 strict mode double-mount):

```typescript
const didPrefill = useRef(false);

useEffect(() => {
  if (didPrefill.current) return;
  if (matchedDest && startStep === "dates") {
    didPrefill.current = true;
    setDestination(matchedDest);  // Single LaunchCity object, not separate fields
    setStep("dates");             // String key, not numeric index
  }
}, [matchedDest, startStep]);
```

After reading params, replace the URL to prevent stale query params in browser history:

```typescript
const router = useRouter();
// Inside the effect, after pre-fill:
router.replace("/onboarding", { scroll: false });
```

### Back Button Behavior

When user arrives via quick-start and presses back from DatesStep:
- First back: goes to DestinationStep (user can change pre-filled city)
- Second back: goes to ForkScreen (acceptable -- minimal code change, reasonable UX)

No special handling needed -- existing `goBack()` logic handles this correctly.

---

## 4. Loading & Error States

**No changes to loading state.** Current two `CardSkeleton` blocks are fine.

**No changes to error state.** Current `ErrorState` component handles retry correctly.

---

## 5. Edge Cases

| Case | Handling |
|---|---|
| Trip with no name | Already handled: `displayName = trip.name \|\| trip.destination` |
| Past dates but "planning" status | Show in Active section -- status is source of truth |
| Double-click on quick-start card | `<Link>` handles dedup natively |
| Tampered query params (`?city=<script>`) | Validated against LAUNCH_CITIES allowlist, silent fallback to step 0. React auto-escapes all rendered strings. |
| Missing/partial params (`?city=Tokyo` no step) | Silent fallback to step 0 |
| Case-insensitive matching (`?city=tokyo`) | `.toLowerCase()` comparison handles this |
| URL-encoded spaces (`Mexico%20City`, `Mexico+City`) | `searchParams.get()` auto-decodes both |
| Stale dashboard after creating trip | `useEffect` re-fetches on mount |
| Stale query params in history | `router.replace("/onboarding")` clears them after reading |
| Abandoned onboarding | No draft state -- nothing persisted until submit |
| Seeded cities list changes | `FEATURED_CITY_NAMES` const in QuickStartGrid -- update when new cities seeded |
| `getCityPhoto` unknown city | Returns fallback Unsplash photo (handled in `lib/city-photos.ts`) |

---

## 6. Cleanup

- Remove `CompassIcon` function from dashboard page (dead code)
- Remove `EmptyState` and `CompassIcon` imports from dashboard page
- Keep `EmptyState` component itself (used elsewhere)
- Update existing test `"shows empty state when no trips exist"` -- now asserts for `"Where to?"` instead of `"Your adventures start here"`

---

## Implementation Order

1. **QuickStartGrid component** -- new file, CityCard + SomewhereElseCard, imports LAUNCH_CITIES
2. **Dashboard integration** -- swap EmptyState for QuickStartGrid, add header button, add section label conditional, remove dead code
3. **Onboarding query params** -- Suspense wrapper, useSearchParams, validate against LAUNCH_CITIES, pre-fill + setStep("dates"), router.replace
4. **Update existing tests** -- fix broken empty state assertion, add new test cases
