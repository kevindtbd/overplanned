# Cold Start Orchestration Reference

*Internal Reference -- February 2026*
*Purpose: Wiring diagram for the cold-start system. Maps sources, layers, data flow, gaps, and build priority against the actual codebase. Implementation detail lives in companion docs -- this doc is the index and the integration spec.*

---

## The Seven Sources

Every persona signal entering the system originates from one of these sources. Each has a fixed confidence ceiling, a defined write target, and clear boundaries on what it can and cannot influence.

| # | Source | Provides | When Active | Weight | Write Target | Ranking Eligible |
|---|--------|----------|-------------|--------|-------------|-----------------|
| S1 | Onboarding | Preset seed, tag cloud, scenario cards, trip shape | Account creation | 0.6--1.0x | `persona_dimensions` | No |
| S2 | Destination prior | Weak cluster nudges per city | Trip creation, `confidence < 0.3` only | 0.15x | `persona_dimensions` (soft blend) | No |
| S3 | Backfill | Historical trips: food ratio, pace, local bias, vibe affinities | Post-submission, 2+ trips minimum for aggregate | 0.20--0.65x (by tier) | `BackfillSignal` + `PersonaDelta` + `backfill_persona_aggregates` | No |
| S4 | Synthetic training | LLM-generated behavioral sequences (12 archetypes x 50 users) | Pre-launch, offline only | 0.3x | `BehavioralSignal` (source=synthetic_agent_v1) | No -- persona seed only |
| S5 | In-app behavioral | RankingEvents, pivots, dwell, moment capture, post-trip text | Trip 1 day 1 forward | 1.0x (3.0x post-trip explicit) | `BehavioralSignal` (append-only) -> nightly batch -> `persona_dimensions` | Yes |
| S6 | Collaborative filtering | Nearest-neighbor persona blend from warm user embedding space | 50+ warm users (3+ trips each) | 0.5x blend | `cf_persona_blend` (blended at query time) | No |
| S7 | cant_miss floor | Unconditional inclusion of irreplaceable venues | Always (seeded during city pipeline) | N/A -- floor rule | `ActivityNode.cantMiss` boolean | Overrides suppression |

**Boundary rule:** S1/S2/S3 write to `persona_dimensions` as priors. S5 writes to `BehavioralSignal` (append-only canonical log), then nightly batch updates `persona_dimensions`. S4 writes to `BehavioralSignal` tagged synthetic -- never touches `persona_dimensions` directly. S6 writes to `cf_persona_blend` -- blended at query time, never stored in `persona_dimensions`. S7 is a post-ranking pass, not a persona signal.

---

## The Three Layers

```
LAYER A -- PERSONA PRIORS (pre-trip, slow-changing)
  Table: persona_dimensions
  Sources: S1 (onboarding), S2 (destination prior), S3 (backfill aggregate), S5 (via nightly batch)
  Read by: effective_persona() at trip creation and session start
  Codebase:
    services/api/priors/destination_prior.py .............. S2 -- BUILT (7 cities)
    services/api/simulation/synthetic_runner.py ........... S4 -- PARTIAL (see Gaps)
    services/api/jobs/persona_updater.py .................. S5 nightly -- BUILT (EMA alpha=0.3)
    services/api/pipeline/backfill_pipeline.py ............ S3 ingestion -- BUILT
    [MISSING] backfill_aggregate_computation.py ........... S3 cross-trip patterns -- GAP

LAYER B -- REAL-TIME ADJUSTMENT (in-trip, session-scoped)
  Stores: SessionPersonaDelta (Redis, ephemeral), TripPersonaCache (Redis, trip-scoped)
  Sources: S5 real-time signals
  Read by: RankingOrchestrator for every in-trip LLM call
  Codebase:
    apps/web/lib/hooks/useSignalEmitter.ts ............... Frontend signal emission -- BUILT
    apps/web/lib/hooks/useCardViewTracker.ts .............. Card view tracking -- BUILT
    apps/web/lib/events/impressions.ts ................... ImpressionTracker -- BUILT
    apps/web/lib/events/signal-hierarchy.ts .............. Signal priority -- BUILT
    [MISSING] SessionPersonaDelta ........................ Redis real-time accumulator -- GAP
    [MISSING] TripPersonaCache ........................... Redis warm cache -- GAP

LAYER C -- BETWEEN-TRIP LEARNING (post-trip, injected into Trip N+1)
  Store: TripContextSummary (JSONB), trip_context_history table
  Sources: S5 post-trip batch computation
  Read by: LLM prompt builder for next trip generation
  Codebase:
    [MISSING] TripContextSummary compute job ............. GAP
    [MISSING] trip_context_history table ................. GAP

LAYER D -- SCORE FLOOR (unconditional inclusion)
  Store: ActivityNode.cantMiss boolean
  Sources: S7 -- manual curation during seeding
  Read by: Post-ranking pass in candidate selection
  Codebase:
    [MISSING] cantMiss column on ActivityNode ............ GAP (schema)
    [MISSING] apply_cant_miss_floor() .................... GAP (ranker logic)
    docs/overplanned-vibe-vocabulary.md .................. iconic-worth-it tag -- BUILT
    services/api/pipeline/vibe_extraction.py ............. Extraction signals -- BUILT
```

---

## `effective_persona()` -- The Single Entry Point

The `RankingOrchestrator` never reads `persona_dimensions` directly. All persona reads go through one function:

```python
def effective_persona(user_id: str, trip_id: str | None = None) -> PersonaSnapshot:
    """
    Priority stack (highest wins):
      1. TripPersonaCache  -- if trip active and cache version matches persona_dimensions.version
      2. persona_dimensions -- base priors + nightly batch updates
      3. cf_persona_blend   -- blended at 0.5x (if >=5 neighbors, >=50 warm users)
      4. destination_prior  -- blended at 0.15x (only dimensions with confidence < 0.3)

    Negative tag affinities applied at Qdrant query time (exclusion weights).
    cant_miss floor applied post-ranking (Layer D), not here.
    """
```

**Codebase location:** Not yet built as a unified function. Currently persona reads happen inline in generation code. This function is the integration point.

---

## cant_miss + iconic-worth-it: How They Relate

Two separate mechanisms serving the same product principle ("some things cannot be suppressed"):

| Mechanism | Type | Where | Effect |
|-----------|------|-------|--------|
| `iconic-worth-it` | Vibe tag (44-tag controlled vocab) | `ActivityNode.vibeTags[]` | User-facing signal. Extraction from "worth the hype", "crowded for a reason". Influences Qdrant vector similarity. Can appear alongside other tags. Contradicts `hidden-gem` (flagged for review). |
| `cantMiss` | Boolean column on ActivityNode | `ActivityNode.cantMiss` | Ranker floor rule. Score cannot drop below 0.72. Persona still affects timing/presentation but cannot suppress inclusion. Set manually during seeding. ~0.1% of nodes. |

**Seeding criteria for `cantMiss = true` (both must be true):**
1. The experience is genuinely irreplaceable -- cannot be seen/done anywhere else on earth
2. Local reviewers (city subreddits, Spotted by Locals, local editorial) still endorse it

**`iconic-worth-it` without `cantMiss`:** A place that's worth the crowds but isn't irreplaceable. Most tourist-popular venues. Persona can still suppress these.

**`cantMiss` without `iconic-worth-it`:** Shouldn't happen. If it's cant_miss, it's by definition iconic. Flag for review if a node has `cantMiss=true` but no `iconic-worth-it` tag.

---

## Negative Space Architecture

Every positive signal type needs a negative counterpart. Current parity status:

| Positive Signal | Negative Counterpart | Status | Codebase |
|----------------|---------------------|--------|----------|
| `vibe_select` | Tags displayed but not selected | **GAP** -- displayed set not logged | apps/web/app/onboarding/ |
| `preset_selected` (implicit) | `preset_hovered`, `preset_all_skipped` | **GAP** -- not in SignalType enum | -- |
| `card_viewed` -> accepted | `card_dismissed` + reason taxonomy | **PARTIAL** -- `card_dismissed` exists, reason missing | apps/web/lib/hooks/useSignalEmitter.ts |
| `pivot_accepted` | `pivot_drawer_opened_no_selection` | **GAP** -- not a distinct signal type | -- |
| `slot_confirm` | `slot_skip` + 4-way reason | **PARTIAL** -- binary today | -- |
| `discover_swipe_right` | `destination_card_scrolled_past` | **GAP** | -- |
| Search result selected | `zero_results`, `all_results_rejected` | **GAP** -- `search_events` table doesn't exist | -- |
| Positive tag affinity (implicit) | `negative_tag_affinities` JSONB on persona | **GAP** -- column doesn't exist | -- |

All **GAP** items require schema additions (SignalType enum values, new columns, or new tables) before the negative signal can be captured. The ML logic to consume them can follow.

---

## Signal Weight Transitions

Signal weight varies by source confidence AND by trip phase. This table governs the `signal_weight` value written to `BehavioralSignal`:

| Context | Weight | Rationale |
|---------|--------|-----------|
| Pre-trip planning interactions | 0.4x | Stated preference, no commitment yet |
| Active trip day 1 | 0.6x | First-day calibration noise |
| Active trip day 2--4 | 1.0x | Behavioral ground truth |
| Active trip day 5+ | 0.6--0.7x | Fatigue distortion |
| Post-trip explicit text | 3.0x | Deliberate retrospective signal |
| Backfill tier 2 (structured import) | 0.65x | Confirmed but no counterfactual |
| Backfill tier 3 (annotated free-form) | 0.40x | Less reliable extraction |
| Backfill tier 4 (bare free-form) | 0.20x | Lowest confidence |
| Synthetic (source=synthetic_agent_v1) | 0.3x | LLM-generated prior only |
| Destination prior | 0.15x | Weak population-level nudge |
| Anonymous browse (pre-account) | 0.3x | Aspiration signal, no commitment |

**Earn-out schedule:**
- Synthetic signals: excluded from persona training at 500 real users
- Backfill aggregate: halved at 3 completed in-app trips, residual at 7
- Destination priors: stop applying when `persona_confidence >= 0.3`
- CF blend: only applied to cold users (< 3 trips)

---

## Off-Riff City Discovery Pipeline

When a user requests a city outside the seeded corpus (10 cities in `city_configs.py`), the system needs a path from stub nodes to ML-capable data.

```
User requests unseeded city
         |
         v
LLM fallback fires (llm_fallback_seeder.py)
  -> Writes ~30-50 stub ActivityNodes (vibe_confidence < 0.5)
  -> [MUST] Write raw Places data to GCS (gs://overplanned-raw/places/{city}.jsonl)
  -> Increment city_demand_queue
         |
         v
city_demand_queue accumulates
  -> Tracks: request_count, unique_user_count, behavioral_hits, node_count
         |
    +----+----+----+
    |         |         |
    v         v         v
  3 users   10 users   50 nodes +
             OR 20      10 requests
             hits
    |         |         |
    v         v         v
  Reddit/   Spot       Full Tier 1
  blog      extraction  graduation
  scrape    (top 15     (complete
  begins    nodes)      extraction +
                        embeddings +
                        cross-ref)
```

**Codebase status:**
- `llm_fallback_seeder.py` -- BUILT (creates nodes from unlinked QualitySignals)
- `generation/fallbacks.py` -- BUILT (4-tier generation cascade)
- `city_demand_queue` table -- **GAP**
- Demand-triggered spot extraction -- **GAP**
- GCS raw data write -- **NEEDS VERIFICATION** (check if `llm_fallback_seeder.py` writes to GCS before LLM extraction)

---

## The Warm Cache Architecture

Three distinct concepts that the phrase "micro trip adjustment" conflates:

```
App Open (Trip Active)
    |
    v
Read TripPersonaCache (Redis, trip-scoped)
    |
    +-- Cache miss -> read persona_dimensions from DB (cold session)
    +-- Version stale -> refresh from persona_dimensions, rebuild cache
    |
    v
SessionPersonaDelta (Redis, session-scoped, ephemeral)
    |
    v
[User interactions: accepts, skips, pivots, check-ins]
    |
    v
App Close / Session Timeout (30 min idle)
    |
    +-- Write session delta -> TripPersonaCache (persists to next open)
    +-- Log all signals -> BehavioralSignal (append-only, canonical)

Nightly Batch (3:00-3:30am UTC)
    +-- training_extract.py .... 3:00am -- extract to Parquet
    +-- write_back.py .......... 3:15am -- aggregate to ActivityNode
    +-- persona_updater.py ..... 3:30am -- EMA update persona_dimensions
    +-- [future] Increment persona_dimensions.version
    +-- [future] Invalidate TripPersonaCache if version changed
    +-- [future] For completed trips: compute TripContextSummary
```

**All three layers are currently GAP.** The nightly batch exists (`persona_updater.py`), but the real-time session delta and warm cache do not.

---

## Source Registry Additions (from Activity Dogma doc)

Three highest-priority non-food source integrations, ranked by implementation ROI:

| Priority | Source | Authority | Category | Analog | Status |
|----------|--------|-----------|----------|--------|--------|
| 1 | Resident Advisor (ra.co) | 0.91 | Nightlife/Electronic | Tabelog for nightlife | **GAP** -- not in scrapers/ |
| 2 | Atlas Obscura | 0.82 | Culture/History | Direct ActivityNode feed | **PARTIAL** -- `scrapers/atlas_obscura.py` exists, Tier 2. Elevate to Tier 1. |
| 3 | Spotted by Locals | 0.86 | Neighborhood/Arts | Resident-written city guides | **GAP** -- not in scrapers/ |

**Existing scrapers:**
- `scrapers/arctic_shift.py` -- Reddit (Parquet dumps) -- BUILT
- `scrapers/blog_rss.py` -- Editorial RSS -- BUILT
- `scrapers/atlas_obscura.py` -- Atlas Obscura -- BUILT (Tier 2)
- `scrapers/foursquare.py` -- Foursquare/Google Places -- BUILT

**Source philosophy (from dogma doc, non-negotiable):**
- Local signal beats aggregate signal
- Affiliate content (>20% link density) excluded regardless of volume
- Reddit recommendation = highest-quality discovery signal
- Local/tourist divergence = the overrated detector
- `cant_miss` applies to ~0.1% of nodes only

---

## Consolidated Gap List

### Launch Blockers

| # | Gap | Type | Spec Doc | Codebase Touch |
|---|-----|------|----------|----------------|
| L1 | `SessionPersonaDelta` in Redis | New code | scaffold 3.1, deepdive Concept A | New: `services/api/realtime/session_delta.py` |
| L2 | `TripPersonaCache` in Redis | New code | deepdive Concept B | New: `services/api/realtime/trip_cache.py` |
| L3 | `negative_tag_affinities` JSONB on PersonaDimension | Schema | scaffold 3.5 | `schema.prisma` + migration |
| L4 | Preset hover/negative space signals | Schema + frontend | scaffold 1.1 | SignalType enum + onboarding components |
| L5 | Tag cloud displayed set capture | Frontend | scaffold 1.2 | Onboarding `tags_displayed` payload |
| L6 | Pre-trip removal reason taxonomy | Schema + backend | scaffold 2.1 | SignalType payload enrichment |
| L7 | `cantMiss` boolean on ActivityNode | Schema + ranker | activity dogma doc | `schema.prisma` + `apply_cant_miss_floor()` |
| L8 | GCS raw data persistence in fallback | Verification | gaps doc Gap 4 | `llm_fallback_seeder.py` |
| L9 | `effective_persona()` unified function | New code | this doc | New: `services/api/persona/effective.py` |

### V2 -- After First Real Trips

| # | Gap | Type | Spec Doc |
|---|-----|------|----------|
| V1 | TripContextSummary compute job | New code + schema | scaffold 4.1 |
| V2 | Backfill aggregate persona computation | New code + schema | gaps doc Gap 1 |
| V3 | CF warm start schema + tables | Schema (tables only pre-launch) | gaps doc Gap 2 |
| V4 | Pivot drawer empty signal type | Schema | scaffold 3.2 |
| V5 | Skipped slot 4-way reason taxonomy | Schema + inference | scaffold 3.3 |
| V6 | Planning mode signal weight (0.4x) | Backend | deepdive Concept C |

### V2 -- Survivable Without at Launch

| # | Gap | Type | Spec Doc |
|---|-----|------|----------|
| S1 | Search events + vocab gap queue | Schema + backend | gaps doc Gap 3 |
| S2 | Discover feed negative space | Frontend + schema | scaffold 2.5 |
| S3 | Dwell calibration (expected_duration_min) | Schema | scaffold 3.4 |
| S4 | Anonymous session capture + merge | Schema + frontend | scaffold 0.1 |
| S5 | Persona confidence ratchet milestones | Backend | scaffold 4.3 |
| S6 | Synthetic Recommendation Agent + metrics | New code | synthetic training doc Steps 5-8 |
| S7 | Archetype variance (instantiate_persona with noise) | New code | synthetic training doc |
| S8 | Resident Advisor scraper | New scraper | activity dogma doc |
| S9 | Spotted by Locals scraper | New scraper | activity dogma doc |
| S10 | `city_demand_queue` + trigger pipeline | Schema + jobs | deepdive Part 1 |

---

## Document Map

| What you need | Where to find it |
|---------------|-----------------|
| Signal capture detail (preset negative space, tag cloud, pivot drawer, search events) | `overplanned-cold-start-scaffold.md` |
| Synthetic agent training (archetypes, two-agent loop, model comparison) | `overplanned-synthetic-agent-training.md` |
| TripPersonaCache + warm cache between app opens | `overplanned-cold-start-deepdive.md` Concept B |
| Off-riff city discovery pipeline + city demand queue | `overplanned-cold-start-deepdive.md` Part 1 |
| Backfill ingestion pipeline (Stages 1-5) | `overplanned-backfill-enrichment.docx` |
| Backfill aggregate persona computation (cross-trip patterns) | `overplanned-cold-start-gaps.md` Gap 1 |
| CF warm start schema + nightly job | `overplanned-cold-start-gaps.md` Gap 2 |
| Search events + vocab gap queue schema | `overplanned-cold-start-gaps.md` Gap 3 |
| GCS raw Places persistence + verification checklist | `overplanned-cold-start-gaps.md` Gap 4 |
| Five-source stack overview + LLM ranker full input example | `overplanned-cold-start-complete.md` |
| cant_miss flag + source registry + recommendation dogmas | `overplanned-activity-dogma.docx` |
| TripContextSummary (between-trip injection) | `overplanned-trip-context-enrichment.docx` |
| Nightly job sequence (extract -> writeback -> persona update) | `overplanned-bootstrap-deepdive.md` Phase 2 |
| Signal quality heuristics (cold user quarantine, dwell calibration) | `overplanned-heuristics-addendum.md` |
| Controlled vibe vocabulary (44 tags, extraction rules) | `overplanned-vibe-vocabulary.md` |
| Model promotion gates (BPR -> two-tower -> LightGCN) | `overplanned-bootstrap-deepdive.md` Phase 4 |

---

## What's Built (Quick Reference)

| Component | File | Status |
|-----------|------|--------|
| Destination prior (7 cities) | `services/api/priors/destination_prior.py` | Built, tested |
| Synthetic runner (12 archetypes, basic loop) | `services/api/simulation/synthetic_runner.py` | Partial -- missing Recommendation Agent |
| Backfill pipeline (5-stage async) | `services/api/pipeline/backfill_pipeline.py` | Built, multi-city |
| Backfill LLM helpers | `services/api/pipeline/backfill_llm.py` | Built (4 LLM functions) |
| Nightly persona updater (EMA) | `services/api/jobs/persona_updater.py` | Built (alpha=0.3, mid-trip 3x) |
| Nightly training extract | `services/api/jobs/training_extract.py` | Built (Parquet export) |
| Nightly write-back | `services/api/jobs/write_back.py` | Built |
| Signal emission hooks | `apps/web/lib/hooks/useSignalEmitter.ts` | Built |
| Card view tracking | `apps/web/lib/hooks/useCardViewTracker.ts` | Built |
| Impression tracker (dual thresholds) | `apps/web/lib/events/impressions.ts` | Built |
| Signal hierarchy | `apps/web/lib/events/signal-hierarchy.ts` | Built |
| RankingEvent (full candidate logging) | `packages/db/prisma/schema.prisma` | Built (candidateSetId, viewDurations, weatherContext, personaSnapshot) |
| 27+ SignalType enum values | `packages/db/prisma/schema.prisma` | Built |
| LLM fallback seeder | `services/api/pipeline/llm_fallback_seeder.py` | Built |
| Generation fallback cascade (4-tier) | `services/api/generation/fallbacks.py` | Built |
| City seeding pipeline (6-stage) | `services/api/pipeline/city_seeder.py` | Built (10 cities) |
| Vibe extraction (44-tag vocab) | `services/api/pipeline/vibe_extraction.py` | Built (iconic-worth-it included) |
| Atlas Obscura scraper | `services/api/scrapers/atlas_obscura.py` | Built (Tier 2) |
| PersonaDelta model | `packages/db/prisma/schema.prisma` | Built |
| BackfillTrip/Leg/Venue/Signal/Photo | `packages/db/prisma/schema.prisma` | Built |

---

*Overplanned Internal -- February 2026*
*Cross-references all companion docs listed in Document Map above.*
*This doc is the integration index. Implementation detail lives in the referenced docs.*
