# Training Data Pipeline — Learnings

## Persona Seed JSON: Watch for Legacy Values
The Trip.personaSeed JSON has values from BOTH the old 6-archetype seeder
and the new cartesian seeder. When materializing into structured tables:
- `social_mode`: can be composite (`solo_or_couple`, `solo_or_group`, etc.)
- `pace`: can be raw (`slow`) or labeled (`leisurely`)
- `budget_tier`: can be `flexible` (old) instead of `low/mid/high`
Always build reverse-mapping dicts with fallback defaults.

## Schema Changes: Always Brainstorm + Deepen First
User enforced this twice — once when I tried to `prisma db push` without
brainstorming, once when I started coding enrichments without the workflow.
Non-negotiable: brainstorm → deepen → agent review → code.

## Affinity Reconstruction is Lossy
The persona seeder applies per-user jitter (+/-0.05) at runtime but never
persists the jittered values. When reconstructing affinities from
PersonaDimension labels, you get the base vector (no jitter). This is a
documented known limitation — acceptable for bootstrap, not for production.
Fix: store jittered vector as `category_affinities` PersonaDimension row.

## Agent Review Findings (Patterns to Reuse)
- **Data scientist caught exploration_radius redundancy** — deterministically
  derived from pace, zero independent info. Always check for derived dimensions.
- **Backend architect caught missing ItinerarySlot index** — the seeder
  queries slots by tripId+dayNumber heavily. Always check indexes for
  seeder query patterns, not just app query patterns.
- **Security auditor caught admin auth gap** — pre-existing but real.
  All /admin/* routes lack auth dependency. Out of scope for training data
  but needs fixing before any external access.

## Tokyo Data Quality
Only 20 nodes. Every user sees the same 20 candidates with top-20 selection.
Item embeddings will overfit. Exclude Tokyo from BPR training or weight
NYC/CDMX examples more heavily until Tokyo catalog > 50 nodes.

## Enrichment Patterns (Phase 2 Learnings)

### Data-driven expectations beat design estimates
- Design said ~280 abandoned trips, reality was 13 — almost all trips had
  post_trip signals. Always query the actual data distribution before setting
  targets. The filter (no post_trip signals) was correct; the estimate was wrong.
- IntentionSignals came in at 2,864 vs ~3,100 estimate — per-user capping
  naturally reduces count below the naive 25% calculation.

### Batch INSERT via executemany for high-volume enrichments
- Discovery signals (13K+) use `conn.executemany()` instead of per-row inserts.
  Massive perf difference. Always batch when inserting >1K rows.

### Weather UPDATE batching by value, not by row
- Group signal IDs by weather string, then UPDATE WHERE id = ANY($1).
  Turns 43K individual UPDATEs into ~12 batched UPDATEs. Pattern: when
  updating a column to one of N known values, batch by value.

### Conditional weighted random with guard clauses
- IntentionSignal types have conditional eligibility (group_conflict only
  for group users, price_mismatch only for expensive+low-budget). Pattern:
  start with base weights dict, conditionally redistribute ineligible weights
  to fallback category, then random.choices().

### Per-user noise prevents echo chamber
- Discovery swipes use +-15% per-user jitter on affinity thresholds (seeded
  from user index for determinism). Without this, discovery signals perfectly
  echo itinerary confirms — useless for BPR learning separate contexts.

### Idempotency verification matters
- Re-running enrichments confirmed: DELETE+re-INSERT produces identical counts,
  WHERE IS NULL returns 0, check-before-write skips correctly. Always verify
  idempotency explicitly before calling it done.

## Prisma db push Gotchas
- `prisma db push` from project root may use wrong schema path or env vars
- Always run from `packages/db/` with explicit DATABASE_URL if needed
- `--accept-data-loss` is fine when seeders are idempotent (repopulate after)
- PersonaDimension + RankingEvent tables get dropped/recreated on schema
  changes — not a problem since `seed_training_data()` repopulates them

## The Brainstorm-Deepen-Review Loop (Meta-Pattern)
Across both blocker and enrichment phases, the mandatory workflow caught
issues that would have been bugs or rework:
- **Brainstorm** surfaced format questions (weather pipe-delimited vs JSON,
  discovery signals as BehavioralSignal vs separate table)
- **Deepen** caught data consistency risks (trip status flip without
  checking post_trip signals, swap pair orphans assumption)
- **Agent review** caught performance issues (missing indexes, unbatched
  inserts) and signal quality issues (discovery thresholds too clean,
  missing price_mismatch intention type)
Each phase caught things the others missed. The overhead (~20 min) saved
hours of debugging and rework. Worth it for anything touching >1 table.

## Final Dataset Summary (BPR-Ready)
- 765 shadow users across 300 archetypes (5-axis cartesian)
- 2,801 trips across Tokyo/NYC/CDMX
- 225K+ BehavioralSignals (modelVersion backfilled)
- 14,760 itinerary RankingEvents + 838 discovery RankingEvents
- 6,120 PersonaDimensions (8 dims x 765 users)
- 1,044 PivotEvents, 2,864 IntentionSignals
- 13,643 discovery swipe signals
- 43,595 weather-tagged outdoor/active signals
- Trip status mix: ~2,700 completed, 13 planning, 8 active, 80 shortened
- All idempotent, all admin-endpoint accessible
- Remaining gap: QualitySignal source diversity (#5, not BPR-blocking)

## Key Files
- `services/api/pipeline/persona_seeder.py` — cartesian persona generator
- `services/api/pipeline/city_node_seeder.py` — synthetic city venues
- `services/api/pipeline/training_data_seeder.py` — 3 blockers + enrichments
- `services/api/routers/admin_seeding.py` — admin API endpoints
- `docs/plans/2026-02-20-training-blockers-design.md` — blocker design
- `docs/plans/2026-02-20-training-enrichments-design.md` — enrichment design
- `docs/plans/training-enrichments-review-notes.md` — enrichment review
- `docs/plans/training-data-gaps-second-pass.md` — enrichment backlog (items 1-4,6 done, #5 pending)
