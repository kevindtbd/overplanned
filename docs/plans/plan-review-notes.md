# Plan Review Notes: UI Visual Overhaul

*Reviewed: 2026-02-20*
*Reviewer: deepen-plan*

---

## Critical Issues (Must Address)

### 1. Token values in plan don't match canonical source
**Problem:** The plan lists #F7F4EF for --bg, but design-v4.html (declared canonical) uses #FAF8F5 for --bg-base. Multiple mockups have slightly different values.
**Resolution:** Use design-v4.html as the single source of truth. Cross-reference and update ALL token values in the plan to match design-v4.html exactly. Where design-v4 doesn't define a token that other mockups use (e.g., --bg-stone, --bg-warm), use the most common value across mockups.

### 2. Phase 3-4 dependency loop unresolved
**Problem:** Plan says Phases 3-4 can be parallelized, but screens need API data and API routes need to exist before screens can render real data.
**Resolution:** Interleave per screen. For each P0 screen: build the API route first, then build the screen that consumes it. Updated execution order:
1. Landing page (no API dependency)
2. Trip CRUD API routes (POST/GET /api/trips, GET /api/trips/[id])
3. Onboarding (needs POST /api/trips)
4. Home Dashboard (needs GET /api/trips)
5. Trip Detail (needs GET /api/trips/[id])

### 3. Component rewrite migration strategy undefined
**Problem:** 15+ files import from the current SlotCard, AppShell, and Navigation. Plan doesn't specify how to handle the breakage.
**Resolution:** Break-and-fix all at once. Rewrite component + update every consumer in the same commit. No temporary V2 duplication.

---

## Gaps Identified

### 4. Landing page globe is a major subtask
The landing page mockup requires a 3D interactive globe (Three.js/Globe.gl). This is a significant standalone task that will add ~200KB to the bundle and requires:
- Three.js or Globe.gl dependency
- City coordinate data
- Floating card positioning
- Mobile fallback (mockup shows a simplified banner version on small screens)
- Performance optimization (requestAnimationFrame, lazy loading)

**Recommendation:** Treat the globe as a self-contained subtask within Phase 3. It can be built independently and dropped into the landing page layout.

### 5. Responsive strategy not specified
The mockups are mobile-frame layouts (375-390px). Desktop mockup exists (overplanned-desktop-dashboard.html) but not all screens have desktop variants.
**Resolution:** Mobile-first from mockups. Desktop adapts with sidebar layout. Fill gaps where mockups don't fully specify desktop behavior.

### 6. Theme toggle mechanism needs specifics
**Resolution:** CSS media queries as baseline (prefers-color-scheme), data-theme attribute as explicit override. Small inline script in <head> reads localStorage preference, falls back to matchMedia. Works on desktop/mobile/iPad without JS dependency for initial render.

### 7. No error/loading states mentioned
The plan rebuilds screens but doesn't mention loading skeletons, error states, or empty states. The mockups have a "states" file (overplanned-states.html) that likely covers these.
**Recommendation:** Check overplanned-states.html for loading/error/empty patterns and include them in Phase 3 screen work.

### 8. No mention of the Trip model's `name` field
The onboarding creates a trip name, but the Prisma Trip model doesn't have a `name` field (checked first 100 lines). The POST /api/trips route will need to handle this -- either the model needs a name column or the name goes into `personaSeed` JSON.
**Recommendation:** Verify the full Prisma schema for a `name` field on Trip before building the API route.

---

## Risks

### 9. Scope is large
4 phases, ~14 screens (6 P0), full token rewrite, 6+ new API routes, component library rebuild, Three.js integration. This is easily a multi-day effort.
**Mitigation:** Strict P0/P1/P2 prioritization. Ship P0 screens first. P1 and P2 can be follow-up work.

### 10. Font loading performance
Four Google Fonts (Sora, DM Mono, Lora, Outfit) adds network requests and potential FOUT/FOIT.
**Mitigation:** Next.js font optimization (next/font/google) handles preloading and subsetting. Already used for Sora + DM Mono. Lora + Outfit just need to be added the same way.

---

## Suggested Improvements

1. **Add overplanned-states.html to Phase 2 scope** -- loading skeletons and error states are part of the component library
2. **Verify Trip.name field** exists in Prisma schema before Phase 4 API work
3. **Update token values** to use design-v4.html as canonical (not app-shell.html values)
4. **Landing page globe as isolated subtask** with its own dependency (Three.js) and mobile fallback
5. **Add "theme provider" component** in Phase 1 that handles detection, localStorage, and the data-theme attribute
