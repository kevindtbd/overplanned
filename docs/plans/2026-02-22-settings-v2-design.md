# Settings V2 Design

## Goal

Expand the settings page with four new capabilities: travel interests (hybrid vibe tags + free-form), display preferences (units, date/time, dark mode), Stripe billing portal, and two missing notification fields.

## Decision Log

- **Travel Profile stub deleted** — contradicts the "invisible intelligence" philosophy. ML persona data should never be shown to users directly.
- **Hybrid input for travel interests** — curated vibe tags for quick selection + optional free-form text for nuance. Free-form feeds ML async, not on the save path.
- **Stripe-only billing** — no Apple IAP abstractions until a native iOS app exists.
- **Display prefs are table stakes** — .ics export and slot times already ship; rendering in wrong units/formats breaks non-US users.
- **checkin_reminder is opt-in only** — product ML doc flags it as potentially invasive.
- **Dark mode** — design system already has full token support (`data-theme="dark"`). Just needs a toggle and persistence.

### Agent Review Amendments

- **Keep localStorage for theme** — `layout.tsx` already has inline script + `suppressHydrationWarning`. No cookies, no layout changes. Client toggle syncs `localStorage` + DB.
- **Split API routes** — `/api/settings/display` (5 format fields) + `/api/settings/preferences` (existing 4 + vibePreferences + travelStyleNote). Different consumers, different fetch patterns.
- **Disclosure groups for vibe chips** — 23 chips on mobile is too many rows. Collapse into 5 groups, Discovery Style + Food & Drink open by default. Active count badge in collapsed header.
- **Stripe fetch-on-click** — don't expose `stripeCustomerId` in session. Button always renders for non-free tiers. Route does DB lookup. 404 if no Stripe customer.
- **Wire vibePreferences to ranking engine** — add `vibePreferences?: string[]` to `PersonaSeed` type, merge from `UserPreference` at trip creation. Also write `PersonaDimension` records + `BehavioralSignal` on vibe save.
- **Textarea saves on blur** — not debounced. Vibe tag chips keep 500ms debounce. Matches account name pattern.
- **Date format pills use dm-mono text-xs** — long strings barely fit at 375px with default styling.
- **Billing button loading state** — disabled + spinner + "Opening..." during Stripe round-trip. Inline error state.
- **Horizontal anchor nav** — 8 sections on mobile needs skip-to-section links at top.
- **preTripDaysBefore: hide but preserve** — when tripReminders off, selector hidden, value stays in DB. Snap transition (no animation).
- **Install `stripe` npm package** — not currently in dependencies. Create `lib/stripe.ts` singleton. Add `STRIPE_SECRET_KEY` to `lib/env.ts`.
- **Configure Stripe Customer Portal in Dashboard** — required before API calls work. Enable invoice history, payment methods, cancellation.
- **Document LLM prompt injection contract** — add note to `lib/validations/settings.ts` that `travelStyleNote` must use delimiter isolation when fed to any LLM.

---

## 1. Travel Interests (Hybrid)

### What it is

A new section on the settings page (between Preferences and Notifications). Curated vibe tag chips in collapsible groups, plus an optional free-form textarea.

### Vibe tag selection

Sourced from the locked 42-tag vibe vocabulary (`docs/overplanned-vibe-vocabulary.md`), filtered to user-level preferences (excluding activity-level tags like cash-only, queue-worthy, book-ahead, no-frills):

**Pace & Energy**
- `high-energy` — High energy
- `slow-burn` — Slow burn
- `immersive` — Immersive

**Discovery Style** (open by default)
- `hidden-gem` — Hidden gems
- `iconic-worth-it` — Iconic & worth it
- `locals-only` — Locals only
- `offbeat` — Offbeat & unexpected

**Food & Drink** (open by default)
- `destination-meal` — Destination meals
- `street-food` — Street food
- `local-institution` — Local institutions
- `drinks-forward` — Drinks-forward spots

**Activity Type**
- `nature-immersive` — Nature immersive
- `urban-exploration` — Urban exploration
- `deep-history` — Deep history
- `contemporary-culture` — Contemporary culture
- `hands-on` — Hands-on experiences
- `scenic` — Scenic views

**Social & Time**
- `late-night` — Late night
- `early-morning` — Early morning
- `solo-friendly` — Solo-friendly
- `group-friendly` — Group-friendly
- `social-scene` — Social scene
- `low-interaction` — Low interaction

Total: 23 tags across 5 groups.

### Mobile UI: Disclosure groups

Each group is a collapsible section with `aria-expanded`. Discovery Style and Food & Drink open by default (highest signal value). Collapsed groups show active count badge (e.g., "2 selected"). Same chip pattern as existing Preferences (tap to toggle, terracotta fill, CheckIcon).

```tsx
<button onClick={() => setOpen(o => !o)} aria-expanded={open} className="flex items-center justify-between w-full py-2">
  <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400">{heading}</span>
  <span className="flex items-center gap-2">
    {activeCount > 0 && <span className="font-dm-mono text-[10px] text-accent">{activeCount}</span>}
    <ChevronSvg className={`transition-transform ${open ? "rotate-180" : ""}`} />
  </span>
</button>
{open && <div className="flex flex-wrap gap-2 pt-1">{chips}</div>}
```

### Free-form text

Below the chips: a textarea with placeholder text.

Label (dm-mono, uppercase): "Anything else about how you travel?"
Placeholder: "I always hunt for the best coffee spot in every city..."
Max length: 500 characters. Character counter: right-aligned, `font-dm-mono text-[10px] tabular-nums`, hidden until > 400 chars, red (`var(--error)`) when <= 20 remaining.

**Save trigger:** Blur only (not debounced). Matches account name input pattern. Counter updates on every keystroke via controlled state.

### Schema changes

Add to `UserPreference` model:
```prisma
vibePreferences   String[]  @default([])
travelStyleNote   String?
```

### API changes

Extend existing `GET /api/settings/preferences` and `PATCH /api/settings/preferences`:
- GET returns `vibePreferences` and `travelStyleNote` alongside existing fields
- PATCH accepts both new fields
- `vibePreferences` validated against the 23-tag allowlist (same pattern as dietary/mobility)
- `travelStyleNote` validated as `.string().max(500).optional()`
- Server-side deduplication on `vibePreferences` array

### Zod schema update

Add to `updatePreferencesSchema` in `lib/validations/settings.ts`:
```typescript
export const VIBE_PREFERENCE_OPTIONS = [
  "high-energy", "slow-burn", "immersive",
  "hidden-gem", "iconic-worth-it", "locals-only", "offbeat",
  "destination-meal", "street-food", "local-institution", "drinks-forward",
  "nature-immersive", "urban-exploration", "deep-history", "contemporary-culture", "hands-on", "scenic",
  "late-night", "early-morning", "solo-friendly", "group-friendly", "social-scene", "low-interaction",
] as const;
```

Add to schema object:
```typescript
vibePreferences: z.array(z.enum(VIBE_PREFERENCE_OPTIONS)).max(23).optional(),
travelStyleNote: z.string().max(500).optional(),
```

Add LLM safety note:
```typescript
// SECURITY: travelStyleNote MUST use delimiter isolation (<user_note> tags) when
// fed to any LLM for persona extraction. Never pass raw text as instructions.
// See docs/plans/2026-02-22-settings-v2-design.md for the full contract.
```

### ML integration

**On save path (synchronous, non-blocking):**
1. **PersonaDimension upsert** — for each vibe tag in `vibePreferences`, upsert a `PersonaDimension` record: `dimension: "vibe_preference"`, `value: tag`, `confidence: 1.0`, `source: "settings"`. Tags removed = delete the corresponding `PersonaDimension` record.
2. **BehavioralSignal logging** — fire-and-forget after upsert. Log `signalType: "vibe_select"` for added tags, `signalType: "vibe_deselect"` for removed tags. `rawAction: "settings:vibe_preference_update"`.

**Deferred (future async job):**
- `travelStyleNote` LLM extraction to PersonaDimension. The API route does NOT call any LLM. Raw text stored only.

### Ranking engine integration

Add `vibePreferences?: string[]` to `PersonaSeed` type in `lib/generation/types.ts`. When a trip is created, pull `UserPreference.vibePreferences` and merge into `PersonaSeed`. The scoring function in `lib/generation/scoring.ts` uses these as vibe tag overlap input alongside per-trip signals.

### Component

New `TravelInterests.tsx` component in `components/settings/`. Fetches from `/api/settings/preferences` on mount (same endpoint as PreferencesSection). Disclosure groups, chip toggles (debounce 500ms), textarea (blur save).

---

## 2. Display Preferences

### What it is

A new section on the settings page with its own component and API endpoint. Five display format controls.

### Fields

| Field | Options | Default | UI |
|---|---|---|---|
| Distance | mi, km | mi | Two-option radio pills |
| Temperature | F, C | F | Two-option radio pills |
| Date format | MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD | MM/DD/YYYY | Three-option radio pills (dm-mono text-xs) |
| Time format | 12h, 24h | 12h | Two-option radio pills |
| Theme | Light, Dark, System | system | Three-option radio pills |

Date format pills use `font-dm-mono text-xs` (not `font-sora text-sm`) because the long date strings barely fit at 375px with default styling.

### Schema changes

Add to `UserPreference` model:
```prisma
distanceUnit      String  @default("mi")
temperatureUnit   String  @default("F")
dateFormat        String  @default("MM/DD/YYYY")
timeFormat        String  @default("12h")
theme             String  @default("system")
```

### Zod additions

```typescript
export const DISTANCE_UNITS = ["mi", "km"] as const;
export const TEMPERATURE_UNITS = ["F", "C"] as const;
export const DATE_FORMATS = ["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"] as const;
export const TIME_FORMATS = ["12h", "24h"] as const;
export const THEME_OPTIONS = ["light", "dark", "system"] as const;
```

New `updateDisplaySchema`:
```typescript
export const updateDisplaySchema = z
  .object({
    distanceUnit: z.enum(DISTANCE_UNITS).optional(),
    temperatureUnit: z.enum(TEMPERATURE_UNITS).optional(),
    dateFormat: z.enum(DATE_FORMATS).optional(),
    timeFormat: z.enum(TIME_FORMATS).optional(),
    theme: z.enum(THEME_OPTIONS).optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");
```

### API route

New `GET /api/settings/display` + `PATCH /api/settings/display`:
- Same auth + upsert pattern as other settings routes
- Reads/writes the 5 display fields on `UserPreference`
- Separate from `/api/settings/preferences` because different consumers and fetch patterns

### Theme application

**Do NOT change `layout.tsx`.** The existing inline script + `suppressHydrationWarning` already handles flash prevention correctly.

Client-side on theme change:
```typescript
function applyTheme(value: "light" | "dark" | "system") {
  if (value === "system") {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    localStorage.removeItem("theme");
  } else {
    document.documentElement.setAttribute("data-theme", value);
    document.documentElement.style.colorScheme = value;
    localStorage.setItem("theme", value);
  }
  // PATCH to DB
  save({ theme: value });
}
```

The existing `THEME_SCRIPT` in layout.tsx reads `localStorage` on page load. If empty, falls back to `prefers-color-scheme` media query. No cookie needed.

### Consumer wiring

**DayView time format** — `formatTimeMarker` in `components/trip/DayView.tsx` changes `hour12: true` to `hour12: timeFormat !== "24h"`. `timeFormat` passed as prop from trip detail page, which fetches display preferences.

**.ics export** — RFC 5545 mandates `YYYYMMDDTHHMMSS` format for DTSTART/DTEND regardless of user preferences. User's dateFormat/timeFormat do NOT affect the .ics protocol lines. If human-readable strings are added to DESCRIPTION later, they would use the display format — but currently DESCRIPTION is just the category name.

**distanceUnit / temperatureUnit** — no current consumers. Values stored for future use when distance/temperature data appears in slot cards.

### Component

New `DisplayPreferences.tsx` component in `components/settings/`. Fetches from `/api/settings/display` on mount. Auto-save on change (immediate, no debounce — discrete radio selections). Revert on failure.

---

## 3. Stripe Billing Portal

### What it is

A "Manage billing" link in the SubscriptionBadge section that opens Stripe's hosted Customer Portal.

### Prerequisites

1. **Install `stripe` npm package** — not currently in dependencies
2. **Create `lib/stripe.ts`** — singleton pattern matching `lib/prisma.ts`:
   ```typescript
   import Stripe from "stripe";
   const globalForStripe = globalThis as unknown as { stripe?: Stripe };
   export const stripe = globalForStripe.stripe ?? new Stripe(process.env.STRIPE_SECRET_KEY!, {
     apiVersion: "2024-06-20",
     typescript: true,
   });
   if (process.env.NODE_ENV !== "production") globalForStripe.stripe = stripe;
   ```
3. **Add `STRIPE_SECRET_KEY` to `lib/env.ts`** — validate with `.startsWith("sk_")`
4. **Configure Customer Portal in Stripe Dashboard** (test mode) — enable invoice history, payment methods, subscription cancellation

### API route

`POST /api/settings/billing-portal`

```typescript
// Auth required
// Rate limit: per-userId, same as other settings routes
// DB lookup for stripeCustomerId (NOT from session)
const dbUser = await prisma.user.findUnique({
  where: { id: userId },
  select: { stripeCustomerId: true },
});
if (!dbUser?.stripeCustomerId) {
  return NextResponse.json({ error: "No billing account found" }, { status: 404 });
}

try {
  const session = await stripe.billingPortal.sessions.create({
    customer: dbUser.stripeCustomerId,
    return_url: `${process.env.NEXTAUTH_URL}/settings`,
  });
  // Validate Stripe response before forwarding
  if (!session.url || !session.url.startsWith("https://billing.stripe.com/")) {
    return NextResponse.json({ error: "Failed to create billing session" }, { status: 502 });
  }
  return NextResponse.json({ url: session.url });
} catch (err) {
  if (err instanceof Stripe.errors.StripeInvalidRequestError) {
    console.error("[billing-portal] Stripe invalid request:", err.message, err.code);
    return NextResponse.json({ error: "Billing portal unavailable" }, { status: 422 });
  }
  if (err instanceof Stripe.errors.StripeConnectionError) {
    return NextResponse.json({ error: "Could not reach billing service" }, { status: 503 });
  }
  console.error("[billing-portal] Unexpected error:", err);
  return NextResponse.json({ error: "Internal error" }, { status: 500 });
}
```

### UI changes to SubscriptionBadge

No props change needed (fetch-on-click, no session data required).

Button always renders for `pro` and `lifetime` tiers. Loading state with spinner + "Opening..." text. Inline error display. `window.location.href` for redirect (external domain).

```tsx
const showBillingLink = ["pro", "lifetime"].includes(tier);

{showBillingLink && (
  <button
    onClick={handleManageBilling}
    disabled={billingLoading}
    className="font-dm-mono text-xs text-ink-400 hover:text-accent transition-colors disabled:opacity-50"
  >
    {billingLoading ? (
      <span className="flex items-center gap-1.5">
        <SpinnerSvg className="animate-spin h-3 w-3" />
        Opening...
      </span>
    ) : "Manage billing"}
  </button>
)}
{billingError && <span className="font-sora text-xs text-[var(--error)]">{billingError}</span>}
```

### Known limitations

- `stripeCustomerId` is never written by current code — billing button will never render for beta users. This is correct behavior; the button becomes visible when checkout/webhook infrastructure is wired.
- Stripe customer not deleted on account delete — ghost records in Stripe. Low urgency for beta, add to backlog.

---

## 4. Notification Gaps

### What it is

Two new fields in the existing Notifications section.

### checkinReminder

- **Toggle label**: "Check-in prompts during active trips"
- **Default**: `false` (opt-in only — product doc flags as potentially invasive)
- **Position**: Last item in "Trip activity" group
- **Behavior**: Same as other toggles — immediate PATCH on toggle, revert on failure

### preTripDaysBefore

- **Selector label**: "Remind me before trips"
- **Options**: 1 day / 3 days / 1 week (values: 1, 3, 7)
- **Default**: 3
- **Position**: Rendered below "Reminders before upcoming trips" toggle, only visible when `tripReminders` is `true`. Snap transition (no animation) — matches existing toggle pattern.
- **Behavior**: Immediate PATCH on change, revert on failure
- **When tripReminders off**: Selector hidden, value preserved in DB. Re-enabling shows previous selection.

### Schema migration

Add to `NotificationPreference`:
```prisma
checkinReminder    Boolean @default(false)
preTripDaysBefore  Int     @default(3)
```

### Zod update

Add to `updateNotificationsSchema`:
```typescript
checkinReminder: z.boolean().optional(),
preTripDaysBefore: z.number().int().refine(v => [1, 3, 7].includes(v), "Must be 1, 3, or 7").optional(),
```

### Component changes

- Add `checkinReminder` to `NotifField` type and `DEFAULTS`
- Add `{ field: "checkinReminder", label: "Check-in prompts during active trips" }` to Trip activity group
- Add `preTripDaysBefore` as a separate non-toggle control: three radio pills (1 day / 3 days / 1 week) below tripReminders, conditionally rendered

---

## Settings Page Layout

### Section order

1. Anchor nav (horizontal scroll, skip links)
2. Account (existing)
3. Subscription + Stripe portal (enhanced)
4. Display Preferences (new component)
5. My Preferences (existing, enhanced with vibePreferences + travelStyleNote)
6. Travel Interests (new component)
7. Notifications + new fields (enhanced)
8. Privacy & Data (existing)
9. About (existing)

### Horizontal anchor nav

At the top of the settings page, below the header. Horizontal scrollable `<nav>` with anchor links to each section. `font-dm-mono text-[10px] uppercase`. Provides jump-to-section on mobile where 8 sections creates significant scroll depth.

```tsx
<nav className="flex gap-3 overflow-x-auto scrollbar-none -mx-4 px-4 pb-2 mb-2">
  {SECTION_ANCHORS.map(({ id, label }) => (
    <a key={id} href={`#${id}`}
      className="shrink-0 font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 hover:text-ink-200 transition-colors">
      {label}
    </a>
  ))}
</nav>
```

---

## Schema Migration Summary

### UserPreference (7 new columns)
```
vibePreferences   String[]  @default([])
travelStyleNote   String?
distanceUnit      String    @default("mi")
temperatureUnit   String    @default("F")
dateFormat        String    @default("MM/DD/YYYY")
timeFormat        String    @default("12h")
theme             String    @default("system")
```

### NotificationPreference (2 new columns)
```
checkinReminder    Boolean  @default(false)
preTripDaysBefore  Int      @default(3)
```

Total: 9 new columns across 2 tables. All have defaults — no data migration needed.

---

## What This Does NOT Include

- LLM extraction from travelStyleNote (future async job — delimiter isolation contract documented in Zod file)
- Currency display preference (no price data surfaced in UI yet)
- Language/locale (English-only for now)
- Home airport/location (no flight features)
- Emergency contacts (no mobile-native experience)
- Apple IAP (no native iOS app)
- Actually delivering notifications (push infra doesn't exist yet)
- Stripe webhook handler for subscription lifecycle (needed for checkout, not portal)
- Stripe customer cleanup on account delete (backlog item)
