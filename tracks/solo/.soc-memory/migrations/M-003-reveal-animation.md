# M-003: Itinerary Reveal Animation

## Description
Loading state during generation with progressive slot reveal.

## Task
Create apps/web/components/trip/RevealAnimation.tsx:
- Loading state with skeleton cards during generation (poll generation status)
- Progressive reveal: slots appear one by one with staggered animation
- Transition to day view on completion
- Handle error states: generation failed → retry button

Design: warm-surface background, terracotta accent on progress indicators. No emoji.

## Output
apps/web/components/trip/RevealAnimation.tsx

## Zone
ui-components

## Dependencies
- M-002

## Priority
80

## Target Files
- apps/web/components/trip/RevealAnimation.tsx
- apps/web/app/trip/[id]/generating/page.tsx

## Files
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
