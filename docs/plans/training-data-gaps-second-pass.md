# Training Data Gaps — Second Pass

After fixing the 3 blockers (RankingEvent, PersonaDimension, ModelRegistry),
these quality improvements were addressed before BPR training.

**Status: 5/6 complete (commit 0fd5f6b). Only #5 remains.**

## 1. PivotEvent Records — DONE

1,044 PivotEvent rows created from existing swap slot pairs.
Design: `docs/plans/2026-02-20-training-enrichments-design.md` (Enrichment 1)

## 2. IntentionSignal Seeding — DONE

2,864 IntentionSignal rows for ~25% of slot_skip signals (per-user capped).
Weighted types: not_interested (32%), bad_timing (17%), too_far (15%),
already_visited (10%), weather (10%, 2x for outdoor), price_mismatch (8%),
group_conflict (5%).
Design: Enrichment 2 in design doc.

## 3. Discovery Swipe Signals — DONE

13,643 swipe signals + 838 RankingEvents (surface='discovery') for ~30% of users.
Thresholds: 65%/40%/8% with +-15% per-user noise to prevent echo chamber.
Design: Enrichment 3 in design doc.

## 4. WeatherContext on Outdoor/Active Signals — DONE

43,595 signals updated with pipe-delimited `label|temp_c|precip_index` format.
Only signals with slotId (slot-level decisions). Join through ItinerarySlot -> Trip.
Design: Enrichment 4 in design doc.

## 5. QualitySignal Source Diversity — PENDING

Not a BPR blocker. Needed for convergence/authority scoring pipeline.
Audit QualitySignal rows per city first — may be empty or single-source.

## 6. Trip Completion Realism — DONE

13 trips flipped to 'planning' (only those with NO post_trip signals).
80 trips shortened to 2-3 days. Cosmetic for current BPR but future-proofs
User Tower features.
Design: Enrichment 6 in design doc.
