# UI Vertical — Memory Bank

## Sub-topic Files
- `design-system.md` — Tokens, fonts, component patterns, ink scale
- `landing.md` — Landing page, globe, hero, waitlist
- `dashboard.md` — Trip cards, empty state, QuickStartGrid, onboarding params
- `trips.md` — Trip detail, DayView, calendar, map, WelcomeCard, FAB, legs UI
- `settings.md` — Settings page sections, display prefs, notifications, travel interests
- `onboarding.md` — Fork screen, Trip DNA, dates, destination, templates, backfill
- `discover.md` — Discover feed, swipe deck, shortlist
- `groups.md` — Group social (pulse line, energy bars, affinity matrix), voting UI
- `mid-trip.md` — Pivot drawer, swap cards, prompt bar
- `post-trip.md` — Reflection, photo strip, visited map, trip summary, diary
- `admin.md` — Admin layout, model registry, seeding control, node review, safety
- `nav.md` — AppShell, MobileNav, DesktopSidebar, navigation architecture

## Key Patterns
- Single-file components (no separate CSS/JS)
- SVG icons only, no icon libraries, no emoji
- Tailwind with custom token system (see design-system.md)
- `next/dynamic({ ssr: false })` for heavy client components (globe, maps)
- `suppressHydrationWarning` on `<html>` for theme hydration
- Suspense boundary required for `useSearchParams` in Next.js 14
