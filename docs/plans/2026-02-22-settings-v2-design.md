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

---

## 1. Travel Interests (Hybrid)

### What it is

A new section on the settings page (positioned between existing Preferences and Notifications). Curated vibe tag chips grouped by category, plus an optional free-form textarea.

### Vibe tag selection

Sourced from the locked 42-tag vibe vocabulary (`docs/overplanned-vibe-vocabulary.md`), filtered to user-level preferences (excluding activity-level tags like cash-only, queue-worthy, book-ahead, no-frills):

**Pace & Energy**
- `high-energy` — High energy
- `slow-burn` — Slow burn
- `immersive` — Immersive

**Discovery Style**
- `hidden-gem` — Hidden gems
- `iconic-worth-it` — Iconic & worth it
- `locals-only` — Locals only
- `offbeat` — Offbeat & unexpected

**Food & Drink**
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

Total: 23 tags across 5 groups. UI: same chip pattern as existing Preferences (tap to toggle, terracotta fill when active, CheckIcon). Multi-select, no min/max.

### Free-form text

Below the chips: a textarea with placeholder text.

Label (dm-mono, uppercase): "Anything else about how you travel?"
Placeholder: "I always hunt for the best coffee spot in every city..."
Max length: 500 characters. Character count shown when > 400.

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

### ML integration (async, not on save path)

When `travelStyleNote` changes, a background job (not blocking the PATCH response) sends the text to the LLM for persona dimension extraction. Results written to `PersonaDimension` table. This is future work — the settings page just stores the raw text. The API route does NOT call any LLM.

### Component

Extend existing `PreferencesSection.tsx` — add vibe tag chips and textarea below the travel frequency fieldset. Same debounce pattern (500ms). Same auto-save. Same revert-on-failure.

---

## 2. Display Preferences

### What it is

A new subsection within Preferences, below travel frequency and above vibe tags. Five display format controls.

### Fields

| Field | Options | Default | UI |
|---|---|---|---|
| Distance | mi, km | mi | Two-option radio pills |
| Temperature | F, C | F | Two-option radio pills |
| Date format | MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD | MM/DD/YYYY | Three-option radio pills |
| Time format | 12h, 24h | 12h | Two-option radio pills |
| Theme | Light, Dark, System | system | Three-option radio pills |

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

Add to `updatePreferencesSchema`:
```typescript
distanceUnit: z.enum(DISTANCE_UNITS).optional(),
temperatureUnit: z.enum(TEMPERATURE_UNITS).optional(),
dateFormat: z.enum(DATE_FORMATS).optional(),
timeFormat: z.enum(TIME_FORMATS).optional(),
theme: z.enum(THEME_OPTIONS).optional(),
```

### Theme application

Theme toggle sets `data-theme` attribute on `<html>`:
- `light` → `data-theme="light"`
- `dark` → `data-theme="dark"`
- `system` → remove `data-theme`, let CSS `prefers-color-scheme` handle it

To prevent flash-of-wrong-theme on page load, add an inline `<script>` in the root layout that reads the theme from a cookie (set alongside DB save) and applies `data-theme` before first paint. The cookie is set client-side on theme change: `document.cookie = "theme=dark;path=/;max-age=31536000"`.

### API changes

Same preferences endpoint — GET returns new fields, PATCH accepts them. Defaults filled in when no record exists.

---

## 3. Stripe Billing Portal

### What it is

A "Manage billing" link in the SubscriptionBadge section that opens Stripe's hosted Customer Portal.

### API route

`POST /api/settings/billing-portal`

```typescript
// Auth required
// If user.stripeCustomerId is null → 404
// Otherwise:
const session = await stripe.billingPortal.sessions.create({
  customer: user.stripeCustomerId,
  return_url: `${process.env.NEXTAUTH_URL}/settings`,
});
return NextResponse.json({ url: session.url });
```

### UI changes to SubscriptionBadge

Props change: add `stripeCustomerId: string | null`.

Below the tier badge pill, conditionally render:
```
{stripeCustomerId && (
  <button onClick={handleManageBilling} className="font-dm-mono text-xs text-ink-400 hover:text-accent transition-colors">
    Manage billing
  </button>
)}
```

On click: POST to `/api/settings/billing-portal`, redirect to returned URL.

For beta users with no `stripeCustomerId`: no link shown, badge stays as-is.

### Page wiring

Pass `stripeCustomerId` from session to SubscriptionBadge. Check if `stripeCustomerId` is exposed in the session — if not, need to add it to the NextAuth session callback, or fetch it from a separate endpoint.

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
- **Position**: Rendered below "Reminders before upcoming trips" toggle, only visible when `tripReminders` is `true`
- **Behavior**: Immediate PATCH on change, revert on failure

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

## Section Order on Settings Page

1. Account (existing)
2. Subscription + Stripe portal (enhanced)
3. Preferences — display prefs, dietary, mobility, languages, frequency (enhanced)
4. Travel Interests — vibe tags + free-form (new section)
5. Notifications + new fields (enhanced)
6. Privacy & Data (existing)
7. About (existing)

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

- LLM extraction from travelStyleNote (future async job)
- Currency display preference (no price data surfaced in UI yet)
- Language/locale (English-only for now)
- Home airport/location (no flight features)
- Emergency contacts (no mobile-native experience)
- Apple IAP (no native iOS app)
- Actually delivering notifications (push infra doesn't exist yet)
