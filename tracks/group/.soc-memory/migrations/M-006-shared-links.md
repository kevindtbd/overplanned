# M-006: Shared Trip Links

## Description
Public read-only itinerary view via SharedTripToken with security hardening.

## Task
1. SharedTripToken generation: crypto.randomBytes(32), base64url, 90-day default expiry
2. Public page: apps/web/app/s/[token]/page.tsx — read-only itinerary, no auth required
3. Rate limit: 30/min per IP
4. Identical 404 for nonexistent and revoked tokens (no information leakage)
5. XSS prevention: HTML entity encoding on all user-provided content (owner tips, display names)
6. CSP on shared pages: script-src 'none'
7. Commercial protection: no affiliate links, no booking redirects

## Output
apps/web/app/s/[token]/page.tsx

## Zone
sharing

## Dependencies
- M-001

## Priority
50

## Target Files
- apps/web/app/s/[token]/page.tsx
- services/api/routers/shared_trips.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
