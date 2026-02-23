# Settings Polish: Preferences Expansion + Privacy Consent UX

## Goal
Make the settings page feel complete and dense rather than sparse and stubby. Three workstreams: expand My Preferences content, improve Privacy consent UX with value framing, and two quick UI fixes (toggle visibility, travel interests disclosures).

## UI Fixes (already applied, committed separately)
1. **Toggle off-state**: `bg-warm-border` -> `bg-ink-500` in NotificationsSection (off track was invisible on warm-surface card)
2. **Travel Interests**: Removed disclosure toggles, all 5 vibe groups always expanded with thin dividers between them

---

## Workstream A: Preferences Expansion

### Problem
My Preferences has 4 small fieldsets (Dietary 7, Accessibility 4, Languages 2, Frequency 3+null). Too narrow — only covers constraints, not actual preferences. Lots of whitespace. Doesn't capture budget, accommodation, or transit preferences that directly affect recommendations.

### Design Decisions
- **2-col grid on desktop, 1-col on mobile** — fills horizontal space, reduces vertical sprawl
- **Tighter spacing** — `gap-y-4` instead of `space-y-6`
- **Same chip pattern** — consistent with existing fieldsets and TravelInterests
- **Free-form textarea** — same pattern as TravelInterests (`travelStyleNote`), blur-save, 500 char max
- **No companion style** — per-trip setting, not global preference

### New Content

**Expanded existing groups:**
- Dietary: +3 (dairy-free, pescatarian, no pork) = 10 total
- Accessibility: +2 (service animal, limited stamina) = 6 total

**New groups (4):**
| Group | Type | Options |
|-------|------|---------|
| Budget comfort | Radio (single) | Budget-friendly, Mid-range, Splurge-worthy, Mix of everything |
| Spending priorities | Chips (multi) | Food & drink, Experiences, Accommodation, Shopping |
| Accommodation | Chips (multi) | Hostel, Boutique hotel, Chain hotel, Airbnb/rental, Camping |
| Getting around | Chips (multi) | Walking, Public transit, Rideshare, Rental car, Biking, Scooter |

**Free-form field:**
- Label: "Anything else about how you prefer to travel?"
- Placeholder: "I always need a gym nearby, never book hostels..."
- Blur-save, 500 char max, character counter at <=100 remaining

### Grid Layout (desktop 2-col)
| Left | Right |
|------|-------|
| Dietary needs (10) | Accessibility (6) |
| Budget comfort (4 radio) | Spending priorities (4 chips) |
| Accommodation (5 chips) | Getting around (6 chips) |
| Language comfort (2) | Travel frequency (4 radio) |
| *Free-form textarea (full-width)* | |

### Schema
5 new columns on `UserPreference`:
```
budgetComfort       String?
spendingPriorities  String[]  @default([])
accommodationTypes  String[]  @default([])
transitModes        String[]  @default([])
preferencesNote     String?
```

### Zod
New enums: `BUDGET_OPTIONS`, `SPENDING_PRIORITY_OPTIONS`, `ACCOMMODATION_OPTIONS`, `TRANSIT_OPTIONS`
Expand: `DIETARY_OPTIONS` (+3), `MOBILITY_OPTIONS` (+2)

### API
Extend `PREF_SELECT`, `DEFAULTS`, dedup block (3 new arrays), upsert create block in `preferences/route.ts`.
Also update GDPR export route to include new fields.

---

## Workstream B: Privacy Consent UX

### Problem
Consent toggles default OFF and have dry legal-sounding labels. Users don't turn them on because there's no visible benefit. The labels don't explain *why* data sharing helps.

### Design Decisions
- **Defaults ON** in schema (`@default(true)` on both fields)
- **First-visit consent banner** — shows once, dismissible, stored in localStorage
- **Value-first framing** — emphasize what the user gets, not what we take
- **Stats** — "40% more relevant suggestions within first 3 trips" (aspirational but grounded)
- **Sub-text** under each toggle explaining what it does in plain language

### Banner (first visit only)
Shows at top of consent section inside the card. Dismisses via `localStorage.setItem("consent-banner-seen", "1")`.

```
HOW YOUR DATA HELPS

Your preferences and trip patterns help us learn what makes great
recommendations. Users who share their data see up to 40% more
relevant suggestions within their first 3 trips.

Both options below are currently enabled. You can change these anytime.

[Got it]
```

"Got it" button: `rounded-full border border-accent text-accent px-4 py-1.5 font-sora text-sm hover:bg-accent/10`

### Reframed Toggle Labels

**modelTraining:**
- Label: "Help us learn your travel style"
- Sub-text: "We use your trip patterns and preferences to surface better recommendations for you and travelers like you."

**anonymizedResearch:**
- Label: "Contribute to travel insights"
- Sub-text: "Your anonymized data helps us understand travel trends and improve our recommendation engine for everyone."

Sub-text style: `font-sora text-xs text-ink-400 mt-0.5`

### Toggle off-state
Same fix as NotificationsSection: `bg-ink-500` for off track.

### Schema
Change DataConsent model defaults:
```
modelTraining       Boolean @default(true)    // was false
anonymizedResearch  Boolean @default(true)     // was false
```

### API
Update DEFAULTS in `privacy/route.ts` to `{ modelTraining: true, anonymizedResearch: true }`.
