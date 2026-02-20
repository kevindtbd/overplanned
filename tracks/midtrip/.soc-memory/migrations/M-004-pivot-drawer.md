# M-004: Pivot Drawer UI

## Description
Swap card interface for resolving pivot suggestions. Requires Solo slot card.

## Task
1. Drawer showing original slot vs alternatives
2. Accept / reject / let expire actions
3. Write BehavioralSignal: pivot_accepted/rejected/expired
4. Write RawEvent with candidate set (alternatives shown)
5. PivotEvent.responseTimeMs captured
6. Update ItinerarySlot on accept (new activityNodeId, wasSwapped=true, pivotEventId)

## Output
apps/web/components/pivot/PivotDrawer.tsx

## Zone
pivot-ui

## Dependencies
- M-003

## Priority
70

## Target Files
- apps/web/components/pivot/PivotDrawer.tsx
- apps/web/components/pivot/SwapCard.tsx

## Files
- apps/web/components/slot/SlotCard.tsx
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
