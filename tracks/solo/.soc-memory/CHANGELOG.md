# Solo Trip Track — Changelog

## M-001: Onboarding Flow — 2026-02-20

### Added
- `apps/web/app/onboarding/page.tsx` — Root orchestrator: multi-step wizard with state machine driving each step in sequence, creates Trip + TripMember rows on completion and navigates to the generation loading screen
- `apps/web/app/onboarding/components/ForkScreen.tsx` — Entry fork: "Plan a trip" routes to the wizard, "Just exploring" routes to the discover feed
- `apps/web/app/onboarding/components/DestinationStep.tsx` — Destination picker with autocomplete constrained to 13 launch cities
- `apps/web/app/onboarding/components/DatesStep.tsx` — Date range picker for trip start and end dates
- `apps/web/app/onboarding/components/TripDNAStep.tsx` — Behavioral preference capture: pace (packed/moderate/relaxed), morning preference (early/mid/late), food vibe tag chips; saves as `personaSeed` JSON on the Trip row
- `apps/web/app/onboarding/components/TemplateStep.tsx` — Optional preset selection: Foodie Weekend, Culture Deep Dive, Adventure, Chill; appended to personaSeed

---

## M-002: Itinerary Generation Engine — 2026-02-20

### Added
- `services/api/generation/engine.py` — Core solo generation pipeline: persona-weighted Qdrant query → LLM ranking → slot assignment → ItinerarySlot writes → RawEvent candidate log → ModelRegistry registration; logs model version, prompt version, latency, and cost estimate per LLM call
- `services/api/generation/ranker.py` — LLM ranking step using claude-sonnet-4-6; sends personaSeed + candidate nodes, returns ranked slot list; sets `RANKER_PROMPT_VERSION` for registry
- `services/api/generation/slot_assigner.py` — Slot assignment rules: anchors scheduled first, meals locked to windows (12–1pm lunch, 7–8pm dinner), flex activities fill remaining gaps
- `services/api/generation/fallbacks.py` — Triple fallback cascade: (1) LLM ranking with 5s timeout, (2) deterministic ranking by `convergenceScore × persona_match_score` on LLM timeout, (3) Postgres query by category + city + priceLevel on Qdrant timeout (3s), (4) cached template itinerary when both services are down; sets `Trip.generationMethod`
- `services/api/routers/generate.py` — `POST /generate` endpoint accepting Trip ID; orchestrates engine, handles cascade, returns generation summary

---

## M-003: Itinerary Reveal Animation — 2026-02-20

### Added
- `apps/web/components/trip/RevealAnimation.tsx` — Loading state component: skeleton cards during generation polling, staggered slot reveal animation as each slot becomes ready, transition to day view on completion, retry button on generation failure
- `apps/web/app/trip/[id]/generating/page.tsx` — Generating screen that mounts RevealAnimation and polls generation status until complete or failed

---

## M-004: Day View — 2026-02-20

### Added
- `apps/web/components/trip/DayView.tsx` — Vertical timeline layout for a single day: slot cards arranged with time markers, status indicators (confirmed=green, proposed=amber, completed=grey), timezone-aware time display using `Trip.timezone`, empty state for days with no slots
- `apps/web/components/trip/DayNavigation.tsx` — Day navigation bar: swipe gesture support on mobile, tab row on desktop, highlights current day
- `apps/web/app/trip/[id]/page.tsx` — Main trip view; server component that fetches trip + slots, renders DayNavigation and DayView

---

## M-005: Slot Card Component (Shared) — 2026-02-20

### Added
- `apps/web/components/slot/SlotCard.tsx` — Reusable slot card used across Solo, Group, and Mid-Trip tracks: Unsplash photo (lazy loaded), activity name in Sora, vibe tag chips, time + duration display, booking badge placeholder; accepts `showVoting` and `showPivot` props (no-ops in Solo, wired for downstream tracks)
- `apps/web/components/slot/VibeChips.tsx` — Vibe tag chip strip: DM Mono labels, terracotta accent on primary tag, overflow truncation
- `apps/web/components/slot/SlotActions.tsx` — Confirm / Skip / Lock action buttons with SVG icons; each action writes a BehavioralSignal (signalType, signalValue, userId, tripId, slotId, activityNodeId, tripPhase, rawAction)

---

## M-006: Map View — 2026-02-20

### Added
- `apps/web/components/map/MapView.tsx` — Dual-layout map: desktop sidebar list + map canvas, mobile full-screen map with bottom sheet; pins colored by slot type (dining=red, culture=blue, outdoors=green); day filter shows only current day's slots; reuses SlotCard for pin tap detail popup
- `apps/web/components/map/MapPin.tsx` — SVG map pin component with slot-type color mapping and active/inactive state
- `apps/web/components/map/SlotBottomSheet.tsx` — Mobile bottom sheet that slides up on pin tap, renders SlotCard in detail mode
- `apps/web/app/trip/[id]/map/page.tsx` — Map route: fetches trip + slots, mounts MapView with current-day filter defaulted

---

## M-007: RawEvent Integration — 2026-02-20

### Added
- `apps/web/lib/events/types.ts` — TypeScript types: `RawEvent`, `EventType`, `IntentClass`, `EventBatchRequest`; intent classes: `explicit`, `implicit`, `contextual`
- `apps/web/lib/events/event-emitter.ts` — Singleton EventEmitter service: generates a UUID sessionId on app open, buffers events in memory, auto-flushes every 5 seconds or on navigation, POSTs to `/api/events/batch`; each event stamped with a `clientEventId` UUID for server-side dedup
- `apps/web/lib/events/impressions.ts` — IntersectionObserver-based impression tracker: every card entering the viewport emits an implicit `card_impression` RawEvent with activityNodeId, list position (1-indexed), and dwell time
- `apps/web/lib/events/index.ts` — Barrel export; wires event emitter into day view, map view, and slot detail card surfaces

---

## M-008: Discover / Explore Surface — 2026-02-20

### Added
- `apps/web/app/discover/page.tsx` — Server component: detects cold-start (no behavioral signals) vs returning user, fetches appropriate feed data, renders DiscoverClient
- `apps/web/app/discover/DiscoverClient.tsx` — Client shell: manages tab state between feed, swipe deck, and shortlist; wires event emitter for all surface interactions
- `apps/web/app/discover/components/DiscoverFeed.tsx` — Feed component: cold-start shows trending by convergenceScore + editorial picks by authorityScore + category browsing; returning users get rules-based personalization (boost confirmed categories, demote skipped); every shown item emits a `card_impression` RawEvent with position field
- `apps/web/app/discover/components/SwipeDeck.tsx` — Tinder-style card deck for quick browsing: swipe-right writes `swipe_right` BehavioralSignal, swipe-left writes `swipe_left`
- `apps/web/app/discover/components/Shortlist.tsx` — Saved activity list: add/remove writes `shortlist_add` / `shortlist_remove` BehavioralSignals

---

## M-009: Calendar View + .ics Export — 2026-02-20

### Added
- `apps/web/app/trip/[id]/calendar/page.tsx` — Calendar route server component: fetches trip + slots, renders CalendarClient
- `apps/web/app/trip/[id]/calendar/CalendarClient.tsx` — Month grid view: trip days highlighted, day cells show slot count + first slot name, tap navigates to day view
- `services/api/routers/calendar.py` — `GET /trips/{id}/calendar.ics`: generates iCal file with correct VTIMEZONE (from `Trip.timezone`); each ItinerarySlot becomes a VEVENT with summary (activity name), location (lat/lng), dtstart/dtend, and description; output validates in Apple Calendar and Google Calendar

---

## M-010: Shadow Training Validation Tests — 2026-02-20

### Added
- `services/api/tests/shadow_training/conftest.py` — Fixtures: seeded user, trip, generation run, impression + interaction RawEvents, BehavioralSignals covering all signal types
- `services/api/tests/shadow_training/test_training_data_quality.py` — 7 test groups validating ML training data integrity: positive pairs (slot_confirm, slot_complete, post_loved), explicit negatives (slot_skip, swipe_left, post_disliked), implicit negatives (impression without tap), candidate set completeness (full ranked pool logged, rejected count > selected count), position bias coverage (position field is integer, not null), session sequence ordering (events ordered by timestamp, sessionId consistent), signal integrity (no orphan FKs, required fields present on all signals)

---

## M-011: E2E + Integration Tests — 2026-02-20

### Added
- `apps/web/__tests__/solo/SlotCard.test.tsx` — Unit tests: all SlotCard rendering variants, vibe chip display, signal emission on confirm/skip/lock, showVoting and showPivot prop passthrough (no-ops in Solo, validated for cross-track compatibility)
- `apps/web/__tests__/solo/DayView.test.tsx` — Unit tests: timeline rendering, day navigation (swipe + tab), status indicator colors, empty state, timezone display
- `apps/web/__tests__/solo/MapView.test.tsx` — Unit tests: pin rendering per slot type, day filter, bottom sheet open/close, SlotCard reuse in popup
- `services/api/tests/solo/__init__.py` — Package marker
- `services/api/tests/solo/test_generation.py` — Integration tests: onboarding → generation pipeline produces correctly structured ItinerarySlots with linked ActivityNodes
- `services/api/tests/solo/test_fallbacks.py` — Integration tests: LLM timeout triggers deterministic fallback, Qdrant timeout triggers Postgres fallback; generationMethod field set correctly on each path
- `services/api/tests/solo/test_discover.py` — Integration tests: discover feed loads with correct cold-start vs personalization rules; BehavioralSignal boosts and demotions applied correctly
- `apps/web/__tests__/e2e/solo.spec.ts` — Playwright E2E suite (30+ tests): login → onboard → generate → day view → slot interactions → BehavioralSignal DB verification; discover → browse → swipe → shortlist → RawEvent capture verification; calendar view → .ics download → file parse validation
