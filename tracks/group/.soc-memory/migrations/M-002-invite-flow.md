# M-002: Invite Flow

## Description
InviteToken generation, sharing, and redemption. Requires Google OAuth signup to join.

## Task
1. Organizer creates invite: POST /trips/{id}/invite
   - Generate token: crypto.randomBytes(32).toString('base64url')
   - Default: maxUses=1, expiresAt=7 days, role=member (NEVER organizer via link)

2. Organizer management: GET /trips/{id}/invites
   - List active tokens, usage counts
   - Revoke: PATCH /trips/{id}/invites/{tokenId}/revoke

3. Invite landing page: apps/web/app/invite/[token]/page.tsx
   - Show trip preview (destination, dates, organizer name)
   - "Sign in with Google to join" button
   - If already signed in: "Join this trip" button

4. Redemption: POST /trips/{id}/join?token=xxx
   - Validate: not expired, not revoked, usedCount < maxUses
   - Create TripMember row (role: member)
   - Increment InviteToken.usedCount
   - Reject with identical error for expired/revoked/nonexistent tokens (no information leakage)

## Output
apps/web/app/invite/[token]/page.tsx

## Zone
invite

## Dependencies
- M-001

## Priority
90

## Target Files
- apps/web/app/invite/[token]/page.tsx
- services/api/routers/invites.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
