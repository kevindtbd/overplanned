# Server / Slots

## Routes
- `app/api/trips/[id]/slots/route.ts` — Trip slots list
- `app/api/slots/[slotId]/swap/route.ts` — Swap slot activity
- `app/api/slots/[slotId]/status/route.ts` — Update slot status
- `app/api/slots/[slotId]/move/route.ts` — Move slot to different time/day
- `app/api/slots/[slotId]/vote/route.ts` — Vote on slot

## Key Libraries
- `lib/validations/slot.ts` — Slot Zod schemas

## Patterns
- ItinerarySlot gained tripLegId FK (multi-city)
- ownerTip on ItinerarySlot (separated from voteState per architect review)
- Slot move supports cross-day and time changes

## Learnings
- (space for future compound learnings)
