# M-007: RawEvent Integration

## Description
Frontend event emitter that captures all user interactions as RawEvents. Must be wired BEFORE discover surface.

## Task
Create apps/web/lib/events/:

1. EventEmitter service (event-emitter.ts):
   - Generate sessionId (UUID) on app open, persist for session
   - Buffer events in memory
   - Flush every 5 seconds or on navigation (whichever comes first)
   - POST to /events/batch endpoint
   - clientEventId: UUID generated on device for dedup

2. Impression tracking (impressions.ts):
   - IntersectionObserver: every card entering viewport = implicit RawEvent
   - Track: which activityNodeId, position in list, viewport duration (dwell time)

3. Event types captured:
   - Impressions: card_impression (implicit)
   - Interactions: card_tap, slot_confirm, slot_skip, slot_lock (explicit)
   - Navigation: screen_view, tab_switch, scroll_depth (contextual)
   - Dwell: card_dwell (time spent looking at a card)

4. intentClass tagging:
   - explicit: user took deliberate action (tap, confirm, skip)
   - implicit: passive observation (impression, scroll, dwell)
   - contextual: navigation context (screen_view, tab_switch)

5. All surfaces emit: day view, map view, slot detail card

6. Over-log principle: emit EVERYTHING. Backend decides importance via RawEvent → BehavioralSignal promotion (Month 5+).

## Output
apps/web/lib/events/event-emitter.ts

## Zone
event-capture

## Dependencies
- M-006

## Priority
60

## Target Files
- apps/web/lib/events/event-emitter.ts
- apps/web/lib/events/impressions.ts
- apps/web/lib/events/types.ts
- apps/web/lib/events/index.ts

## Files
- docs/plans/vertical-plans-v2.md
