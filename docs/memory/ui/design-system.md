# UI / Design System

## Token Architecture
CSS custom properties on `[data-theme="light"]` / `[data-theme="dark"]`, mapped through `tailwind.config.ts` via `var(--token)`.

### Full Token List
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

### CRITICAL: Ink Scale is INVERTED
ink-100 = darkest (primary text), ink-900 = lightest (near-bg). Opposite of Tailwind gray convention.

## Fonts (3 Families)
| Font | Role | Weights |
|------|------|---------|
| Sora | Body, UI, CTAs, wordmark | 300-700 |
| DM Mono | Data, labels, metadata | 400-500 |
| Lora | Serif headlines, emotional text | 400, 500 (normal + italic) |

Outfit was DROPPED (near-identical to Sora at UI sizes).

## Component Classes
- `.btn-primary` — bg-accent, text-accent-fg, rounded-xl, Sora semibold
- `.btn-ghost` — transparent bg, ink-200 text, hover bg-stone
- `.btn-secondary` — bg-raised border ink-900
- `.card` — bg-surface, shadow-card, rounded-2xl, p-5
- `.chip` variants — chip-accent, chip-gold, chip-outline
- `.photo-overlay-warm` — `rgba(14,10,6,0.92)` warm-brown (NEVER cool-black)
- `.skel` — shimmer animation with `prefers-reduced-motion` pause
- `.label-mono` — DM Mono, uppercase, tracking-wider, ink-300
- `.section-eyebrow` — DM Mono, uppercase, accent color, letter-spacing 0.08em

## Theme Switching
- Inline `<script>` in `<head>` reads localStorage -> matchMedia fallback
- Cookie set client-side alongside DB save (prevents flash-of-wrong-theme)
- `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }` for no-JS

## Key Files
- `apps/web/app/globals.css` — Token definitions, component classes, theme selectors
- `apps/web/tailwind.config.ts` — Token mapping, font families
- `apps/web/app/layout.tsx` — Font loading, theme script, suppressHydrationWarning
- `apps/web/app/dev/tokens/page.tsx` — Token swatch dev page
