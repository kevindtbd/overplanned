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

---

# Globe Redesign Review (2026-02-21)

*Reviewer: deepen-plan*

## Issues Addressed During Review

### 1. Visual Weight: Globe vs Headline (RESOLVED)
- **Concern:** H*0.82 globe might overpower headline text
- **Decision:** Keep H*0.82. If the globe looks cinematic, text being slightly subordinate is fine. Gradient layers protect text contrast for accessibility. Tune during implementation if needed.

### 2. Kyoto/Osaka Dot Overlap (RESOLVED)
- **Concern:** 0.32 degrees apart = ~8-12px at this radius, dots nearly merge
- **Decision:** Two dots is fine. Anti-collision handles the tooltip cards. Dots overlapping slightly is acceptable.

### 3. CSS Variable Strategy (RESOLVED -- PLAN UPDATED)
- **Concern:** `--bg-base-rgb` requires updating 4 theme blocks in globals.css
- **Decision:** Use pre-computed variants (`--bg-base-92`, `--bg-base-60`, etc.) instead of RGB decomposition. Matches existing `--bg-surface-80` pattern. Simpler maintenance.
- **Action:** Update plan Section 5 to use pre-computed variants instead of RGB variable.

### 4. Source Naming on Marketing Page (RESOLVED -- PLAN UPDATED)
- **Concern:** Naming Tabelog, Reddit, Naver publicly creates aging risk and potential IP issues
- **Decision:** Never name sources publicly. Describe source *types* instead: "local review platforms in Japanese," "resident forum threads," "local food bloggers." Specificity comes from data (review counts, freshness) not brand names.
- **Action:** Update plan Sections 3 and 4 to remove all platform names. Rewrite copy to be brand-agnostic.

### 5. Trip Map Animation (RESOLVED -- PLAN UPDATED)
- **Concern:** Static trip map may feel dead compared to animated globe
- **Decision:** Add progressive route-drawing animation triggered by IntersectionObserver. Route "draws itself" when scrolled into view, then holds. One-shot, not continuous.
- **Action:** Update plan Section 2 to include progressive draw animation using IntersectionObserver.

## Remaining Risks

### Performance: Globe at Backdrop Scale
- ~400 continent dots + 13 city dots + 3 routes + anti-collision + lerp = more work per frame at a larger canvas
- Canvas at H*0.82 on a 4K display = huge pixel count
- **Mitigation:** Already throttling card updates to every 2 frames. Monitor frame rate during implementation. Consider devicePixelRatio capping at 2 for the globe canvas.

### Gradient Layer Stacking on Various Browsers
- 5 overlapping gradient divs with pointer-events-none = no interaction issues, but rendering might vary
- **Mitigation:** Test in Chrome, Firefox, Safari during implementation. Gradients are CSS-only, well-supported.

### Text Contrast on Globe Overlap Zone
- Where the left gradient fades and the globe shows through, headline text sits on a semi-transparent background
- WCAG contrast may fail if gradient isn't strong enough
- **Mitigation:** The left gradient is solid for the first 35%, semi-transparent 35-55%. Headline should be fully within the solid zone. Test with contrast checker.

## No Changes Needed For
- Globe positioning values (W*0.72, H*0.52) -- solid reasoning
- Compound rotation math -- standard 3D rotation matrix, well-understood
- Anti-collision algorithm -- researched and validated, performance is trivial at this scale
- Mobile treatment -- separate banner is the right call
- City roster -- good geographic spread, removes problematic overlaps
