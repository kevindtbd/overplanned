# M-005: Slot Card Component (SHARED)

## Description
Reusable slot card component used by Solo, Group, and Mid-Trip tracks. This is a critical shared component.

## Task
Create apps/web/components/slot/SlotCard.tsx:
- Photo (Unsplash URL, lazy loaded)
- Activity name (Sora font)
- Vibe tag chips (DM Mono, terracotta accent for primary tag)
- Time + duration display
- Booking badge placeholder (not functional yet)

Actions (configurable per context):
- Confirm / Skip / Lock buttons
- Each action writes a BehavioralSignal:
  - confirm → signalType: "slot_confirm", signalValue: "confirmed"
  - skip → signalType: "slot_skip", signalValue: "skipped"
  - lock → signalType: "slot_lock", signalValue: "locked"
- Signal includes: userId, tripId, slotId, activityNodeId, tripPhase, rawAction

Props interface designed for reuse:
- slot: ItinerarySlot (with ActivityNode populated)
- onAction: (action, slotId) => void
- showVoting?: boolean (Track 4)
- showPivot?: boolean (Track 5)
- showFlag?: boolean (Track 5)

No emoji. SVG icons for action buttons.

## Output
apps/web/components/slot/SlotCard.tsx

## Zone
ui-components

## Dependencies
- M-004

## Priority
70

## Target Files
- apps/web/components/slot/SlotCard.tsx
- apps/web/components/slot/VibeChips.tsx
- apps/web/components/slot/SlotActions.tsx

## Files
- docs/overplanned-design-v4.html
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
