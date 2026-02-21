# Dashboard Design Audit Report

**Auditor:** Claude Opus 4.6
**Date:** 2026-02-20
**References:** `docs/overplanned-design-v4.html` (canonical design system), `docs/overplanned-landing.html` (landing/shared patterns)
**Scope:** All dashboard-related pages and their component trees

---

## Table of Contents

1. [Token & Infrastructure Audit](#1-token--infrastructure-audit)
2. [Dashboard Page (`/dashboard`)](#2-dashboard-page)
3. [Trip Detail Page (`/trip/[id]`)](#3-trip-detail-page)
4. [Onboarding Page (`/onboarding`)](#4-onboarding-page)
5. [Dashboard Components](#5-dashboard-components)
6. [Slot Components](#6-slot-components)
7. [Trip Components](#7-trip-components)
8. [Layout Components](#8-layout-components)
9. [Summary of Critical Discrepancies](#9-summary-of-critical-discrepancies)

---

## 1. Token & Infrastructure Audit

### 1.1 Accent Color Mismatch

| Layer | Value | Source |
|-------|-------|--------|
| CLAUDE.md (canonical) | `#C4694F` | Project instructions |
| `globals.css` light mode | `#C4694F` | Line 24 |
| `design-v4.html` light mode | `#B85C3F` | Line 22 |
| `overplanned-landing.html` | `#B85C3F` | Line 13 |
| `globals.css` dark mode | `#D07050` | Line 78 |
| `design-v4.html` dark mode | `#C96848` | Line 60 |

**Verdict:** Implementation follows CLAUDE.md (`#C4694F`), which overrides design-v4 (`#B85C3F`). This is correct per project rules (CLAUDE.md takes precedence). However, dark mode uses `#D07050` vs design-v4's `#C96848` -- needs confirmation which is canonical.

### 1.2 Missing `--accent-on` Token

- `design-v4.html` defines `--accent-on: #8C3A24` (light) and `--accent-on: #E8906E` (dark)
- `globals.css` uses `--accent-fg` instead of `--accent-on` (lines 27, 81)
- Tailwind config maps this as `accent-fg` (line 31 of `tailwind.config.ts`)
- The `VibeChips.tsx` component references `text-accent-fg` (line 43) which is correct for the implementation but diverges from the spec naming

**Impact:** Functionally equivalent but naming divergence makes spec-to-code tracing harder.

### 1.3 Font Weight Discrepancy

- `design-v4.html` base body: `font-weight: 300` (line 98)
- `globals.css` heading defaults: `font-weight: 600` (line 223)
- `design-v4.html` heading weight in type scale: `font-weight: 500` (lines 177-179, 1181, 1297-1300)

**Verdict:** The implementation uses `font-weight: 600` for headings globally. The spec consistently uses `font-weight: 500` for headings (page-title at 500, day-title at 500, sc-name at 500). This is a systematic mismatch across every heading in the app.

### 1.4 Missing Lora Font Usage

- `overplanned-landing.html` uses `Lora` for hero titles and section titles (serif italic accents)
- `tailwind.config.ts` includes `font-lora` (line 71) and `AppShell.tsx` uses `font-lora` (line 44)
- But the design-v4.html system reference does NOT use Lora at all -- it only uses Sora + DM Mono
- The landing page uses Lora + Outfit + DM Mono + Sora

**Verdict:** Lora is correct for the landing page but should not be used in the app shell or dashboard components per design-v4. The `AppShell.tsx` TripHero uses `font-lora` on line 44, which contradicts the design-v4 system that is Sora-only for the app interior.

### 1.5 `section-eyebrow` Implementation vs Spec

| Property | `globals.css` (line 257-274) | `design-v4.html` (line 200-207) |
|----------|------|------|
| Font size | `0.5625rem` (9px) | `10px` |
| Letter spacing | `0.05em` | `0.14em` |
| Color | `var(--accent)` | `var(--ink-400)` |
| Has `::before` line | Yes (18px accent line) | No (sec-label has no line) |

**Verdict:** The implementation's `section-eyebrow` borrows from the landing page pattern (`section-eyebrow` in `overplanned-landing.html` line 118) but the design-v4 system uses `sec-label` with `color: var(--ink-400)` and `letter-spacing: 0.14em` and NO decorative line. The dashboard `section-eyebrow` should follow design-v4's `sec-label` pattern, not the landing page's.

---

## 2. Dashboard Page

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/app/dashboard/page.tsx`

### 2.1 Page Header Typography

**Implementation (line 80-81):**
```tsx
<h1 className="font-sora text-2xl font-bold text-ink-100 sm:text-3xl">
```

**Spec (design-v4.html `page-title`, line 176-183):**
```css
font-size: 34px; font-weight: 500; letter-spacing: -0.025em; line-height: 1.15;
```

| Property | Implementation | Spec |
|----------|---------------|------|
| Font size | `text-2xl` (24px) / `sm:text-3xl` (30px) | 34px |
| Font weight | `font-bold` (700) | 500 |
| Letter spacing | none | -0.025em |
| Line height | Tailwind default (1.5) | 1.15 |

**Discrepancies:**
- Weight is 700 vs spec 500 -- too heavy
- Missing negative letter spacing
- Missing tight line height
- Size slightly off (30px vs 34px at desktop)

### 2.2 Page Subtitle

**Implementation (line 83-85):**
```tsx
<p className="mt-1 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
```

**Spec (`page-eyebrow`, line 167-174):**
```css
font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent);
```

| Property | Implementation | Spec |
|----------|---------------|------|
| Font size | `text-xs` (12px) | 10px |
| Color | `text-ink-400` | accent color |
| Letter spacing | `tracking-wider` (0.05em) | 0.16em |

**Discrepancies:**
- Color should be accent, not ink-400
- Letter spacing significantly tighter than spec
- Font size 12px vs 10px

### 2.3 Section Eyebrow Usage

**Implementation (lines 119, 136):**
```tsx
className="section-eyebrow mb-4"
```

Uses the globals.css `section-eyebrow` class which includes the decorative `::before` line. Per the design-v4 spec, the `sec-label` pattern for section headers inside the app does NOT have the decorative line. The landing-page-style eyebrow with the line is for marketing sections only.

### 2.4 Active Trips Grid

**Implementation (line 123):**
```tsx
<div className="grid gap-4 sm:grid-cols-2">
```

**Spec (design-v4 `dest-hero`):** The spec shows destination hero cards at full width (not 2-up grid), with 340px height, 20px border radius, and `shadow-lg`. The implementation uses `TripHeroCard` in a 2-column grid which is a reasonable adaptation, but the card height (`h-56 sm:h-64` = 224px / 256px) is shorter than the spec's 340px.

### 2.5 Missing Page Layout Wrapper

**Spec (design-v4 `.page`, line 161-165):**
```css
max-width: 1100px; margin: 0 auto; padding: 80px 40px 80px;
```

**Implementation:** Content padding comes from `AppShell` (line 143):
```tsx
<div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
```

`max-w-5xl` = 1024px vs spec's 1100px. Top padding is 24px-32px vs spec's 80px. The spec has much more generous vertical breathing room.

### 2.6 Missing Components

The dashboard page is missing several elements visible in the design-v4 spec:
- **Page description** (`page-desc` class) -- a body-text paragraph below the title
- **Section dividers** -- spec uses `border-bottom: 1px solid var(--ink-800)` between sections with 64px margin-bottom (line 194-198)
- **Empty state styling** -- the `EmptyState` component exists but its visual alignment with the spec's card/shell patterns is unverified

---

## 3. Trip Detail Page

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/app/trip/[id]/page.tsx`

### 3.1 Missing Itinerary Shell Structure

**Spec (design-v4 `itin-shell`, lines 1086-1092):**
```css
background: var(--bg-surface); border-radius: 22px;
border: 1px solid var(--ink-800); box-shadow: var(--shadow-lg);
```

**Implementation:** No outer shell wrapper. Content renders directly in the `AppShell` content area. The spec envisions the entire itinerary view wrapped in a rounded card shell with border and shadow. The implementation is flat.

### 3.2 Trip Header Typography

**Implementation (lines 266-267):**
```tsx
<h1 className="font-sora text-2xl sm:text-3xl font-bold text-ink-100">
```

**Spec (`day-title`, line 1181):**
```css
font-size: 22px; font-weight: 500; letter-spacing: -0.02em;
```

Same issues as dashboard: weight 700 vs 500, missing letter spacing.

### 3.3 Trip Metadata Bar

**Implementation (lines 269-283):**
```tsx
<div className="flex items-center gap-3 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
```

**Spec (`trip-sub`, line 1124):**
```css
font-family: 'DM Mono'; font-size: 10px; color: var(--ink-400); letter-spacing: 0.04em;
```

| Property | Implementation | Spec |
|----------|---------------|------|
| Font size | `text-xs` (12px) | 10px |
| Letter spacing | `tracking-wider` (0.05em) | 0.04em |
| Text transform | `uppercase` | None specified |

### 3.4 Day Header

**Implementation (lines 297-298):**
```tsx
<h2 className="font-sora text-lg font-semibold text-ink-100">
```

**Spec (`day-title`, line 1181):**
```css
font-size: 22px; font-weight: 500;
```

- `text-lg` = 18px vs spec 22px
- `font-semibold` = 600 vs spec 500

### 3.5 Missing Sidebar

**Spec (design-v4 `itin-body`, line 1170):**
```css
display: grid; grid-template-columns: 1fr 280px;
```

The spec includes a right sidebar (`itin-sidebar`) with route overview, stats grid, and driving tags. The implementation has no sidebar at all. This is a major structural omission.

### 3.6 Missing Energy Bar

**Spec (lines 1185-1221):** The `energy-row` component shows a gradient energy bar with label and status. Not present in implementation.

### 3.7 Missing Transit Rows

**Spec (lines 1334-1344):** Between slots, the spec shows `.transit-r` rows with walking/taxi time and cost. The implementation (`DayView.tsx`) has timeline dots and connecting lines but no transit information between slots.

### 3.8 AppShell TripHero Duplicates Day Navigation

The `AppShell` in trip context renders both a `TripHero` AND a `DayStrip` (line 133-134), but the trip detail page also renders its own `DayNavigation` component (line 287-293). This creates duplicate day navigation: one in the AppShell header (static placeholder) and one in the page content (functional).

---

## 4. Onboarding Page

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/app/onboarding/page.tsx`

### 4.1 Creation Flow Shell Missing

**Spec (design-v4 `.shell`, lines 670-676):**
```css
background: var(--bg-surface); border-radius: 22px;
border: 1px solid var(--ink-800); box-shadow: var(--shadow-lg);
```

The spec shows the creation flow wrapped in a `.shell` container with a `.topbar` and `.creation-grid` (left panel + right panel). The implementation uses a full-screen mobile-first wizard with no outer shell container.

**This is a fundamental layout divergence.** The spec envisions a desktop-first two-column layout (320px left panel + right panel) inside a bordered shell. The implementation is a centered single-column mobile-first wizard.

### 4.2 Step Progress Indicator

**Spec (`.step-track` + `.step-pip`, lines 696-711):**
```css
.step-pip { height: 5px; border-radius: 3px; background: var(--ink-700); width: 20px; }
.step-pip.done { background: var(--accent); opacity: 0.5; width: 14px; }
.step-pip.active { background: var(--accent); width: 28px; }
```

**Implementation (lines 237-244):**
```tsx
<div className="h-1 overflow-hidden rounded-full bg-ink-700">
  <div className="h-full rounded-full bg-accent" style={{ width: `${...}%` }} />
</div>
```

- Spec uses discrete pip segments with varying widths
- Implementation uses a single continuous progress bar
- Fundamentally different UI pattern

### 4.3 Missing Tag System (Right Panel)

**Spec (`.c-right`, lines 880-997):**
The design-v4 spec shows a right panel with:
- Tag panel head + count badge
- Drop zone with drag-and-drop
- Pool of chips organized by category (Food, Culture, Pace, Activity)
- Selected tags rendered as `sel-tag` pills with remove buttons

The implementation's `TripDNAStep` has a simplified version (pace radio, morning radio, food chip toggles) but lacks:
- The full tag category system with icon-badge headers
- Drag-and-drop drop zone
- The dual-panel layout
- Category-specific icon coloring per spec (food=accent, culture=info, pace=success, activity=warning)

### 4.4 Vibe Chip Styling

**Spec (`.vibe-chip`, lines 852-875):**
```css
padding: 7px 13px; background: var(--bg-raised);
border: 1.5px solid var(--ink-700); border-radius: 100px;
font-size: 12px; font-weight: 400; color: var(--ink-300);
```

Active state:
```css
border-color: var(--accent); background: var(--accent-light); color: var(--accent-on);
```

**Implementation (`TripDNAStep.tsx` food chips, line 140-141):**
```tsx
className={`rounded-full border px-3.5 py-1.5 font-dm-mono text-xs ${
  selected ? "border-accent bg-accent text-white" : "border-ink-700 bg-surface text-primary ..."
}`}
```

| Property | Implementation (active) | Spec (active) |
|----------|------------------------|---------------|
| Background | `bg-accent` (solid terracotta) | `var(--accent-light)` (tinted bg) |
| Text color | `text-white` | `var(--accent-on)` (#8C3A24) |
| Border | `border-accent` | `border-color: var(--accent)` |

**Verdict:** Active chips use solid accent fill with white text. Spec uses light tinted background with dark accent text. Very different visual weight.

### 4.5 Input Styling

**Spec (`.input`, lines 767-786):**
```css
padding: 11px 14px 11px 38px; background: var(--bg-input);
border: 1.5px solid var(--ink-700); border-radius: 12px;
```

**Implementation (DestinationStep.tsx, line 122):**
```tsx
className="w-full rounded-lg border border-ink-700 bg-surface py-3 pl-10 pr-4"
```

| Property | Implementation | Spec |
|----------|---------------|------|
| Background | `bg-surface` (white) | `var(--bg-input)` (#F3EFE9, warm tinted) |
| Border radius | `rounded-lg` (8px) | 12px |
| Border width | 1px (Tailwind default) | 1.5px |

### 4.6 Missing Field Labels

**Spec (`.field-label`, lines 732-738):**
```css
font-family: 'DM Mono'; font-size: 10px; letter-spacing: 0.12em;
text-transform: uppercase; color: var(--ink-400);
```

The implementation uses `label-mono` class which is close but has `letter-spacing: 0.05em` vs spec's `0.12em`. The letter spacing is less than half the spec value.

### 4.7 Missing Topbar with Wordmark

**Spec (`.topbar`, lines 679-694):**
```css
display: flex; align-items: center; justify-content: space-between;
padding: 14px 24px; border-bottom: 1px solid var(--ink-800);
```

With wordmark: `font-size: 17px; font-weight: 600; letter-spacing: -0.04em;` and buttons (Save draft + Continue).

The implementation has no topbar within the onboarding flow -- just the progress bar at the top of the screen.

---

## 5. Dashboard Components

### 5.1 TripHeroCard

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/dashboard/TripHeroCard.tsx`

**Spec reference:** `dest-hero` (lines 292-407)

| Property | Implementation | Spec |
|----------|---------------|------|
| Height | `h-56 sm:h-64` (224/256px) | 340px |
| Border radius | `rounded-2xl` (16px) | 20px |
| Shadow | `shadow-card` | `var(--shadow-lg)` |
| City name font size | `text-xl` (20px) | 38px |
| City name weight | `font-semibold` (600) | 500 |
| Country label | Not present | `font-family: DM Mono; font-size: 10px; uppercase` |
| Photo tags | Not present | Glass pill tags with icons over photo |
| Plan button | Not present | White pill button "Plan this trip" |
| Hover effect | `scale-[1.02]` | `scale(1.03)` |

**Major missing elements:**
- No glass-morphism photo tags over the hero image
- No "Plan this trip" action button
- No country/region DM Mono label above the city name
- No seasonal hint text
- Progress bar is fine but not in the spec's destination hero pattern

### 5.2 PastTripRow

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/dashboard/PastTripRow.tsx`

This component has no direct analog in design-v4.html. It is a reasonable custom addition. However:

- Border uses `border-ink-900` (line 53) which is nearly invisible in light mode (ink-900 = #F5F1EC, very close to bg-surface white). Should likely be `border-ink-800` or `border-ink-700` per the spec's consistent use of `var(--ink-800)` for card borders.
- Background uses `bg-surface` which matches spec for card interiors.

---

## 6. Slot Components

### 6.1 SlotCard

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/slot/SlotCard.tsx`

**Spec reference:** `slot-card` (lines 1274-1331)

| Property | Implementation | Spec |
|----------|---------------|------|
| Border radius | `rounded-2xl` (16px) | 13px |
| Border width | None (uses `shadow-card`) | `1.5px solid var(--ink-800)` |
| Padding | `p-4` (16px) | `13px 15px` |
| Background | `bg-surface` | `var(--bg-surface)` (same) |
| Layout | Full photo card (16:9 photo top) | Compact text card with optional thumbnail |

**Fundamental layout mismatch:** The spec's `slot-card` is a compact card with no photo by default (photo is only for anchor slots via `.slot-thumb`, 90px tall). The implementation renders every slot as a large photo card with 16:9 aspect ratio, status badges over the photo, etc. This is dramatically more visual than the spec.

**Spec slot card structure:**
```
sc-type (label) -> sc-name (name) -> sc-why (description) -> sc-foot (meta tags)
```

**Implementation structure:**
```
Photo (16:9) -> Status badge overlay -> Lock badge overlay ->
Content: name + whyThis + time/duration + VibeChips + SlotActions
```

The spec does NOT show action buttons (confirm/skip/lock) on the slot card itself. Those interactions are implied but the visual spec only shows meta tags (`mtag` pills).

### 6.2 SlotCard Type Label

**Spec (`.sc-type`, lines 1288-1295):**
```css
font-family: 'DM Mono'; font-size: 9px; letter-spacing: 0.12em;
text-transform: uppercase; color: var(--ink-400);
```

With colored variants:
```css
.sc-type.anchor-t { color: var(--accent); }
.sc-type.flex-t   { color: var(--info); }
.sc-type.meal-t   { color: var(--warning); }
.sc-type.break-t  { color: var(--success); }
```

**Implementation (SlotCard.tsx line 289-296):**
```tsx
<span className="shrink-0 label-mono bg-base px-1.5 py-0.5 rounded">
  {slot.slotType}
</span>
```

- No category-specific coloring
- Uses a background pill instead of inline colored text
- Missing the visual hierarchy that slot type creates per spec

### 6.3 SlotCard Meta Tags

**Spec (`.mtag`, lines 1315-1331):**
```css
font-family: 'DM Mono'; font-size: 10px; padding: 2px 9px;
border-radius: 100px; background: var(--bg-raised);
border: 1px solid var(--ink-800); color: var(--ink-400);
```

With semantic variants:
```css
.mtag.a { background: var(--accent-light); color: var(--accent-on); }
.mtag.s { background: var(--success-bg); color: var(--success); }
.mtag.w { background: var(--warning-bg); color: var(--warning); }
```

**Implementation:** Uses `VibeChips` component with different styling (11px font, `border-ink-700`, `bg-surface`). The chip styling is close but lacks the semantic coloring by category.

### 6.4 SlotActions -- Non-Spec Component

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/slot/SlotActions.tsx`

This component uses Tailwind color classes that are NOT from the design token system:
- `bg-emerald-100` (line 143) -- Tailwind default palette, not design tokens
- `border-emerald-300` (line 143) -- not a token
- `hover:border-emerald-400` (line 144) -- not a token
- `hover:border-red-400` (line 162) -- not a token
- `hover:text-error` (line 162) -- references `--error` which is custom but `error` is not in spec
- `bg-amber-100` (line 187) -- Tailwind default palette
- `border-amber-300` (line 187) -- not a token
- `hover:border-amber-400` (line 188) -- not a token

**Verdict:** This component uses raw Tailwind palette colors instead of design tokens. Should use `bg-success-bg`, `text-success`, `bg-warning-bg`, `text-warning`, `bg-accent-light`, `text-accent` etc.

### 6.5 Timeline Dot Colors (DayView.tsx)

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/trip/DayView.tsx`

**Implementation (line 49):**
```tsx
case "confirmed": return "bg-success border-emerald-200";
case "proposed": return "bg-warning border-amber-200";
```

**Spec (`.s-dot`, lines 1252-1265):**
```css
.s-dot.anchor { background: var(--accent); }
.s-dot.flex   { border: 2px solid var(--ink-500); }
.s-dot.meal   { background: var(--warning); }
.s-dot.rest   { background: var(--success); }
```

The spec colors dots by SLOT TYPE (anchor/flex/meal/rest), not by STATUS (confirmed/proposed/completed). The implementation colors by status. This is a semantic mismatch in what the dot communicates.

Also uses `border-emerald-200` and `border-amber-200` -- raw Tailwind, not tokens.

---

## 7. Trip Components

### 7.1 DayNavigation

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/trip/DayNavigation.tsx`

**Spec (`.day-tabs` + `.dtab`, lines 1144-1167):**
```css
.dtab { padding: 11px 18px; font-size: 13px; font-weight: 400; color: var(--ink-400);
        border-bottom: 2px solid transparent; }
.dtab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }
```

**Implementation (lines 145-163):**
Active tab: `bg-accent text-white shadow-sm`
Inactive tab: `bg-surface text-ink-400 border border-ink-700`

| Property | Implementation | Spec |
|----------|---------------|------|
| Active style | Solid accent pill with white text | Text accent + bottom border accent |
| Inactive style | Surface card with border | Transparent with bottom border only |
| Shape | Rounded pill (`rounded-lg`) | Flat tab with bottom border |
| Active indicator | Fill color | 2px bottom border |

**Verdict:** Completely different visual paradigm. Spec uses underline tabs. Implementation uses filled pill buttons. The spec's approach is more space-efficient and conventional for day navigation.

### 7.2 DayNavigation Arrows

The spec does NOT include prev/next arrow buttons. The `day-tabs` are a simple horizontally-scrollable tab strip. The implementation adds prev/next buttons which is a reasonable UX enhancement but not in spec.

### 7.3 DayNavigation Mobile Swipe

The implementation includes touch swipe handling (lines 61-80) and a "Swipe to change day" hint (line 201). This is not in the spec but is a good mobile UX addition.

---

## 8. Layout Components

### 8.1 AppShell

**File:** `/home/pogchamp/Desktop/overplanned/apps/web/components/layout/AppShell.tsx`

**Spec reference:** `itin-shell` (lines 1086-1092) and `itin-top` (lines 1094-1127)

The spec shows an `itin-shell` with:
- Topbar: back link + divider + trip name/sub + avatar stack
- Day tabs strip
- Two-column body: main content + sidebar (280px)

The AppShell implementation:
- Uses a desktop sidebar (`DesktopSidebar`) + mobile bottom nav (`MobileNav`) -- not in spec
- Trip context: photo hero + DayStrip + content -- DayStrip is a placeholder
- App context: MobileTopBar + content

### 8.2 TripHero (in AppShell)

**Implementation (lines 21-51):**
- Height: `h-48` (192px) -- spec `dest-hero` is 340px
- Title uses `font-lora` -- spec uses `font-family: 'Sora'` for app interior
- "Active trip" label: `text-[8px]` -- spec eyebrow is 10px minimum
- No warm gradient matching spec's dual-gradient overlay

### 8.3 DayStrip (in AppShell)

**Implementation (lines 55-91):**
- Hardcoded weekday names (Mon-Sun) -- should be actual trip days
- `text-[8px]` tabs -- spec `dtab` is 13px
- Active uses `text-ink-100 border-accent` which is closer to spec
- Font size is less than half the spec value

### 8.4 MobileTopBar Wordmark

**Implementation (lines 95-105):**
```tsx
<span className="font-sora font-bold text-base tracking-[-0.04em]">
  overplanned<span className="text-accent">.</span>
</span>
```

**Spec (`.wordmark`, lines 688-694):**
```css
font-size: 17px; font-weight: 600; letter-spacing: -0.04em;
```

The wordmark is "Way**mark**" in the spec (with colored span), but the implementation uses "overplanned." -- this is correct for the actual product, spec uses a placeholder name.

Weight is `font-bold` (700) vs spec `600`.

---

## 9. Summary of Critical Discrepancies

### Severity: HIGH (Visual/Structural Mismatch)

| # | Issue | Files Affected | Spec Reference |
|---|-------|---------------|----------------|
| H1 | **Heading weight 600/700 everywhere, spec says 500** | All pages, all components | design-v4 type scale |
| H2 | **SlotCard is full-photo layout, spec is compact text card** | `SlotCard.tsx`, `DayView.tsx` | `.slot-card` lines 1274-1331 |
| H3 | **DayNavigation uses filled pills, spec uses underline tabs** | `DayNavigation.tsx` | `.dtab` lines 1154-1167 |
| H4 | **Onboarding is mobile-first wizard, spec is desktop two-column shell** | `onboarding/page.tsx`, all step components | `.shell`, `.creation-grid` lines 670-728 |
| H5 | **Trip detail missing sidebar** (route overview, stats, driving tags) | `trip/[id]/page.tsx` | `.itin-sidebar` lines 1396-1448 |
| H6 | **Trip detail missing itinerary shell wrapper** | `trip/[id]/page.tsx` | `.itin-shell` lines 1086-1092 |
| H7 | **Raw Tailwind colors used instead of design tokens** | `SlotActions.tsx`, `DayView.tsx` | Global token system |
| H8 | **AppShell DayStrip is placeholder (hardcoded weekdays, 8px font)** | `AppShell.tsx` lines 55-91 | `.day-tabs` lines 1144-1167 |

### Severity: MEDIUM (Token/Spacing Mismatch)

| # | Issue | Files Affected | Spec Reference |
|---|-------|---------------|----------------|
| M1 | **section-eyebrow follows landing pattern, not app pattern** | `globals.css`, `dashboard/page.tsx` | `.sec-label` lines 200-207 |
| M2 | **Input background uses bg-surface instead of bg-input** | `DestinationStep.tsx`, `DatesStep.tsx`, onboarding name step | `.input` lines 767-786 |
| M3 | **label-mono letter-spacing 0.05em vs spec 0.12em** | All uses of `label-mono` / `field-label` | `.field-label` lines 732-738 |
| M4 | **Page padding too tight** (24-32px vs spec 80px vertical) | `AppShell.tsx` | `.page` lines 161-165 |
| M5 | **TripHeroCard height 224/256px vs spec 340px** | `TripHeroCard.tsx` | `.dest-hero` lines 293-301 |
| M6 | **Active vibe chips: solid accent fill vs spec light tinted** | `TripDNAStep.tsx` food chips | `.vibe-chip.active` lines 869-873 |
| M7 | **Border radius inconsistencies** (16px impl vs 13-22px spec) | `SlotCard.tsx`, `TripHeroCard.tsx` | Various |
| M8 | **Timeline dots colored by status vs spec by slot type** | `DayView.tsx` | `.s-dot` lines 1252-1265 |
| M9 | **font-lora used in AppShell TripHero, not in design-v4 scope** | `AppShell.tsx` line 44 | Sora-only for app interior |
| M10 | **Duplicate day navigation** (AppShell DayStrip + page DayNavigation) | `AppShell.tsx`, `trip/[id]/page.tsx` | Single `.day-tabs` |
| M11 | **PastTripRow border uses ink-900 (nearly invisible in light mode)** | `PastTripRow.tsx` line 53 | ink-800 or ink-700 for borders |

### Severity: LOW (Minor Polish)

| # | Issue | Files Affected |
|---|-------|---------------|
| L1 | Dashboard subtitle color ink-400 vs spec accent for eyebrow | `dashboard/page.tsx` line 83 |
| L2 | Dashboard subtitle font-size 12px vs spec 10px | `dashboard/page.tsx` line 83 |
| L3 | Missing transition on slot card border hover | `SlotCard.tsx` |
| L4 | Step progress bar continuous vs spec discrete pips | `onboarding/page.tsx` lines 237-244 |
| L5 | Missing hover `translateY(-3px)` on trip cards | `TripHeroCard.tsx` (only scales) |
| L6 | No energy bar component for day view | `trip/[id]/page.tsx` |
| L7 | No transit rows between slots | `DayView.tsx` |
| L8 | Missing source badges on slot photos | `SlotCard.tsx` |
| L9 | Missing local/tourist signal badges on slot photos | `SlotCard.tsx` |

---

## Recommendations (Priority Order)

1. **Fix heading weights globally** -- change `font-bold` / `font-semibold` (700/600) to `font-medium` (500) for all h1-h3 elements
2. **Replace raw Tailwind colors** in `SlotActions.tsx` and `DayView.tsx` with token-based classes
3. **Rethink SlotCard layout** -- spec intends compact text-first cards, not photo-heavy cards. Consider a compact mode for timeline view and expanded mode for detail view
4. **Restyle DayNavigation** to underline tabs per spec, or document the pill-button approach as an intentional departure
5. **Remove or wire the AppShell DayStrip** -- either remove it and let the page-level DayNavigation handle everything, or wire it to actual trip state and remove the page-level one
6. **Add itinerary shell wrapper** to trip detail page for the bordered-card container
7. **Update input backgrounds** from `bg-surface` to `bg-input`
8. **Widen letter-spacing** in `label-mono` from 0.05em to at least 0.10em
9. **Address onboarding layout** -- decide if mobile-first wizard is intentional departure or if desktop should get the two-column shell
10. **Add trip sidebar** to desktop trip view (route, stats, driving tags)
