# M-002: Post-Trip Reflection Screen

## Description
Highlight rating per slot with single feedback question.

## Task
1. Per-slot rating: loved / skipped / missed (emoji-free icons)
2. "What would you do differently?" free text
3. Write BehavioralSignal: post_loved, post_skipped, post_missed, post_disliked
4. Post-trip feedback CAN override slot status (completed → skipped if user says they didn't go)

## Output
apps/web/app/trip/[id]/reflection/page.tsx

## Zone
reflection

## Dependencies
- M-001

## Priority
90

## Target Files
- apps/web/app/trip/[id]/reflection/page.tsx
- apps/web/app/trip/[id]/reflection/components/SlotRating.tsx

## Files
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
