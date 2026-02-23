# M-005: Add Back Button to Trip Detail

## Description
Trip detail page (`/trip/[id]`) has no way to return to `/dashboard` except browser back. Users are stranded. P1 priority.

## Task
Edit `apps/web/app/trip/[id]/page.tsx`:
- Add a "Back to trips" link in the page header area
- Use `<Link href="/dashboard">` (Next.js Link for client-side navigation)
- Style: inline SVG left arrow icon + "Back to trips" text
- Use design system tokens: `text-ink-400 hover:text-ink-200 transition-colors`
- Font: `font-dm-mono text-[12px] tracking-[0.05em] uppercase`
- Position: above the trip title, left-aligned

Verify: Clicking "Back to trips" navigates to `/dashboard`. The link is visible on both mobile and desktop. Keyboard accessible (focusable, activatable with Enter).

## Output
apps/web/app/trip/[id]/page.tsx

## Zone
ui

## Dependencies
M-004

## Priority
85

## Target Files
- apps/web/app/trip/[id]/page.tsx

## Files
- docs/plans/dashboard-audit-compound.md
