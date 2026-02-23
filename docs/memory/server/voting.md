# Server / Voting

## Route
- `app/api/slots/[slotId]/vote/route.ts` — Cast/change vote

## Patterns
- Zod-validated vote payloads
- Quorum logic: 70% yes-only threshold
- Camp detection for conflicting preferences
- Behavioral signal logged on every vote action
- Vote state reset on pivot swap
- 24 tests

## Learnings
- (space for future compound learnings)
