# M-012: Wire Reflection Page

## Description
Phase 2 UI wiring: Wire reflection page submit handler to new API, remove client-side signal logging.

## Task

### 1. Wire submit handler (`apps/web/app/trip/[id]/reflection/page.tsx`)
- Find the submit handler (currently `console.log`)
- Replace with POST to `/api/trips/${tripId}/reflection`:
  ```typescript
  const response = await fetch(`/api/trips/${tripId}/reflection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ratings, feedback }),
  });
  ```
- On success: show success toast + redirect to trip detail page
- On error: show error message, don't clear form

### 2. Remove client-side signal logging
- Find `sendBehavioralSignal` calls in the reflection page
- Remove them — server now handles all signal logging in the `$transaction`
- Keep the import of `sendBehavioralSignal` ONLY if it's used elsewhere on the page (unlikely)

### 3. Test
- Verify submit handler posts to correct URL
- Verify client-side signal calls are removed
- Page still renders correctly

## Output
apps/web/app/trip/[id]/reflection/page.tsx

## Zone
ui

## Dependencies
M-007

## Priority
60

## Target Files
- apps/web/app/trip/[id]/reflection/page.tsx
