# Trip Detail Page — Post-Creation UX

**Goal:** Close the UX gap between creating a trip (onboarding) and reviewing it (/trip/[id]). Currently there's no feedback that the trip was created, no guidance on what to do with slots, and the FAB is ambiguous.

**Architecture:** All changes scoped to trip detail page and API layer. No new DB tables. One status auto-transition mechanism.

**Tech Stack:** Next.js 14 (App Router), existing design system tokens, existing slot action infrastructure.

**Review Status:** Deepened + architect + security + test-engineer reviewed (2026-02-22). All blockers resolved below.

---

## Decisions Made

| Question | Decision | Rationale |
|---|---|---|
| What does "done" mean? | Auto-transition: `planning` -> `active` on startDate | No friction, no finalize gate. User just reviews slots at their pace. |
| Post-creation feedback? | Inline welcome card, self-destructs on first slot action | Double duty: celebration + teaches confirm/skip mechanic in context |
| FAB clarity? | Labeled pill FAB: `+ Add activity`, collapses on scroll | Removes ambiguity immediately. Text label = zero guesswork. |
| Post-welcome guidance? | Subtle progress nudge on `X/Y confirmed` counter | Micro-animation on confirm. Zero new UI, makes existing stat feel alive. |

---

## Review Fixes Applied

| Finding | Resolution |
|---|---|
| BLOCKER: No behavioral signal on auto-transition | BehavioralSignal is for user actions, not system events. Auto-transition is a system event. Log via `console.info` for observability; do NOT pollute behavioral signal training data. |
| BLOCKER: Dashboard GET can't do auto-transition (TripMember.findMany, not Trip.findUnique) | Removed. Auto-transition only fires on trip detail GET. Dashboard already groups `planning` + `active` as "Active" — visual difference is zero. |
| BLOCKER: FAB height inverted (compact h-14 > expanded h-12) | Fixed. Both use `h-14`. Pill is wider via `px-5`, circle is `w-14`. Same height, no layout shift. |
| GAP: `window.history.replaceState` bypasses Next.js router | Replaced with `sessionStorage` keyed on tripId. No URL param at all — cleaner, no router desync risk. |
| GAP: Scroll listener targets wrong container | Verified: AppShell uses `min-h-screen` with no `overflow-auto`. `window.scrollY` is the correct scroll target. |
| GAP: 8 state atoms accumulating | Extract fetch logic to `useTripDetail` hook. New state (`showWelcome`, `fabCompact`, `confirmPulse`) stays in page since it's UI-only. |
| GAP: WelcomeCard with 0 slots is misleading | Added zero-state copy branch. |
| GAP: confirmPulse timeout not cleaned on unmount | Use `useRef` for timeout ID + cleanup in `useEffect`. |
| SECURITY: Auto-transition must be role-gated | Gated to `membership.role === "organizer"`. Guests can't trigger status writes. |
| SECURITY: `?new=1` injectable by anyone | Replaced with `sessionStorage` — not URL-accessible. |

---

## 1. Auto-Transition: `planning` -> `active`

**Files:**
- Create: `apps/web/lib/trip-status.ts` (utility)
- Edit: `apps/web/app/api/trips/[id]/route.ts` (GET handler only)

No cron job. Check on read — when GET /api/trips/[id] loads a trip, if the requesting user is an organizer AND `status === "planning"` AND `startDate <= now`, update to `"active"`.

**NOT applied to GET /api/trips (dashboard list).** Dashboard already groups `planning` + `active` as "Active" — no visual difference.

```typescript
// lib/trip-status.ts
export function shouldAutoTransition(status: string, startDate: Date): boolean {
  return status === "planning" && startDate <= new Date();
}
```

In the GET handler, after membership check and trip fetch:

```typescript
// Auto-transition: planning -> active when trip start date has arrived
// Only organizer role triggers the write to prevent guest-initiated mutations
if (
  membership.role === "organizer" &&
  shouldAutoTransition(trip.status, new Date(trip.startDate))
) {
  await prisma.trip.update({
    where: { id: trip.id },
    data: { status: "active" },
  });
  trip.status = "active";
  console.info(`[auto-transition] Trip ${trip.id} planning -> active (organizer: ${userId})`);
}
```

**Edge cases:**
- Timezone: `startDate` is stored as UTC. Comparison is UTC-based. Off by hours at most, not days.
- Race condition: Two concurrent organizer reads both try to update. Prisma `update` is idempotent — both write `"active"`, no conflict.
- Manual override: Check only fires on `"planning"` — won't revert `cancelled` or other statuses.
- Guest member visits: No-op — role check prevents the write. Trip still shows as `planning` to the guest, which is fine since the dashboard treats it the same as `active`.

---

## 2. Inline Welcome Card

**Files:**
- Create: `apps/web/components/trip/WelcomeCard.tsx`
- Edit: `apps/web/app/trip/[id]/page.tsx`
- Edit: `apps/web/app/onboarding/page.tsx`

### WelcomeCard Component

Renders above the day view, below the day navigation. Appears only on first visit after trip creation.

**Trigger:** `sessionStorage` keyed on tripId. Onboarding sets `sessionStorage.setItem(`new-trip-${tripId}`, "1")` right before redirect. Trip detail page reads and clears it on mount.

**Dismiss:** Card disappears when: (a) user clicks "Got it", or (b) user takes their first slot action (confirm, skip, or lock).

```tsx
// components/trip/WelcomeCard.tsx

interface WelcomeCardProps {
  city: string;
  totalSlots: number;
  totalDays: number;
  onDismiss: () => void;
}

export function WelcomeCard({ city, totalSlots, totalDays, onDismiss }: WelcomeCardProps) {
  return (
    <div className="rounded-xl border border-accent/20 bg-accent/5 p-4 space-y-2">
      <h3 className="font-sora text-base font-medium text-ink-100">
        Your {city} itinerary is ready
      </h3>
      <p className="font-dm-mono text-xs text-ink-400 leading-relaxed">
        {totalSlots > 0
          ? `${totalSlots} activities across ${totalDays} days, built from your vibes. Tap confirm on the ones you love, skip the rest.`
          : `${totalDays} days planned. Browse activities to start filling your itinerary.`}
      </p>
      <button
        onClick={onDismiss}
        className="font-dm-mono text-xs text-accent hover:text-accent/80 transition-colors"
      >
        Got it
      </button>
    </div>
  );
}
```

**Design notes:**
- Border: `border-accent/20` — subtle terracotta outline
- Background: `bg-accent/5` — barely-there warm tint
- No image, no icon — text-only, lightweight
- Zero-state branch: when `totalSlots === 0`, copy pivots to "Browse activities" guidance

### Integration in trip detail page

```tsx
const [showWelcome, setShowWelcome] = useState(false);

// Check sessionStorage on mount
useEffect(() => {
  const key = `new-trip-${tripId}`;
  if (sessionStorage.getItem(key) === "1") {
    sessionStorage.removeItem(key);
    setShowWelcome(true);
  }
}, [tripId]);

// Dismiss on first slot action — setShowWelcome is a stable setter, no dep needed
const handleSlotAction = useCallback(async (event: SlotActionEvent) => {
  setShowWelcome(false);
  // ... existing optimistic update logic
}, [fetchTrip]);
```

### Onboarding redirect update

In `apps/web/app/onboarding/page.tsx`, inside `handleComplete()`:

```diff
+ sessionStorage.setItem(`new-trip-${trip.id}`, "1");
  router.push(`/trip/${trip.id}`);
```

---

## 3. Labeled FAB Pill

**Files:**
- Edit: `apps/web/app/trip/[id]/page.tsx`

### Design

Replace the bare `+` circle with an extended pill. Collapses to icon-only on scroll down.

Both states are `h-14` (56px). Expanded is wider via `px-5`. No height change = no layout shift.

### Scroll behavior

`window.scrollY` is the correct scroll target (verified: AppShell uses `min-h-screen`, no inner overflow container).

```tsx
const [fabCompact, setFabCompact] = useState(false);

useEffect(() => {
  let lastY = 0;
  function onScroll() {
    const y = window.scrollY;
    setFabCompact(y > 80 && y > lastY);
    lastY = y;
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  return () => window.removeEventListener("scroll", onScroll);
}, []);
```

### FAB markup

```tsx
<Link
  href={discoverUrl}
  className={`
    fixed z-30 bottom-24 right-5 lg:bottom-8 lg:right-8
    flex items-center justify-center gap-2
    h-14 rounded-full
    bg-accent hover:bg-accent/90 text-white shadow-lg
    transition-[width,padding] duration-200
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2
    ${fabCompact ? "w-14" : "px-5"}
  `}
  aria-label="Add activity"
>
  <svg
    width="20" height="20" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
    aria-hidden="true"
    className="flex-shrink-0"
  >
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
  {!fabCompact && (
    <span className="font-sora text-sm font-medium whitespace-nowrap">
      Add activity
    </span>
  )}
</Link>
```

**Transition note:** Using `transition-[width,padding]` instead of `transition-all` to avoid animating properties that aren't GPU-composited.

---

## 4. Progress Nudge on Confirmed Counter

**Files:**
- Edit: `apps/web/app/trip/[id]/page.tsx`

### Behavior

When a slot is confirmed, the `X/Y confirmed` counter briefly pulses terracotta. Uses a ref-based timeout for proper cleanup.

```tsx
const [confirmPulse, setConfirmPulse] = useState(false);
const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

// Cleanup on unmount
useEffect(() => {
  return () => {
    if (pulseTimer.current) clearTimeout(pulseTimer.current);
  };
}, []);

// Inside handleSlotAction, after optimistic update:
if (event.action === "confirm") {
  if (pulseTimer.current) clearTimeout(pulseTimer.current);
  setConfirmPulse(true);
  pulseTimer.current = setTimeout(() => setConfirmPulse(false), 600);
}
```

### Markup

```tsx
<span
  className={`
    transition-colors duration-300
    ${confirmPulse ? "text-accent" : "text-ink-400"}
  `}
>
  {statusSummary.confirmed}/{statusSummary.total} confirmed
</span>
```

No keyframes, no new CSS. Color transition driven by 600ms timeout.

---

## 5. Extract `useTripDetail` Hook

**Files:**
- Create: `apps/web/lib/hooks/useTripDetail.ts`
- Edit: `apps/web/app/trip/[id]/page.tsx`

Extract fetch logic to reduce page component state density:

```typescript
// lib/hooks/useTripDetail.ts
export function useTripDetail(tripId: string) {
  const [trip, setTrip] = useState<ApiTrip | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [errorMessage, setErrorMessage] = useState("Failed to load trip");

  const fetchTrip = useCallback(async () => { ... }, [tripId]);
  useEffect(() => { fetchTrip(); }, [fetchTrip]);

  return { trip, setTrip, myRole, fetchState, errorMessage, fetchTrip };
}
```

Page component goes from 8 state atoms to 3 UI-only atoms (`showWelcome`, `fabCompact`, `confirmPulse`) + the hook.

---

## 6. Edge Cases

| Case | Handling |
|---|---|
| Trip created with 0 slots (unseeded city) | Welcome card shows zero-state copy: "Browse activities to start filling your itinerary." |
| User refreshes trip page after dismissing welcome | `sessionStorage` already cleared. Welcome doesn't reappear. |
| User navigates away and back (same tab) | `sessionStorage` cleared on first visit. Welcome gone. |
| User opens trip in new tab | `sessionStorage` is per-tab. New tab won't have the key. Correct — welcome is a one-time moment. |
| Multiple rapid confirms | Each clears previous timeout and restarts pulse. Latest confirm wins. |
| FAB on mobile with bottom nav | `bottom-24` (96px) clears the mobile nav (`h-16` = 64px + safe area). |
| Scroll listener cleanup | `useEffect` cleanup removes listener. No memory leak. |
| Trip already `active` when visited | Auto-transition check is `planning`-only. No effect on active trips. |
| Guest member visits trip detail | No auto-transition fires (role-gated to organizer). Read-only behavior preserved. |

---

## 7. Cleanup

- Remove bare `+` circle FAB (replaced by labeled pill)
- Remove old FAB SVG dimensions (24x24 -> 20x20)
- No dead code expected — all changes are additive or in-place replacements

---

## Implementation Order

1. **Auto-transition utility** — `lib/trip-status.ts` + wire into GET /api/trips/[id] only (role-gated, console.info logged)
2. **`useTripDetail` hook** — extract fetch logic from page.tsx
3. **WelcomeCard component** — new file, zero-state copy branch
4. **Trip detail integration** — welcome card (sessionStorage), FAB pill (scroll state), progress nudge (ref-based pulse)
5. **Onboarding redirect** — add `sessionStorage.setItem` before `router.push`
6. **Tests** — auto-transition pure unit, WelcomeCard render/dismiss, FAB label/collapse (scrollY override), progress pulse (fake timers), integration flow
