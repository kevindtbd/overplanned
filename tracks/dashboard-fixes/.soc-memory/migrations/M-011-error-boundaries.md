# M-011: Add Error Boundaries

## Description
Zero `error.tsx` files exist in the app. Any runtime error in a dashboard component crashes the entire page with no recovery. P2 priority.

## Task
Create `apps/web/app/dashboard/error.tsx`:
- Must be a Client Component (`"use client"`)
- Accept `error` and `reset` props (Next.js error boundary interface)
- Render the existing `ErrorState` component with `onRetry={() => reset()}`
- Log error to console (Sentry integration is separate)
- Include a "Back to home" link as escape hatch

Create `apps/web/app/trip/[id]/error.tsx`:
- Same pattern as dashboard error boundary
- "Back to trips" link pointing to `/dashboard`

Both error pages should use design system tokens (bg-base, text-ink-100, font-sora headings).

Verify: Throwing an error in a dashboard component shows the error boundary, not a blank page. The "Try again" button calls `reset()`. The back link navigates correctly.

## Output
apps/web/app/dashboard/error.tsx
apps/web/app/trip/[id]/error.tsx

## Zone
ui

## Dependencies
M-006

## Priority
55

## Target Files
- apps/web/app/dashboard/error.tsx
- apps/web/app/trip/[id]/error.tsx
- apps/web/components/states/ErrorState.tsx

## Files
- docs/plans/dashboard-audit-compound.md
