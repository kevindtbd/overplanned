# M-010: Wire Invite Page

## Description
Phase 2 UI wiring: Update invite page to use new API routes and unwrap response.

## Task

### 1. Update invite page (`apps/web/app/invite/[token]/page.tsx`)
- Change fetch URL from `${apiBase}/invites/preview/${token}` to `/api/invites/preview/${token}`
  - Note: this is a server component, so use the full internal URL: `${process.env.NEXTAUTH_URL || "http://localhost:3000"}/api/invites/preview/${token}`
- **Unwrap response:** Change from `json.data` to read `json` directly (flat JSON, no wrapper)
  - Find the line that reads `json.success && json.data` and change to read fields directly from `json`
  - Map response fields to existing `InvitePreview` interface
- Verify the page renders correctly with the new API

### 2. Verify InviteJoinButton is already correct
- `InviteJoinButton.tsx` already calls `POST /api/trips/${tripId}/join?token=${token}` — NO changes needed
- Just verify it still works with the new backend route

### 3. Test
- Manual verification that invite page loads with valid token
- Existing tests still pass

## Output
apps/web/app/invite/[token]/page.tsx

## Zone
ui

## Dependencies
M-004

## Priority
60

## Target Files
- apps/web/app/invite/[token]/page.tsx
