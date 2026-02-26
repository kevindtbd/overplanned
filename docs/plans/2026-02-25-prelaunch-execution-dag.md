# Pre-Launch Execution DAG

*2026-02-25 — Checkpoint after Wave 1 completion*

## Source Document
`docs/plans/2026-02-25-prelaunch-playbook.md` (imported from .docx)

## Three Categories

| Category | Scope | Phases |
|----------|-------|--------|
| **A: Schema + Backend** | Prisma migrations, signal taxonomy, RankingEvent logging, nightly jobs | 0-2 |
| **B: Data Seeding** | Corpus collection, LLM extraction, LLM fallback pipeline, Bend canary | 3-5 |
| **C: UI Signal Capture** | Frontend hooks, viewport tracking, signal wiring | 1 (UI) |

## Execution DAG

```
GATE 0: SA Test Cleanup (6 files)                    <<<< WAVE 1 DONE
    │
    ├── A.WT1: Prisma Migration ──────────────────── WAVE 1 DONE
    │   - candidateSetId, candidate_ids on BehavioralSignal
    │   - behavioralUpdatedAt on ActivityNode
    │   - trainingExtracted, extractedAt on RawEvent
    │   - 7 new columns on RankingEvent
    │   - 4 pre_trip_* SignalType enum values
    │   - extractionMetadata on QualitySignal
    │   - metadata reconciliation on BehavioralSignal
    │
    ├── B.WT1: Scraper Updates ──────────────────── WAVE 1 DONE
    │   - Arctic Shift dynamic city configs (was Japan-only)
    │   - 5 Bend editorial sources added
    │   - is_local detection (6 regex patterns)
    │   - Quality filters (score > 10, upvote_ratio > 0.70)
    │   - 64 tests
    │
    ├── B.WT2: Extraction Enhancements ──────────── WAVE 1 DONE
    │   - FIXED: status='active' bug → IN ('pending','approved')
    │   - Enhanced prompt (overrated_flag, price_signal, author_type)
    │   - tourist_score 3-tier aggregation
    │   - Local 3x weighting in convergence
    │   - vibe_confidence harmonic mean
    │   - Extraction logging to JSONL
    │   - 45 tests
    │
    ├── B.WT3: Canary Tooling ───────────────────── WAVE 1 DONE
    │   - bend_canary_report.py (JSON + terminal)
    │   - check_arctic_shift_availability.py
    │   - 3 new city configs (Tacoma, Nashville, Denver)
    │   - Auto-validation in city_seeder.py
    │   - 57 tests
    │
    ├── C.WT1: Signal Hooks + Wiring ────────────── WAVE 1 DONE
    │   - useSignalEmitter (dual-write, fire-and-forget)
    │   - useCardViewTracker (IntersectionObserver ref)
    │   - signal-hierarchy.ts (training weights)
    │   - SlotCard + trip detail page wired
    │   - 13 tests
    │
    └── C.WT2: ImpressionTracker ────────────────── WAVE 1 DONE
        - 300ms dwell threshold + 1000ms impression threshold
        - getDwellData() / flushDwellData() accumulator
        - Safety caps (100ms min, 60s max)
        - 22 tests
```

## Wave 2 (After A.WT1 merges to main)

```
    ├── A.WT2: Signal Taxonomy + RankingEvent Logging ──── WAVE 2 DONE
    │   - services/api/signals/taxonomy.py (4-tier, 16 types)
    │   - ranking_logger.py: async fire-and-forget RankingEvent writer
    │   - persona_snapshot.py: 5 persona dimensions from signal history
    │   - RankingEvent SA model added to models.py
    │   - 5 new SignalType enum values (slot_confirmed, slot_rejected, etc.)
    │   - 55 tests
    │
    ├── A.WT3: Pre-trip Modification Signals ──────────── WAVE 2 DONE
    │   - getTripPhase() in trip-status.ts
    │   - Move/swap/status/add routes emit phase-aware BehavioralSignal
    │   - Fixed: swap route fire-and-forget (.catch() not void+try/catch)
    │   - 17 tests
    │
    ├── C.WT3: RankingEvent in Generation Pipeline ────── WAVE 2 DONE
    │   - generate-itinerary.ts writes RankingEvent per day in $transaction
    │   - persona-snapshot.ts + weather-context.ts utilities
    │   - One RankingEvent per day with full candidate pool for BPR
    │   - 24 tests
    │
    └── C.WT4: Behavioral Signal Route Enhancements ───── WAVE 2 DONE
        - Allowlist (16 signal types, 400 on unknown)
        - signalValue clamped to [-1.0, 1.0]
        - Per-user rate limiting (120/min, 429 on exceed)
        - Weather context auto-attached from TripLeg
        - 28 tests
```

### Wave 2 Issues Resolved
- **Four-way schema conflict**: All 4 agents stripped Prisma columns they didn't understand.
  Resolved by using main schema as canonical base + additive-only changes.
- **Swap route void+try/catch**: `void` discards the promise so try/catch never fires.
  Fixed to `.catch()` pattern.
- **candidateIds type**: A.WT3 used `String[]`, C.WT4 used `Json?`. Kept `String[]` from main.

## Wave 3 (After Wave 2 + B pipeline fixes merged)

```
    ├── A.WT4: Nightly Jobs
    │   - training_extract.py: mark trainingExtracted, in-batch negatives
    │   - write_back.py: behavioralUpdatedAt + served counts
    │   - persona_updater.py (NEW): EMA, mid-trip 3x weight
    │   DEPENDS ON: A.WT2 (taxonomy)
    │
    ├── BEND CANARY RUN
    │   - python3 -m services.api.pipeline.city_seeder bend -v
    │   - Kevin manual review via bend_canary_report.py
    │   - Fix pipeline if tourist traps surface
    │   DEPENDS ON: B.WT1 + B.WT2 + B.WT3 merged
    │
    └── B.WT4: LLM Fallback Pipeline
        - On-demand city seeding (Google Places + LLM enrichment)
        - DB write-back flywheel
        - Graduation query (monthly)
        DEPENDS ON: Bend canary validated
```

## Key Discoveries from Wave 1

1. **`status = 'active'` was a silent pipeline killer** — vibe extraction found zero nodes every run
2. **ActivityNode already had most write-back columns** from V2 ML waves
3. **RankingEvent table existed but nothing populated it**
4. **SlotCard emitted zero signals** — actions fired status API but no training data
5. **Arctic Shift scraper was hardcoded to Japan only**
6. **Bend canary cost: ~$0.13** (not $130 — Haiku batch pricing is 100x cheaper than estimated)
7. **Pipeline infra was more mature than expected** — 6-step orchestrator, 4 scrapers, entity resolution all wired

## Test Count After Wave 1

- ~278 new tests across all worktrees
- Previous: 1,057 JS + 2,121 Python
- Expected after merge: ~1,100 JS + ~2,400 Python (pending final count)
