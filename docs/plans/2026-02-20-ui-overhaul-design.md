# UI Visual Overhaul Design

*Created: 2026-02-20*
*Status: Reviewed + Finalized*
*Review notes: docs/plans/plan-review-notes.md*
*Reviewers: Systems Architect, Security Auditor, Test Engineer, Frontend Designer+Coder*

---

## Guiding Principles (from overplanned-philosophy.md)

Every decision in this overhaul runs through these filters:

1. **"Warm, calm surface. Intelligent underneath."** -- restraint IS the communication. No visual noise.
2. **"Photography does the warmth work"** -- UI chrome is warm-neutral. The world provides the color.
3. **"The Notion quality"** -- layout breathes. One primary action per component. Everything else revealed on interaction.
4. **"This Gets Me" north star** -- not "does this look good?" but "does this feel like it knows me?"
5. **No demographic profiling, no gamification, no surveillance language.**

When in doubt: **ask the user, don't guess.**

---

## Problem Statement

22 pixel-perfect HTML mockups exist for every screen. The implemented UI uses ~20% of the design vocabulary:

1. **Token gap**: globals.css has 5 CSS vars. Mockups define 30+ (ink scale, bg hierarchy, shadows, semantic colors, gold).
2. **Font gap**: Code has Sora + DM Mono. Mockups use Sora + DM Mono + Lora (serif headlines).
3. **Component gap**: Components use generic Tailwind (amber-50, gray-100) not design tokens. Missing photo overlays, "why this" lines, source badges, energy strips, glass-pill badges, skeleton loaders, empty states.
4. **Screen gap**: Landing page is inline-styled placeholder with Google-blue button. Most screens render mock data.
5. **Backend gap**: No POST/GET /api/trips. Onboarding crashes. Trip detail shows hardcoded Tokyo data.
6. **Dark mode gap**: Simplified media query, not the comprehensive data-theme token set.

---

## Execution: Bottom-Up Sequential

Phases 0 -> 1 -> 2 -> 3+4 interleaved. Each phase is its own atomic commit. Each phase depends on the previous.

**Phase 1 includes backward-compatible aliases** for old token names so the app does not break before Phase 2 lands. Phase 2 removes the aliases after migrating all consumers.

---

## Phase 0: Test Infrastructure (Pre-requisite)

Before any implementation begins, set up the test foundation.

### Framework: Vitest (not Jest)
- Existing tests already import from `vitest`. Current jest.config.ts is broken (missing setup file, typo in config key, no deps installed).
- Delete `apps/web/jest.config.ts`, create `apps/web/vitest.config.ts`
- Install: vitest, @vitejs/plugin-react, jsdom, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, vitest-mock-extended
- E2E: Playwright (already configured, add mobile/tablet viewport projects)
- Accessibility: axe-core, @axe-core/playwright

### Test Utilities
- `apps/web/__tests__/__mocks__/prisma.ts` -- Prisma client singleton mock
- `apps/web/__tests__/__mocks__/auth.ts` -- NextAuth session mock helper
- `apps/web/__tests__/helpers/request.ts` -- NextRequest factory
- `apps/web/__tests__/helpers/render.ts` -- Custom render wrapper with providers (session, theme)

### Package.json Scripts
```json
{
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage",
  "test:e2e": "playwright test --config=../../playwright.config.ts"
}
```

### Playwright Config Updates
```typescript
projects: [
  { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  { name: 'mobile', use: { ...devices['iPhone 13'] } },
  { name: 'tablet', use: { ...devices['iPad (gen 7)'] } },
]
```

---

## Phase 1: Token Foundation

### Canonical Source

**design-v4.html is the source of truth** for token names and values. Where design-v4 doesn't define a token that screen mockups use (e.g., --bg-stone, --bg-warm, --gold), merge from screen mockups using the most common value.

**TOKEN FREEZE**: Once Phase 1 is committed, token names are immutable. No renames after this point.

### Token Reconciliation Table

Where mockups disagree, design-v4.html wins:

| Token | design-v4.html | solo-view.html | states.html | Canonical |
|-------|---------------|----------------|-------------|-----------|
| --bg-base | #FAF8F5 | #F7F4EF (as --bg) | #FAFAF8 (as --bg) | #FAF8F5 |
| --bg-surface | #FFFFFF | #FFFFFF (as --bg-card) | #FFFFFF (as --bg-card) | #FFFFFF |
| --accent | #B85C3F | #C4694F | #C4694F | **#C4694F** (CLAUDE.md canonical) |

Note: Mockup references to `--bg-card` map to `--bg-surface`. Mockup references to `--bg` map to `--bg-base`.

### CSS Variables (globals.css rewrite)

**Light theme** (`[data-theme="light"]`):
```css
/* Background hierarchy */
--bg-base:      #FAF8F5;    /* page background (design-v4 canonical) */
--bg-surface:   #FFFFFF;    /* card surfaces */
--bg-raised:    #F3EFE9;    /* elevated surfaces, inputs */
--bg-overlay:   #EDE8E1;    /* overlay backgrounds */
--bg-input:     #F3EFE9;    /* form inputs */
--bg-stone:     #EAE4DA;    /* secondary elevated (from screen mockups) */
--bg-warm:      #F5F1EB;    /* warm variant (from screen mockups) */

/* Accent: Terracotta — #C4694F is canonical (CLAUDE.md) */
--accent:         #C4694F;
--accent-light:   #F0E0D9;
--accent-muted:   #D4886E;
--accent-fg:      #8C3A24;  /* foreground text on accent-light backgrounds */

/* Secondary accent: Gold (from screen mockups, used in Lora headlines) */
--gold:           #A07830;
--gold-light:     #F5EDD8;

/* Ink scale (INVERTED from Tailwind convention: 100=darkest, 900=lightest) */
--ink-100:  #1C1713;   /* primary text */
--ink-200:  #3A302A;   /* strong secondary */
--ink-300:  #5C5048;   /* body secondary */
--ink-400:  #7A6E64;   /* muted text */
--ink-500:  #9C8E84;   /* subtle text, labels */
--ink-600:  #BDB0A6;   /* very subtle, icons */
--ink-700:  #D6CFC8;   /* borders, dividers */
--ink-800:  #EAE4DE;   /* subtle borders */
--ink-900:  #F5F1EC;   /* near-bg */

/* Semantic */
--success:     #4A8A5C;   --success-bg: #E0EEE5;
--info:        #3A6A8C;   --info-bg:    #D8E8F2;
--warning:     #A07830;   --warning-bg: #F2EAD8;
--error:       #8C2A2A;   --error-bg:   #F5E0E0;

/* Shadows (warm-tinted, never blue) */
--shadow-sm:   0 1px 3px rgba(28,23,19,0.06), 0 1px 2px rgba(28,23,19,0.04);
--shadow-md:   0 4px 16px rgba(28,23,19,0.08), 0 1px 4px rgba(28,23,19,0.04);
--shadow-lg:   0 12px 48px rgba(28,23,19,0.10), 0 2px 8px rgba(28,23,19,0.05);
--shadow-card: 0 2px 8px rgba(28,23,19,0.06);
--shadow-xl:   0 32px 80px rgba(28,23,19,0.12), 0 8px 24px rgba(28,23,19,0.07);

/* Animation/Transition tokens */
--transition-fast:   150ms ease;
--transition-normal: 200ms ease;
--transition-slow:   300ms ease-out;

/* Backward-compatible aliases (REMOVE IN PHASE 2) */
--color-terracotta:          var(--accent);
--color-warm-background:     var(--bg-base);
--color-warm-surface:        var(--bg-surface);
--color-warm-border:         var(--ink-700);
--color-warm-text-primary:   var(--ink-100);
--color-warm-text-secondary: var(--ink-400);
```

**Dark theme** (`[data-theme="dark"]`):
```css
--bg-base:      #100E0B;
--bg-surface:   #171310;
--bg-raised:    #1F1A15;
--bg-overlay:   #28211A;
--bg-input:     #1F1A15;
--bg-stone:     #1C1813;
--bg-warm:      #141109;

--accent:         #D07050;
--accent-light:   rgba(208,112,80,0.14);
--accent-muted:   #8C402A;
--accent-fg:      #E8906E;  /* inverts: foreground text on dark accent surfaces */

--gold:           #C8A96E;
--gold-light:     rgba(200,169,110,0.12);

--ink-100:  #F0EAE2;   /* primary text (inverted) */
--ink-200:  #D4C8BC;
--ink-300:  #A89484;
--ink-400:  #7A6A5C;
--ink-500:  #5C4E42;
--ink-600:  #3D332A;
--ink-700:  #2E251E;   /* borders (inverted) */
--ink-800:  #221C16;
--ink-900:  #1A1410;

--success:     #5A9E6A;   --success-bg: rgba(90,158,106,0.12);
--info:        #4A84A8;   --info-bg:    rgba(74,132,168,0.12);
--warning:     #B8943A;   --warning-bg: rgba(184,148,58,0.12);
--error:       #C25555;   --error-bg:   rgba(194,85,85,0.12);

--shadow-sm:   0 1px 3px rgba(0,0,0,0.3);
--shadow-md:   0 4px 20px rgba(0,0,0,0.4);
--shadow-lg:   0 16px 60px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);
--shadow-card: 0 2px 12px rgba(0,0,0,0.25);
--shadow-xl:   0 32px 80px rgba(0,0,0,0.6);

--transition-fast:   150ms ease;
--transition-normal: 200ms ease;
--transition-slow:   300ms ease-out;

/* Backward-compatible aliases (REMOVE IN PHASE 2) */
--color-terracotta:          var(--accent);
--color-warm-background:     var(--bg-base);
--color-warm-surface:        var(--bg-surface);
--color-warm-border:         var(--ink-700);
--color-warm-text-primary:   var(--ink-100);
--color-warm-text-secondary: var(--ink-400);
```

### Theme Switching Mechanism

**Implementation spec** (addresses SSR hydration flash):

1. CSS `[data-theme="light"]` and `[data-theme="dark"]` selectors for all tokens
2. `@media (prefers-color-scheme: dark)` fallback that duplicates dark tokens for no-JS users
3. Inline `<script>` in `app/layout.tsx` via `dangerouslySetInnerHTML` in `<head>` (NOT a Next.js Script component):
```tsx
<html lang="en" suppressHydrationWarning>
  <head>
    <script dangerouslySetInnerHTML={{ __html: `
      (function(){
        var t = localStorage.getItem('theme');
        if (!t) t = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', t);
      })()
    `}} />
  </head>
```
4. `suppressHydrationWarning` on `<html>` is REQUIRED -- server cannot know user's preference
5. Theme toggle component writes to localStorage + updates `data-theme` attribute

### Fonts (3 total)

| Font | Role | Weights | Source |
|------|------|---------|--------|
| Sora | Body, UI text, CTAs, wordmark | 300, 400, 500, 600, 700 | next/font/google (exists, add 700) |
| DM Mono | Data, labels, badges | 300, 400 | next/font/google (exists) |
| Lora | Serif headlines, emotional text | 400i, 500 | next/font/google (NEW) |

Outfit dropped -- Sora 600-700 covers CTAs and wordmark. Near-identical geometric sans-serif at UI sizes.

### Tailwind Config

All tokens under `colors` to auto-generate bg-*, text-*, border-*, ring-* variants:

```typescript
colors: {
  ink: {
    100: 'var(--ink-100)', // darkest (primary text) — INVERTED from Tailwind convention
    200: 'var(--ink-200)',
    // ... through 900 (lightest, near-bg)
  },
  accent: {
    DEFAULT: 'var(--accent)',
    light: 'var(--accent-light)',
    muted: 'var(--accent-muted)',
    fg: 'var(--accent-fg)',
  },
  gold: { DEFAULT: 'var(--gold)', light: 'var(--gold-light)' },
  success: { DEFAULT: 'var(--success)', bg: 'var(--success-bg)' },
  info: { DEFAULT: 'var(--info)', bg: 'var(--info-bg)' },
  warning: { DEFAULT: 'var(--warning)', bg: 'var(--warning-bg)' },
  error: { DEFAULT: 'var(--error)', bg: 'var(--error-bg)' },
},
backgroundColor: {
  base: 'var(--bg-base)',
  surface: 'var(--bg-surface)',
  raised: 'var(--bg-raised)',
  overlay: 'var(--bg-overlay)',
  input: 'var(--bg-input)',
  stone: 'var(--bg-stone)',
  warm: 'var(--bg-warm)',
},
boxShadow: {
  sm: 'var(--shadow-sm)',
  md: 'var(--shadow-md)',
  lg: 'var(--shadow-lg)',
  card: 'var(--shadow-card)',
  xl: 'var(--shadow-xl)',
},
fontFamily: {
  sora: ['var(--font-sora)', 'sans-serif'],
  'dm-mono': ['var(--font-dm-mono)', 'monospace'],
  lora: ['var(--font-lora)', 'serif'],
},
```

Remove hardcoded terracotta-50 through terracotta-900 scale -- replaced by CSS-var-driven accent tokens that respond to theme switching.

### Utility Classes (@layer components)

```css
.label-mono          /* DM Mono 8-10px, uppercase, tracking-wider, ink-500 */
.section-eyebrow     /* DM Mono 9px, uppercase, accent, ::before 18px line */
.btn-primary         /* Sora 14px/600, accent bg, rounded-full, shadow, hover:translateY(-2px), single-line only */
.btn-ghost           /* DM Mono 10px, uppercase, ink-400, hover arrow translateX(3px) */
.btn-secondary       /* Outlined: bg-surface, ink-700 border, hover:bg-raised */
.card                /* bg-surface, 1px ink-700 border, rounded-2xl, shadow-card */
.chip                /* DM Mono 7-8px, pill, category-colored bg, min-height 24px for WCAG touch target */
.chip-local          /* success-bg + success */
.chip-source         /* info-bg + info */
.chip-busy           /* warning-bg + warning */
.photo-overlay-warm  /* linear-gradient(to top, rgba(14,10,6,0.92) 0%, rgba(14,10,6,0.15) 55%) */
.skel                /* ink-800 bg, 6px radius, shimmer animation (pauses on prefers-reduced-motion) */
```

### Phase 1 Tests
- Token swatch dev page at `/dev/tokens` -- renders all CSS variables in both themes
- Visual regression: Playwright `toHaveScreenshot()` on swatch page (2 screenshots: light + dark)
- Verify all CSS variables resolve (no `var(--undefined)`)
- Dark mode toggle works on desktop, mobile, tablet viewports
- Theme persistence: survives page navigation, hard refresh, respects prefers-color-scheme
- Font loading: all 3 fonts render with correct fallback stack
- Backward-compatible aliases resolve correctly (old token names still work)
- Accessibility: color contrast ratios meet WCAG AA for all ink-on-bg combinations

---

## Phase 2: Core Components

### Migration Strategy

Break-and-fix all at once. Rewrite component internals + update every consumer in same commit.
Where possible: keep same prop interface, only change JSX/styles. Add new props (whyThis, etc.) as optional.

**Pre-work**: Run breakage inventory grep for all old token class usage across `apps/web/`:
- `bg-warm-surface`, `bg-warm-background`, `bg-app`, `text-warm-text-primary`, `text-warm-text-secondary`, `border-warm-border`, `text-terracotta`, `bg-terracotta-*`
- `bg-amber-*`, `bg-emerald-*`, `bg-gray-*`, `text-amber-*`, `text-emerald-*`, `text-gray-*` (hardcoded Tailwind colors in SlotCard STATUS_CONFIG etc.)

**Remove backward-compatible aliases** from globals.css after all consumers are migrated.

### SlotCard (match: overplanned-solo-view.html .slot)
- Time row: DM Mono 9px ink-500 + hairline separator
- Photo: warm overlay + booking badge (DM Mono 7px, backdrop-blur, pill) + `will-change: transform` on hover scale
- Content: bg-raised (bg-stone in dark), rounded-b-[14px]
- Name: Sora 13px/500 ink-100
- **"Why this" line**: 11px ink-400 italic 300 weight, 1-line clamp -- NEW
- Footer: source chips (chip-local/chip-source/chip-busy) + circular action buttons (26px, bg-surface, ink-700 border)
- States: `.now` = accent border-left + accent-light bg | `.done` = opacity 0.55
- NEW optional prop: `whyThis?: string`

### Skeleton Loaders (match: overplanned-states.html)
- SlotSkeleton: photo rect + 2 text lines, shimmer animation
- CardSkeleton: full card with photo + body placeholders
- ListSkeleton: rows with thumbnail circle + lines
- Loading message: 11px ink-400 italic centered
- Shimmer pauses when `prefers-reduced-motion: reduce` is set

### Empty States (match: overplanned-states.html)
- Icon container: 56px, rounded-2xl, bg-raised
- Title: Lora 17px/500 italic ink-200
- Body: 12px ink-400 300 weight
- CTA: btn-primary or btn-ghost

### Error States (match: overplanned-states.html)
- Error token: --error / --error-bg
- Retry button with error accent

### AppShell + Navigation (match: overplanned-app-shell.html + nav architecture doc)
- **App context**: bottom nav (4 tabs, 7px DM Mono labels, accent active, badge dot) + desktop sidebar
- **Trip context**: hero photo + day strip overlay + energy bar, NO app nav
- **Wordmark**: Sora 16-19px/700, letter-spacing -0.04em, accent on "."
- **Desktop**: persistent left sidebar, trip tabs in main area

### Photo Treatments
- Warm overlay: `rgba(14,10,6,0.92)` bottom -> transparent top (NEVER cool-black)
- Source badge: DM Mono 7-9px, `rgba(12,9,6,0.42)` bg, backdrop-blur(6px), pill
- Signal badge: glass pill (gem=success, warn=warning)
- Hero city: Lora serif over photo

### Phase 2 Tests
- Unit tests for every component (render, props, states) using @testing-library/react
- **Interaction tests**: click handlers, keyboard events, form inputs per component
- **Accessibility**: axe-core integration in every component test
- SlotCard matrix: 6 statuses x 2 photo states x 2 whyThis states x 2 locked states = 48 render cases (use `it.each`)
- SlotCard interaction tests: 6 statuses x 2 locked states = 12 cases verifying correct action availability
- SlotCard: long text truncation for whyThis, missing photo fallback rendering
- Skeleton/Empty/Error states render correctly in both themes
- Navigation: app context vs trip context switching
- Visual regression: Playwright screenshots for SlotCard 6 states x 2 themes = 12 screenshots
- All old token aliases removed -- grep confirms zero usage of old class names

---

## Phase 3+4: Screens + API (Interleaved)

Build API route first, then the screen that consumes it. Per-screen approach.

### Security Requirements (all API routes)

- **Authentication**: Every route calls `getServerSession(authOptions)` -- defense-in-depth, do not rely on middleware alone
- **Authorization (IDOR prevention)**:
  - `GET /api/trips` -- return ONLY trips where user is a TripMember (join query)
  - `GET /api/trips/[id]` -- verify user is a TripMember before returning data, return 403 if not
  - `PATCH /api/trips/[id]` -- verify user is organizer role TripMember
  - `POST /api/trips` -- any authenticated user can create (fine)
- **Input validation**: Zod schemas on all POST/PATCH bodies
  - Max lengths on string fields (destination: 200, city: 100, name: 200)
  - Enum validation for mode, status
  - IANA timezone validation
  - Date validation (endDate >= startDate, not in past for creation)
  - XSS sanitization on freetext fields

### Execution Order

**Step 1: Landing page** (no API dependency)
- Match overplanned-landing.html exactly
- Hero section with Lora headlines, gold `<em>` accents
- 3D globe (Three.js/Globe.gl) -- **lazy-loaded**:
  - Wrap in `next/dynamic({ ssr: false })` with static image placeholder during SSR
  - Load only on viewport intersection (IntersectionObserver) or after page idle
  - Mobile (<900px): globe-banner fallback, Three.js bundle NOT downloaded at all
  - Consider `@react-three/fiber` + `@react-three/drei` for better tree-shaking
- Feature sections, social proof
- Nav: fixed top, Sora wordmark, DM Mono links, theme toggle

**Step 2: Schema migration**
- Add `name String?` to Trip model in Prisma
- Run `prisma migrate dev`

**Step 3: Trip CRUD API routes**
- `POST /api/trips` -- create trip + TripMember(organizer) in transaction. Trip.userId = creator (denormalized), TripMember = normalized ownership record. Zod validation.
- `GET /api/trips` -- list user's trips via TripMember join, ordered by startDate, with status badges
- `GET /api/trips/[id]` -- full trip with slots, vibes, members. 403 if not a member.
- `PATCH /api/trips/[id]` -- update trip details (name, dates, destination). Organizer only.

**Step 4: Onboarding** (needs POST /api/trips)
- Match overplanned-onboarding.html
- Fork screen: full-bleed photo hero with Lora title, accent CTAs
- Destination: search input with suggestion cards (photo + city + meta)
- Dates: styled date pickers matching field-input pattern
- Trip DNA: category accordions with chip selection
- Wire to POST /api/trips, redirect to trip detail

**Step 5: Home Dashboard** (needs GET /api/trips)
- Match overplanned-app-shell.html home screen
- Wordmark top bar + avatar (user data from NextAuth session)
- Upcoming trip hero card (photo overlay, Lora city name, "open trip" glass button)
- Prep cards grid (2-col)
- Quick actions row
- Past trip rows (thumbnail + name + meta + status badge)
- Empty state if no trips (use states mockup pattern)

**Step 6: Trip Detail / Solo View** (needs GET /api/trips/[id])
- Match overplanned-solo-view.html
- Hero: destination photo + warm overlay + Lora city + DM Mono meta
- Day strip: overlaid on hero, DM Mono 8px tabs, active underline
- Energy strip: gradient bar with position marker
- Slot list: rebuilt SlotCard component with real data
- Trip context navigation (no app nav)

### P1 Screens (follow-up)
- Discover (overplanned-discover.html) -- cold start vibes, shortlist, returning user
- Map View (overplanned-map-view.html)
- Day View detail (overplanned-day-view.html)

### P2 Screens (later)
- Group, Pivot, Mid-Trip, Post-Trip, Calendar, Itinerary Reveal

### Phase 3+4 Tests
- **API route unit tests** (test handler functions directly, mock Prisma + auth session):
  - POST /api/trips: happy path, 401 unauth, 400 validation (missing destination, bad dates, invalid timezone), 500 DB error
  - GET /api/trips: returns only member trips, ordered by startDate, empty array, 401 unauth
  - GET /api/trips/[id]: full data, 404 not found, 403 not a member, 401 unauth
  - PATCH /api/trips/[id]: happy path, 403 non-organizer, 400 validation, 401 unauth
- **Onboarding E2E**: each step renders and navigates (forward/back), destination search works, dates accepted, Trip DNA persists, submit creates trip + redirects to detail, round-trip data verification
- **Onboarding failure E2E**: network error shows error state with retry, session expired redirects to auth
- Dashboard: renders with 0 trips (empty state), 1 trip (hero card), multiple trips (list)
- Trip detail: renders real data, day switching works
- **Responsive**: every P0 screen at 375px, 768px, 1280px, 1440px viewports
- Dark mode: every P0 screen in both themes
- **Accessibility**: axe-core audit on every P0 screen

---

## Philosophy Compliance Checks

- No visual noise: one primary action per component
- Photography does the warmth: chrome is neutral, photos provide color
- No emoji anywhere
- No demographic profiling language
- No gamification elements
- Warm gradients only (never cool-black overlays)
- Automate with grep/lint rules where possible

---

## Schema Change

```prisma
model Trip {
  // ... existing fields ...
  name  String?   // User-facing display name, e.g. "Tokyo Mar 2026"
}
```

---

## Responsive Strategy

**Mobile-first** from mockups (375-390px frames).
**Desktop adapts**: sidebar layout, wider content area, multi-column where appropriate.
**Fill gaps** where mockups don't specify desktop behavior -- use the desktop-dashboard.html mockup as reference for dashboard, adapt others logically.
**Breakpoints tested**: 375px, 768px, 1280px, 1440px.

---

## Out of Scope

- Stripe payment integration (beta mode, no paywall)
- FastAPI ML services
- Qdrant vector DB
- Group invite/join beyond basic UI
- Real-time features (WebSocket)
- Admin panel redesign
- P1/P2 screens (follow-up work)
- DELETE /api/trips/[id] (intentional omission for P0)

---

## Success Criteria

1. Every P0 screen visually matches its HTML mockup in both light and dark mode
2. Onboarding flow creates a real trip in the database
3. Trip detail page loads real data from Prisma
4. Home dashboard shows user's actual trips
5. No hardcoded mock data in any P0 screen
6. All three fonts rendering correctly (Sora, DM Mono, Lora)
7. Theme toggle works with proper token switching, no hydration flash
8. All component tests pass (including interaction + accessibility)
9. All API route tests pass (including auth/authz/validation)
10. Responsive at 375px, 768px, 1280px, 1440px for every P0 screen
11. Loading/empty/error states implemented for every data-dependent screen
12. Zero philosophy violations (no emoji, no noise, warm overlays only)
13. Zero IDOR vulnerabilities on trip endpoints
14. axe-core passes on all P0 screens
