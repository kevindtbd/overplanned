# Server / Sharing

## Routes
- `app/api/trips/[id]/share/route.ts` — Create share token
- `app/api/shared/[token]/route.ts` — Public shared trip view
- `app/api/shared/[token]/import/route.ts` — Import/clone shared trip

## Patterns
- Import clones Trip + Legs + Slots with fresh UUIDs
- Read-only public view with commercial protection
- 28 tests

## Learnings
- (space for future compound learnings)
