# Server / Invites

## Routes
- `app/api/invites/preview/[token]/route.ts` — Public invite preview (no auth)
- `app/api/trips/[id]/join/route.ts` — Join trip via invite
- `app/api/trips/[id]/invite/route.ts` — Create invite link

## Patterns
- TOCTOU prevention: atomic SQL for join (check + insert in single query)
- 256-bit secure tokens
- No-account join supported (pending member until auth)
- 35 tests covering the flow

## Learnings
- (space for future compound learnings)
