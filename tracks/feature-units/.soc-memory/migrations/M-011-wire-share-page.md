# M-011: Wire Shared Trip Page

## Description
Phase 2 UI wiring: Update shared trip page to use new API routes, unwrap response, add import CTA.

## Task

### 1. Update shared trip page (`apps/web/app/s/[token]/page.tsx`)
- Change fetch URL from `${apiBase}/shared/${safeToken}` to internal API URL `/api/shared/${safeToken}`
- **Unwrap response:** Change from `json.success && json.data` to read `json` directly (flat JSON)
- Map response to existing `SharedTripData` interface

### 2. Add Import CTA
- Add an "Import this trip" button below the trip preview
- Button behavior:
  - If user is signed in: POST `/api/shared/${token}/import` -> redirect to new trip
  - If user is not signed in: redirect to sign-in page with callbackUrl back to this page
- Use existing auth check pattern (check session on client or pass auth state from server)
- Style: use `btn-primary` class from design system
- Show loading state during import
- Handle errors: 409 (already imported) -> show "You've already imported this trip" message

### 3. Test
- Verify page renders with new API
- Verify import flow works
- Existing CSP headers still applied

## Output
apps/web/app/s/[token]/page.tsx

## Zone
ui

## Dependencies
M-006

## Priority
60

## Target Files
- apps/web/app/s/[token]/page.tsx
