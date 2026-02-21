# Globe Redesign + Landing Page Enrichment — Design Doc

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the hero globe from a centered widget into a cinematic backdrop, fix the broken trip map, add a local-sources section, and enrich existing landing copy with specific product features.

**Architecture:** Canvas 2D globe rewrite with compound rotation, AABB anti-collision for tooltip cards, new TripMapCanvas component ported from HTML mockup. No new dependencies.

**Tech Stack:** Next.js 14, TypeScript, Canvas 2D API, Tailwind CSS

---

## 1. Globe — Full-Bleed Backdrop

### Layout Change

Remove the 50/50 grid split. The globe canvas becomes `position: absolute; inset: 0` behind the entire hero section. Text content overlays at `z-[10]` with gradient protection.

**Hero section capped at `max-w-[1600px] mx-auto`** to prevent ultrawide gap between text and globe.

**Hero DOM structure:**
```
<section class="relative min-h-screen overflow-hidden max-w-[1600px] mx-auto">
  <!-- Z1: Globe canvas (full bleed) -->
  <div class="absolute inset-0 z-[1] hidden md:block">
    <GlobeCanvas />
  </div>

  <!-- Z2: Ambient terracotta glow (CSS, not canvas) -->
  <div class="absolute inset-0 z-[2] pointer-events-none"
       style="background: radial-gradient(ellipse at 72% 52%, rgba(196,105,79,0.06) 0%, transparent 65%)" />

  <!-- Z3: Gradient layers (5 total, explicit stop positions) -->
  <div class="absolute left-0 inset-y-0 w-[55%] z-[3] pointer-events-none"
       style="background: linear-gradient(to right, var(--bg-base-92) 0%, var(--bg-base-92) 30%, var(--bg-base-60) 50%, transparent 100%)" />
  <div class="absolute bottom-0 inset-x-0 h-[140px] z-[3] pointer-events-none"
       style="background: linear-gradient(to top, var(--bg-base-92) 0%, transparent 100%)" />
  <div class="absolute top-0 inset-x-0 h-[80px] z-[3] pointer-events-none"
       style="background: linear-gradient(to bottom, var(--bg-base-92) 0%, transparent 100%)" />
  <div class="absolute right-0 inset-y-0 w-[80px] z-[3] pointer-events-none"
       style="background: linear-gradient(to left, var(--bg-base-50) 0%, transparent 100%)" />

  <!-- Z10: Text content (same as current left column) -->
  <div class="relative z-[10] flex flex-col justify-center min-h-screen px-6 py-[60px] md:px-14 lg:pl-20 lg:pr-12 max-w-[600px]">
    <!-- eyebrow, headline, subtext, CTA, city pills -->
  </div>
</section>
```

**Review update:** Globe breakpoint changed from `lg` (1024px) to `md` (768px) — tablets get the cinematic treatment. Gradient stop positions are now explicit (solid at 0-30%, fading 30-50%, transparent after).

### Globe Positioning & Scale

| Parameter | Value | Notes |
|---|---|---|
| Globe center X | `min(W, 1600) * 0.72` | Offset right, ~35% cropped. Capped for ultrawide. |
| Globe center Y | `H * 0.52` | Slightly below center |
| Radius | `H * 0.82` | Viewport-height dominant |
| X-axis tilt | `-20deg` (fixed) | Spreads East Asian cluster |
| Y-axis rotation speed | `0.0008` rad/frame | ~131s full rotation at 60fps |
| Initial Y rotation | `-2.2` radians | Both city groups visible at load |

### Code Architecture (UPDATED per agent review)

**Extract pure functions to `globe-utils.ts`** for testability and separation of concerns:

```typescript
// apps/web/components/landing/globe-utils.ts

export interface Vec3 { x: number; y: number; z: number }
export interface ProjectedPoint { x: number; y: number; z: number; vis: boolean }

const TILT_X = -20 * (Math.PI / 180);
const cTilt = Math.cos(TILT_X);
const sTilt = Math.sin(TILT_X);

export function latLngToVec3(lat: number, lng: number): Vec3 {
  const p = ((90 - lat) * Math.PI) / 180;
  const t = ((lng + 180) * Math.PI) / 180;
  return { x: -Math.sin(p) * Math.cos(t), y: Math.cos(p), z: Math.sin(p) * Math.sin(t) };
}

export function projectPoint(v: Vec3, cx: number, cy: number, R: number, rotation: number): ProjectedPoint {
  const cY = Math.cos(rotation);
  const sY = Math.sin(rotation);
  const x1 = v.x * cY + v.z * sY;
  const z1 = -v.x * sY + v.z * cY;
  const y2 = v.y * cTilt - z1 * sTilt;
  const z2 = v.y * sTilt + z1 * cTilt;
  return { x: cx + x1 * R, y: cy - y2 * R, z: z2, vis: z2 > -0.12 };
}

export interface CardRect { x: number; y: number; width: number; height: number; cityIdx: number }
export function resolveCardPositions(cards: CardRect[], bounds: { width: number; height: number }): CardRect[] {
  // AABB force repulsion — 3 iterations
  // See Anti-Collision System section for algorithm
}
```

**Rotation parameter is explicit** (not a ref capture) — makes `projectPoint` a pure function.

### Card Rendering — Direct DOM Mutation (UPDATED per agent review)

**Do NOT use `useState` for card positions.** React re-renders at 30fps are wasteful. Instead:

```typescript
// In GlobeCanvas component:
const cardElemRefs = useRef<Map<number, HTMLDivElement>>(new Map());

// In rAF loop — direct DOM mutation, zero React involvement:
pC.forEach((c, i) => {
  const el = cardElemRefs.current.get(i);
  if (!el) return;
  const vis = c.z > 0.3;
  el.style.transform = `translate(${c.x}px, ${c.y}px) translateY(-50%)`;
  el.style.opacity = String(vis ? Math.min(0.92, c.z * 2.5) : 0);
  el.style.display = vis ? 'block' : 'none';
});

// JSX — rendered once, positioned via ref:
{CITIES.filter(c => c.main && c.card).map((city, i) => (
  <div key={city.name}
    ref={(el) => { if (el) cardElemRefs.current.set(i, el); else cardElemRefs.current.delete(i); }}
    className="absolute pointer-events-none z-[4]"
    style={{ willChange: 'transform, opacity', top: 0, left: 0 }}>
    {/* card content */}
  </div>
))}
```

Cards use `willChange: "transform, opacity"` for compositor layer promotion. Borders should be softer than standard `.card` — use `border-ink-700/60` for globe tooltip cards.

### Continent Dot Batching (UPDATED per agent review)

**Batch all dots into a single canvas path** — one `fill()` call instead of 400:

```typescript
ctx.fillStyle = contDotColor;
ctx.beginPath();
for (let i = 0; i < CONTINENT_DOTS.length; i++) {
  const [la, ln] = CONTINENT_DOTS[i];
  const v = latLngToVec3(la, ln);
  const p = projectPoint(v, cx, cy, R, rotation);
  if (p.z > -0.1) {
    ctx.moveTo(p.x + 2.0, p.y);
    ctx.arc(p.x, p.y, 2.0, 0, Math.PI * 2);
  }
}
ctx.fill(); // single GPU draw call
```

### Opacity Values (Bumped for Visibility)

| Element | Light mode | Dark mode |
|---|---|---|
| Continent dots | `rgba(184,92,63,0.18)`, 2.0px radius | `rgba(201,104,72,0.22)`, 2.0px radius |
| Globe sphere fill | `0.25 -> 0.06` gradient | `0.35 -> 0.08` gradient |
| Globe outline stroke | `rgba(184,92,63,0.08)` | `rgba(201,104,72,0.15)` (bumped from 0.10 — review) |
| Grid lines alpha | `0.10` | `0.12` |
| City glow ring | `rgba(184,92,63,0.25)` | `rgba(201,104,72,0.35)` |
| Route arcs | `0.4 - 0.6` opacity range | `0.4 - 0.6` opacity range |
| Card max opacity | `0.92` (never fully opaque) | `0.92` |

### City Roster (13 total)

**Featured (5, with tooltip cards) — source tags are brand-agnostic:**
- Tokyo (35.67, 139.65) — "TOKYO / DAY 1", "Tsukiji outer market", "locals-only / 06:00 counter", tag: "8.1k local reviews"
- Kyoto (35.01, 135.77) — "KYOTO / DAY 3", "Kinkaku-ji", "weekday / thins out by 15:00", tag: "4.2k local reviews"
- Seoul (37.57, 126.98) — "SEOUL / PIVOT", "Rain at 14:00", "swapping to indoor alternative"
- Barcelona (41.39, 2.17) — "BARCELONA / DAY 2", "El Born backstreets", "pre-lunch tapas crawl", tag: "Local"
- Osaka (34.69, 135.50) — "OSAKA / NIGHT", "Dotonbori standing bar", "walk-ins only before 18:00", tag: "5.6k local reviews"

**Note:** Osaka must be promoted to `main: true` with full card data. Current code has it as a minor dot — this is a data fix.

**Minor dots (8, visual rhythm only):**
- Lisbon (38.72, -9.14), r=4
- Istanbul (41.01, 28.98), r=4
- Marrakech (31.63, -8.00), r=3.5
- Taipei (25.03, 121.57), r=4
- Ho Chi Minh City (10.82, 106.63), r=3.5
- Mexico City (19.43, -99.13), r=3.5
- Buenos Aires (-34.60, -58.38), r=3
- Sydney (-33.87, 151.21), r=4

**Routes (3 arcs):**
- Tokyo -> Seoul
- Barcelona -> Istanbul
- Tokyo -> Sydney

### Anti-Collision System (~50 lines total)

1. **AABB force repulsion** (3 iterations, pushes overlapping cards apart) — **run every frame** (cheap at N=5, only 75 comparisons max)
2. **Vertical stagger** (when cluster detected within 100px, fan cards upward toward viewport top since globe is below-center)
3. **Canvas leader lines** (dashed terracotta curves from city dot to offset card)
4. **Lerp smoothing** (cards glide at 0.12 factor, ~300ms convergence) — store `targetX/Y` and `displayX/Y` separately, lerp every frame
5. **Visibility threshold** (cards only show when z > 0.3, max opacity 0.92)

### Animation Loop Pattern (UPDATED per agent review)

**Single entry point with IntersectionObserver gating:**

```typescript
const isRunningRef = useRef(false);
const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
const isDarkRef = useRef(false);

function startLoop() {
  if (isRunningRef.current) return;
  isRunningRef.current = true;
  rafRef.current = requestAnimationFrame(tick);
}

function stopLoop() {
  isRunningRef.current = false;
  cancelAnimationFrame(rafRef.current);
}

// Pause when offscreen or tab backgrounded
const observer = new IntersectionObserver(
  ([entry]) => { entry.isIntersecting ? startLoop() : stopLoop(); },
  { threshold: 0.01 }
);
observer.observe(canvas);

document.addEventListener('visibilitychange', () => {
  document.hidden ? stopLoop() : startLoop();
});

// Cleanup
return () => {
  stopLoop();
  observer.disconnect();
  document.removeEventListener('visibilitychange', visHandler);
  window.removeEventListener('resize', onResize);
};
```

**Hot path caching:**
- Cache `ctx` in a ref after first `getContext('2d')` — never call per frame
- Cache `isDark` via MutationObserver on `documentElement`, not DOM read per frame
- Cache sphere/ambient gradients — only recreate on resize when `cx/cy/R` changes
- Hoist `const ROUTE_DASH = [5, 3]` outside frame — no array allocation per route per frame
- Pre-allocate projected city array outside frame, mutate in-place — no `CITIES.map()` per frame

### devicePixelRatio Scaling (UPDATED per agent review)

```typescript
function resize() {
  const par = canvas.parentElement;
  if (!par) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = par.offsetWidth;
  const h = par.offsetHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  ctxRef.current!.setTransform(dpr, 0, 0, dpr, 0, 0);
  // Invalidate cached gradients here
}
```

### Mobile Treatment

Separate 320px banner below hero text. No tooltip cards on mobile — just dots and arcs. Radius: `min(W,H) * 0.45` (reduced from 0.55 per review — 0.55 fills banner edge-to-edge). Same tilt and city roster. Gradient fades top/bottom (60px each).

**Breakpoint:** `hidden md:block` for desktop globe, `md:hidden` for mobile banner. Tablets (768px+) get the cinematic treatment.

**Mobile performance:** Use `CONTINENT_DOTS_MOBILE` (every other dot, ~200) on `window.innerWidth < 768` to stay under 16ms frame budget on mid-range Android.

### Dynamic Import (UPDATED per agent review)

GlobeCanvas should be dynamically imported with `ssr: false` to avoid shipping canvas code in the SSR bundle:

```typescript
// In page.tsx
const GlobeCanvas = dynamic(
  () => import('@/components/landing/GlobeCanvas'),
  { ssr: false }
);
```

---

## 2. Trip Map — Port from HTML Mockup

Create `apps/web/components/landing/TripMapCanvas.tsx` porting the `drawTripMap()` function from `docs/overplanned-landing.html` (lines 725-803).

### Elements to render:
- **Background**: `var(--bg-stone)` (theme-aware, read via `getComputedStyle`)
- **Street grid**: 52px spacing, very low opacity white lines
- **Diagonal avenues**: 2 angled lines for visual depth
- **City blocks**: 8 semi-transparent rectangles
- **7 trip stops**: Tsukiji -> Senso-ji -> Shinjuku -> Harajuku -> Meiji -> Ginza -> Roppongi
- **Dashed route**: Terracotta quadratic bezier curves connecting stops
- **Stop styling**: Start = green glow, End = terracotta glow, Intermediate = gray
- **Labels**: Stop names with smart left/right positioning
- **Day markers**: "Day 1", "Day 2", "Day 3" at route intervals

### Progressive Draw Animation (from review):
Route draws itself progressively when the section scrolls into view, triggered by IntersectionObserver. The animation plays once and holds. Implementation:
- Track a `progress` value from 0 to 1 over **~2.5 seconds** (eased) — bumped from 1.5s per UI review for readability at 7 stops
- Draw the route path up to `progress * totalLength` using canvas path trimming
- Draw stops as they are "reached" by the route progress
- Labels fade in as their stop appears
- Once complete, hold the final state (no loop)
- **Cancel rAF handle after final frame** — do not keep spinning after one-shot completes
- Add `data-animation-complete="true"` attribute to wrapper when done (for testability)

### Font Loading Gate (UPDATED per agent review):
Canvas `fillText` bakes whatever font is available at call time. Since the animation plays once and holds, wrong font = permanent fallback baking.

```typescript
useEffect(() => {
  document.fonts.ready.then(() => {
    // Only start observing for intersection after fonts are loaded
    observer.observe(canvasRef.current!);
  });
}, []);
```

### devicePixelRatio for Text Crispness:
TripMapCanvas has text labels — unlike the globe's dot-matrix aesthetic, text at small sizes needs proper DPR scaling:

```typescript
const dpr = Math.min(window.devicePixelRatio || 1, 2);
canvas.width = containerWidth * dpr;
canvas.height = containerHeight * dpr;
ctx.scale(dpr, dpr); // must happen before any draw calls
```

### Integration:
Replace the placeholder `<div>Trip route visualization</div>` in the Trip Summary section with `<TripMapCanvas />` inside the `bg-stone` wrapper. Canvas should be responsive (`absolute inset-0`) with the existing map legend overlaid.

---

## 3. New Section: "Local Sources, Not Aggregators"

Add between the "How It Works" section and the "Persona" section.

### Content (UPDATED — no platform names, data-led cards per review):
- **Eyebrow**: "Sources That Matter"
- **Headline**: "We read the forums / *you can't.*"
- **Body**: "Every recommendation traces back to a local source -- review platforms in Japanese, resident forum threads, food bloggers writing for locals. Sources that don't show up in English search results, aggregated so you don't have to dig."
- **Visual**: Grid of 3 source attribution cards leading with data insights (not source type labels):
  - "8,100 reviews" / "Counter seating only, no reservations" / "Japan, updated weekly"
  - "27 locals confirmed" / "The market entrance tourists miss" / "Updated 3 days ago"
  - "4,200 local readers" / "Neighborhood-only picks" / "Korea, food-focused"
  - Each card styled like the existing chip/card system
  - No platform brand names anywhere

### Layout:
Same pattern as other sections — text left, visual right on desktop. `bg-base` background with `border-t border-ink-700`.

---

## 4. Enrich Existing Sections

### "How It Works" — Card 01 (line 549-552 in page.tsx) — UPDATED per review: no platform names
**Current body:** "The 8-seat ramen spot. The izakaya that only takes walk-ins before 18:00. The coffee bar that opened three months ago. Sources that don't translate, aggregated so you don't have to."
**Enriched body:** "The 8-seat ramen spot with 8,000 local reviews. The izakaya that only takes walk-ins before 18:00 -- sourced from a resident's forum post, not a guidebook. The coffee bar that opened three months ago, flagged by a local food blogger. Sources that don't translate, aggregated so you don't have to."

### "How It Works" — Card 02 (line 555-558)
**Current body:** 'Day four tired is different from day one tired. A quick coffee break tired is different from "cancel the afternoon" tired. The plan adjusts -- one slot, not a rebuild -- without you having to explain yourself.'
**Enriched body:** 'Day four tired is different from day one tired. A quick coffee break tired is different from "cancel the afternoon" tired. The plan swaps one slot -- not a rebuild -- pulling from pre-cached alternatives ranked by your persona. Rain at 14:00? The system already has three indoor options ready.'

### "Persona" section — DotList items (line 612-616)
Add a fourth bullet:
- "Works offline — swipe through pre-cached activities, signals sync when you reconnect"

---

## 5. CSS Variable Addition (UPDATED per review: pre-computed variants)

Add pre-computed opacity variants to **all 4 theme blocks** in `globals.css` (matches existing `--bg-surface-80` pattern):

```css
/* Add to [data-theme="light"] */
--bg-base-92: rgba(250, 248, 245, 0.92);
--bg-base-60: rgba(250, 248, 245, 0.60);
--bg-base-50: rgba(250, 248, 245, 0.50);

/* Add to [data-theme="dark"] */
--bg-base-92: rgba(16, 14, 11, 0.92);
--bg-base-60: rgba(16, 14, 11, 0.60);
--bg-base-50: rgba(16, 14, 11, 0.50);

/* Add to @media (prefers-color-scheme: dark) :root:not([data-theme]) */
--bg-base-92: rgba(16, 14, 11, 0.92);
--bg-base-60: rgba(16, 14, 11, 0.60);
--bg-base-50: rgba(16, 14, 11, 0.50);

/* Add to :root:not([data-theme]) (light fallback) */
--bg-base-92: rgba(250, 248, 245, 0.92);
--bg-base-60: rgba(250, 248, 245, 0.60);
--bg-base-50: rgba(250, 248, 245, 0.50);
```

Used by the 5 gradient layers in the hero section. Pre-computed = simpler than RGB decomposition.

---

## 6. Performance Requirements (UPDATED per agent review)

### Frame Budget Target
- Desktop: < 10ms per frame (60fps with headroom)
- Mobile banner: < 16ms per frame (60fps)
- Mid-range Android: use thinned dot array (~200 dots)

### Mandatory Optimizations
1. **Batch continent dots** into single canvas path — one `fill()` call, not 400
2. **No `useState` for card positions** — direct DOM mutation via refs
3. **IntersectionObserver** pauses rAF when globe scrolls offscreen
4. **`visibilitychange`** pauses rAF when tab is backgrounded
5. **Cache `getContext('2d')`** — call once, store in ref
6. **Cache `isDark`** via MutationObserver, not DOM read per frame
7. **Cache sphere/ambient gradients** — only recreate on resize
8. **Pre-allocate projected arrays** — no `CITIES.map()` per frame
9. **Hoist dash arrays** — `const ROUTE_DASH = [5, 3]` outside frame
10. **devicePixelRatio cap at 2** with proper canvas scaling
11. **Card throttle is time-based** (32ms wall clock) not frame-count-based (avoids 120Hz stutter)
12. **Dynamic import** with `ssr: false` — canvas code not in SSR bundle

### What to Profile First
1. Continent dot loop (add `performance.mark`, target < 4ms)
2. GC pressure from per-frame allocations (Chrome DevTools Minor GC bars)
3. React reconciliation cost (should be zero after DOM ref migration)
4. Gradient creation cost (should only fire on resize after caching)

---

## 7. Testing Requirements (NEW — from test engineer review)

### Extract to `globe-utils.ts` (prerequisite for all tests)
- `latLngToVec3(lat, lng)` — pure function, exported
- `projectPoint(v, cx, cy, R, rotation)` — pure function, explicit rotation param
- `resolveCardPositions(cards, bounds)` — AABB anti-collision, pure function

### Must-Have Tests
| Test | File | Framework |
|---|---|---|
| `latLngToVec3` math (poles, equator, unit magnitude) | `__tests__/landing/globe-utils.test.ts` | Vitest |
| `projectPoint` (visibility flag, scaling with R) | `__tests__/landing/globe-utils.test.ts` | Vitest |
| AABB collision (overlap separation, no-op for non-overlapping) | `__tests__/landing/globe-utils.test.ts` | Vitest |
| CSS tokens present in all 4 theme blocks | `__tests__/tokens/token-resolution.test.ts` | Vitest |
| GlobeCanvas renders canvas element | `__tests__/landing/GlobeCanvas.test.tsx` | Vitest |
| rAF cancelled on unmount | `__tests__/landing/GlobeCanvas.test.tsx` | Vitest |
| Resize listener cleaned up on unmount | `__tests__/landing/GlobeCanvas.test.tsx` | Vitest |
| TripMapCanvas: IntersectionObserver lifecycle | `__tests__/landing/TripMapCanvas.test.tsx` | Vitest |
| TripMapCanvas: rAF cleanup on unmount | `__tests__/landing/TripMapCanvas.test.tsx` | Vitest |

### Nice-to-Have Tests
- CONTINENT_DOTS count budget (300-500 range guard)
- Mobile breakpoint class presence
- `data-animation-complete` attribute after trip map finishes
- Playwright visual snapshot (canvas masked to avoid animation flakiness)
- Frame rate > 30fps in headless browser

---

## Files Summary

| File | Action |
|---|---|
| `apps/web/components/landing/globe-utils.ts` | Create (extracted pure functions: latLngToVec3, projectPoint, resolveCardPositions) |
| `apps/web/components/landing/GlobeCanvas.tsx` | Rewrite (compound rotation, backdrop positioning, DOM ref cards, batched dots, IO gating, cached hot path) |
| `apps/web/components/landing/TripMapCanvas.tsx` | Create (port from HTML mockup drawTripMap + progressive draw animation + font gate) |
| `apps/web/app/page.tsx` | Modify (hero layout with max-w cap, md breakpoint, explicit gradients, dynamic import, trip map integration, new section, enriched copy) |
| `apps/web/app/globals.css` | Add pre-computed `--bg-base-92/60/50` to all 4 theme blocks |
| `apps/web/__tests__/landing/globe-utils.test.ts` | Create (math + collision unit tests) |
| `apps/web/__tests__/landing/GlobeCanvas.test.tsx` | Create (mount, cleanup, lifecycle tests) |
| `apps/web/__tests__/landing/TripMapCanvas.test.tsx` | Create (IO lifecycle, cleanup tests) |
