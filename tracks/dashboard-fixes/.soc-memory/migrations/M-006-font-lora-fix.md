# M-006: Replace font-lora in Dashboard Components

## Description
Locked design system specifies Sora (headings) + DM Mono (data/labels) ONLY. `font-lora` is used in EmptyState and AppShell TripHero — design system violation. P1 priority. Dashboard scope only (landing/auth pages are a separate pass).

## Task
Edit `apps/web/components/states/EmptyState.tsx`:
- Find `font-lora italic` on the title heading (line ~33)
- Replace with `font-sora`
- Remove `italic` — Sora headings are not italic in the design system

Edit `apps/web/components/layout/AppShell.tsx`:
- Find `font-lora` in the TripHero sub-component (line ~44)
- Replace with `font-sora`
- Remove `italic` if present

Do NOT touch font-lora in other files (landing page, auth pages, slot cards) — those are out of scope for this track.

Verify: Dashboard components render with Sora font on headings. Visual check that the typography feels consistent with the rest of the design system.

## Output
apps/web/components/states/EmptyState.tsx
apps/web/components/layout/AppShell.tsx

## Zone
ui

## Dependencies
none

## Priority
80

## Target Files
- apps/web/components/states/EmptyState.tsx
- apps/web/components/layout/AppShell.tsx

## Files
- docs/plans/dashboard-audit-compound.md
- docs/overplanned-design-v4.html
