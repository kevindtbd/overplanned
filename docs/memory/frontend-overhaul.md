# Frontend UI Overhaul — Learnings & Specs

## Problem Statement
Despite 22 pixel-perfect HTML mockups, the implemented UI used ~20% of the design vocabulary. Tokens existed in CSS but weren't wired into Tailwind or consumed by components.

## Design Token System (Implemented in Phase 1)

### Token Architecture
CSS custom properties on `[data-theme="light"]` / `[data-theme="dark"]` selectors, mapped through `tailwind.config.ts` via `var(--token)`.

### Full Token List (Light / Dark)
| Token | Light | Dark |
|-------|-------|------|
| --bg-base | #FAF8F5 | #100E0B |
| --bg-surface | #FFFFFF | #1A1714 |
| --bg-raised | #F5F0EB | #231F1B |
| --bg-overlay | rgba(0,0,0,0.4) | rgba(0,0,0,0.6) |
| --bg-stone | #EDE8E1 | #2A2520 |
| --bg-warm | #F7F3EE | #1E1B17 |
| --bg-input | #FFFFFF | #1A1714 |
| --ink-100 (darkest) | #1A1512 | #FAF8F5 |
| --ink-200 | #3D3530 | #E8E0D8 |
| --ink-300 | #6B5E54 | #BFB3A8 |
| --ink-400 | #8C7E73 | #9E9189 |
| --ink-500 | #A89A90 | #8C7E73 |
| --ink-900 (lightest) | #D6CEC6 | #3D3530 |
| --accent | #C4694F | #D4795F |
| --accent-light | #F5E6E0 | #2E1E18 |
| --accent-muted | #E8A994 | #8B4A35 |
| --accent-fg | #FFFFFF | #FFFFFF |
| --gold | #B8960C | #D4AD0E |
| --gold-light | #FBF5E0 | #2E2A10 |
| --shadow-sm/md/lg/card/xl | warm-tinted shadows | same pattern |
| --transition-fast/normal/slow | 150ms/250ms/400ms | same |

### Ink Scale is INVERTED
ink-100 = darkest (primary text), ink-900 = lightest (near-bg). **User explicitly chose this.** Opposite of Tailwind gray convention. Document everywhere.

### Backward-Compat Aliases (Phase 1 only, removed in Phase 2)
Old names alias to new: `--color-warm-background → --bg-base`, `--color-warm-surface → --bg-surface`, `--color-warm-border → --ink-900`, `--color-terracotta → --accent`, `--color-text-primary → --ink-100`, `--color-text-secondary → --ink-300`

## Font Decisions (3 Families)
| Font | Role | Weights |
|------|------|---------|
| Sora | Body, UI, CTAs, wordmark | 300-700 |
| DM Mono | Data, labels, metadata | 400-500 |
| Lora | Serif headlines, emotional text | 400, 500 (normal + italic) |

**Outfit was DROPPED** — near-identical to Sora at UI sizes (confirmed by frontend reviewer comparing letterforms). No visual distinction at 14-18px body text.

## Theme Switching
- `[data-theme="light"]` / `[data-theme="dark"]` CSS selectors
- Inline `<script>` in `<head>` via `dangerouslySetInnerHTML` reads localStorage → matchMedia fallback
- `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }` for no-JS
- `suppressHydrationWarning` on `<html>` tag (required for SSR)

## Component Patterns from Mockups
- `.btn-primary` — bg-accent, text-accent-fg, rounded-xl, Sora semibold
- `.btn-ghost` — transparent bg, ink-200 text, hover bg-stone
- `.btn-secondary` — bg-raised border ink-900
- `.card` — bg-surface, shadow-card, rounded-2xl, p-5
- `.chip` variants — chip-accent, chip-gold, chip-outline
- `.photo-overlay-warm` — `rgba(14,10,6,0.92)` warm-brown (NEVER cool-black)
- `.skel` — shimmer animation with `prefers-reduced-motion` pause
- `.label-mono` — DM Mono, uppercase, tracking-wider, ink-300
- `.section-eyebrow` — DM Mono, uppercase, accent color, letter-spacing 0.08em

## Key Implementation Files
- `apps/web/app/globals.css` — Full token definitions, component classes, theme selectors
- `apps/web/tailwind.config.ts` — Token mapping, font families, backward-compat aliases
- `apps/web/app/layout.tsx` — Font loading (Sora+DM Mono+Lora), theme script, suppressHydrationWarning
- `apps/web/app/dev/tokens/page.tsx` — Token swatch dev page with theme toggle

## Test Infrastructure (Phase 0)
- **Vitest** (not Jest — old jest.config.ts was broken and deleted)
- Config: `apps/web/vitest.config.ts` + `apps/web/vitest.setup.ts`
- Mocks: `__tests__/__mocks__/prisma.ts`, `__tests__/__mocks__/auth.ts`
- Helpers: `__tests__/helpers/request.ts` (NextRequest factory), `__tests__/helpers/render.tsx` (custom render)
- Playwright: mobile (iPhone 13), tablet (iPad gen 7), desktop viewports
- Token tests: `__tests__/tokens/token-resolution.test.ts` (7 tests)

## Migration Inventory
~50 files use old token class names. Phase 2 bulk-migrates them:
- `bg-warm-*` → `bg-base`, `bg-surface`, `bg-raised`
- `text-warm-*` → `text-ink-100`, `text-ink-300`, etc.
- `border-warm-*` → `border-ink-900`
- `text-terracotta` → `text-accent`
- `bg-terracotta` → `bg-accent`

## Security Requirements (from agent reviews)
- IDOR prevention on trip endpoints: verify `TripMember` before returning data
- Zod validation on all POST/PATCH bodies
- `getServerSession` defense-in-depth on every API route
- Three.js globe: `next/dynamic({ ssr: false })`, viewport intersection trigger, skip on mobile (<900px)

## Pre-existing Issues
- `@/lib/auth` barrel import doesn't exist (only `@/lib/auth/config.ts`, `gates.ts`, `session.ts`)
- 4 AdminLayout tests fail because of this — NOT related to UI overhaul
- Build also fails on this import in `middleware/admin.ts`

## Remaining Phases
- **Phase 2**: Core components — bulk token migration (50 files), SlotCard rewrite, skeleton/empty/error states, AppShell+nav rewrite, remove backward-compat aliases
- **Phase 3+4**: Screens + API interleaved — landing page, Trip.name schema migration, trip CRUD routes, onboarding, dashboard, trip detail
