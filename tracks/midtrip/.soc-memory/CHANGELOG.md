# Mid-Trip Track — Changelog

## M-007: Prompt Bar — 2026-02-20

### Added
- `apps/web/components/prompt/PromptBar.tsx` — Natural language mid-trip input (200 char cap, Cmd+Enter submit, parse result display)
- `services/api/routers/prompt.py` — POST /prompt endpoint with UUID validation and structured error responses
- `services/api/pivot/prompt_parser.py` — Haiku parsing (claude-haiku-4-5-20251001, 1.5s timeout), keyword fallback, injection screen
- `services/api/pivot/__init__.py` — Pivot subsystem package
- Wired `prompt.router` into `services/api/main.py`

### Security
- Injection screen: 8 pattern classes (delimiters, SQL, script tags, role escalation, hex escapes, JSON role injection)
- User text wrapped in [USER_DATA_START]/[USER_DATA_END] delimiters for Haiku call
- System prompt contains ONLY schema definition — zero world data or persona context
- All inputs logged to `prompt_bar.parse_attempt` RawEvent (metadata only, no raw text)
- Injection attempts logged to `prompt_bar.injection_flagged` with `reviewStatus: pending`

---

## M-008: Trust Recovery — 2026-02-20

### Added
- `apps/web/components/trust/ResolutionPicker.tsx` — Two-path choice UI (wrong-for-me vs wrong-information)
- `apps/web/components/trust/FlagSheet.tsx` — Bottom sheet with ResolutionPicker, submitting states, error handling, FlagTrigger button

### Signal paths
- Wrong-for-me: parallel write of IntentionSignal (source: user_explicit, confidence: 1.0) + BehavioralSignal (signalType: slot_flag_preference, signalValue: -1.0, tripPhase: mid_trip)
- Wrong-information: POST /api/nodes/:activityNodeId/flag → status: flagged, reviewStatus: pending in admin queue

---

## M-009: Mid-Trip Tests — 2026-02-20

### Added
- `services/api/tests/midtrip/__init__.py` — Package declaration
- `services/api/tests/midtrip/conftest.py` — Fixtures: active_trip, weather variants, slot_sequence, day2_slot, pivot_event fixtures, Haiku mock variants, prompt_parser fixtures
- `services/api/tests/midtrip/test_triggers.py` — 18 tests: weather (outdoor/indoor, sunny/rain/storm/drizzle), closure, overrun, mood, MAX_PIVOT_DEPTH enforcement
- `services/api/tests/midtrip/test_cascade.py` — 11 tests: same-day cascade, locked slot exclusion, sequential ordering, cross-day boundary, new PivotEvent for cross-day
- `services/api/tests/midtrip/test_microstops.py` — 15 tests: Haversine accuracy, 200m radius boundary, inactive node exclusion, slot creation shape (flex, 15-30min, proposed)
- `services/api/tests/midtrip/test_prompt_bar.py` — 28 tests: Haiku happy path, timeout fallback, bad JSON fallback, unknown classification, keyword matching (all 5 patterns), injection prevention (6 patterns), truncation, audit logging
- `services/api/tests/midtrip/test_trust.py` — 20 tests: wrong-for-me signals (intention + behavioral), wrong-information node flag, admin queue shape, shared invariants
- `apps/web/__tests__/e2e/midtrip.spec.ts` — E2E: active trip lifecycle, weather trigger, pivot resolution, cascade scope, prompt bar, trust paths, signal verification, injection prevention
