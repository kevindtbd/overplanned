# Multi-City Plan — Deepen Review Notes

**Date:** 2026-02-22
**Plan:** docs/plans/2026-02-22-multi-city-trip-design.md

---

## Issues Found & Resolutions

### 1. Dual transit source of truth (CRITICAL)

**Problem:** Transit info was stored in TWO places — `TripLeg.transitMode/transitDurationMin/transitCostHint` AND as a separate `ItinerarySlot` with `SlotType.transit`. The ItinerarySlot schema has no transport-specific fields (no mode, no cost), so transit details would have to be stuffed into the `voteState` JSON blob.

**Resolution:** TripLeg is the sole source of truth for inter-leg transit. Do NOT create a phantom ItinerarySlot for inter-leg transit. The UI renders travel transitions directly from TripLeg fields. `SlotType.transit` remains for intra-city transit between activity slots (taxi to Nishiki) — that's a different concept.

**Action:** Update plan to remove references to creating transit ItinerarySlots between legs.

### 2. Day renumbering on leg reorder (MEDIUM)

**Problem:** If `dayNumber` on ItinerarySlot is the absolute trip day (continuous numbering), reordering legs or adjusting day counts requires bulk-updating every slot in downstream legs.

**Resolution:** Use **leg-relative day numbering**. `dayNumber` = day within this leg (1-indexed). Absolute trip day is computed at read time: `sum(previous legs' day counts) + slot.dayNumber`. Reordering legs = updating `TripLeg.position` only, zero slot mutations.

**Action:** Update plan to specify leg-relative day numbering with API computing absolute days.

### 3. Travel day math hidden from user (MEDIUM)

**Problem:** "10-day trip with 3 legs" actually means ~8 activity days after 2 travel transitions. User could be surprised when days disappear into transit.

**Resolution:** Show both. Day Allocation step displays "10 days total, 8 activity days" with the visual timeline making travel days explicit: `[Tokyo 3d] [travel] [Kyoto 3d] [travel] [Osaka 2d]`. No hidden math.

**Action:** Update Day Allocation step description in plan.

### 4. Unseeded city handling (MEDIUM)

**Problem:** Freeform cities (not in LAUNCH_CITIES) have zero ActivityNodes. Multi-city trips make this more likely (user adds Hakone alongside Tokyo).

**Resolution:** Allow freeform cities. Unseeded legs get **LLM-only generation** — the enrichment path already exists, it becomes the primary generator when ActivityNode count = 0. No blank legs, no artificial restrictions.

**Action:** Update generation engine section to describe LLM-only fallback for unseeded legs.

### 5. Transit distance source (LOW)

**Problem:** Heuristic distance table (< 100km = train, etc.) needs city coordinates, but cities have no canonical lat/lng in the schema.

**Resolution:** Skip distance heuristics. Use **LLM to suggest transit mode** for each city pair. One LLM call per leg transition. Cheap, flexible, handles any city including freeform. If hotel/accommodation coordinates are available later, those refine the suggestion.

**Action:** Replace distance heuristic table with LLM transit suggestion.

### 6. BackfillVenue FK migration (LOW)

**Problem:** Existing BackfillVenues have `backfillTripId` FK. New BackfillLeg model puts venues under legs, not trips. Migration path unclear.

**Resolution:** Clean migration — no production data exists. Move venue FK from `backfillTripId` to `backfillLegId`. Existing venues assigned to auto-created position-0 leg. Drop old FK.

**Action:** Update BackfillLeg section to specify FK migration.

### 7. Phase collapse (PROCESS)

**Problem:** 5 phases for a pre-MVP product is over-cautious. No production data, no backward compat needed.

**Resolution:** Collapse Phases 1-2 (schema + API) into one pass. Keep Phase 3 (UI) separate for visual review. Phase 4 (backfill multi-city) stays separate. Phase 5 (cleanup) becomes unnecessary — we do the clean schema from the start since there's no production data.

**Action:** Update migration plan to 3 phases: Schema+API, UI, Backfill.

---

## Summary

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | Dual transit source of truth | Critical | Resolved — TripLeg only, no phantom slots |
| 2 | Day renumbering on reorder | Medium | Resolved — leg-relative dayNumber |
| 3 | Travel day math transparency | Medium | Resolved — show total + activity days |
| 4 | Unseeded city handling | Medium | Resolved — LLM-only generation fallback |
| 5 | Transit distance source | Low | Resolved — LLM suggests transit mode |
| 6 | BackfillVenue FK migration | Low | Resolved — clean migration, no compat |
| 7 | Phase collapse | Process | Resolved — 3 phases, not 5 |
