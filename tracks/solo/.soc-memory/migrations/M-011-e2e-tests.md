# M-011: E2E + Integration Tests

## Description
Full test suite for the Solo Trip track.

## Task
1. Unit tests (apps/web/__tests__/solo/):
   - SlotCard rendering with all variants
   - VibeChip display
   - Signal emission on actions
   - DayView navigation
   - MapView pin rendering

2. Integration tests (services/api/tests/solo/):
   - Onboarding → generation → ItinerarySlots created correctly
   - Generation fallback: mock LLM timeout → deterministic fallback fires
   - Generation fallback: mock Qdrant timeout → Postgres fallback
   - Discover feed loads with correct personalization rules

3. E2E tests (apps/web/__tests__/e2e/solo.spec.ts — Playwright):
   - Login → onboard (create trip) → generate → view day view → interact with slots → verify BehavioralSignals in DB
   - Discover → browse → swipe → shortlist → verify RawEvents captured
   - Calendar view → download .ics → verify file parses correctly

4. Cross-track preparation:
   - Verify SlotCard accepts showVoting and showPivot props (even though they're no-ops in Solo)
   - Verify signal emission uses standard format (for Track 6 disambiguation)

Deliverable: all suites green, 30+ tests.

## Output
apps/web/__tests__/e2e/solo.spec.ts

## Zone
tests

## Dependencies
- M-010

## Priority
20

## Target Files
- apps/web/__tests__/solo/SlotCard.test.tsx
- apps/web/__tests__/solo/DayView.test.tsx
- apps/web/__tests__/solo/MapView.test.tsx
- services/api/tests/solo/test_generation.py
- services/api/tests/solo/test_fallbacks.py
- services/api/tests/solo/test_discover.py
- apps/web/__tests__/e2e/solo.spec.ts

## Files
- apps/web/components/slot/SlotCard.tsx
- services/api/generation/engine.py
- docs/plans/vertical-plans-v2.md
