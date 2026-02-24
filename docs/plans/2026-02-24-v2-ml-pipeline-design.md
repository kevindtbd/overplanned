# V2 ML Pipeline — Implementation Design

## Date: 2026-02-24
## Status: Reviewed (architect + security + test engineer), ready for execution

---

## Scope

32 features across 8 phases. All BUILD NOW, staged for GCP Cloud Run deployment. 2 features DATA-GATED (learned arbitration at 1,500+ events, GPS at v2 mobile).

Source docs: `docs/overplanned-v2-ml-model/` (12 files)
Execution pipeline: `memory/ml/v2-ml-execution-pipeline.md`

---

## Decisions Made

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Synthetic signal storage | `source` column on BehavioralSignal | Single table, quarantine via WHERE clause at extraction time |
| 2 | SlotCompletionSignal storage | Nullable enum column on ItinerarySlot | Slot owns its outcome state, no JOIN needed |
| 3 | Write-back job data access | Use existing columns (`activityNodeId`, `modelVersion`) | No JSONB bag, structured signal philosophy |
| 4 | Subflow priority order | `first_creation_rejection > itinerary_alteration_* > group_split > repeat_city > group_ranking > hllm_rerank > offline_pivot > onthefly_add > core_ranking` | Rarest/most diagnostic subflow wins |
| 5 | `card_dismissed` handling | Fold into `slot_skip` | Same negative signal for write-back purposes, split later if data warrants |
| 6 | `corpus_ingestion_request` table | Add in Phase 0.1 migration | Lightweight (5 cols), captures user-sourced venue signals from day one |
| 7 | Disambiguation weight semantics | Sample weight (`signal_weight: 0.7`), not label value | `signalValue` = what happened, `signal_weight` = how much we trust it |
| 8 | `behavioral_quality_score` default | 0.5 via Laplace smoothing (not NULL) | No null branching in scoring path, impression_count < 10 gates DLRM trust |
| 9 | `signal_weight` ownership | Server-side only, never from client | Security FAIL if client can inject weights; DB CHECK constraint enforced |
| 10 | `completionSignal` type | Prisma enum, not raw String | Matches existing schema convention (SlotStatus, SlotType, SignalType) |
| 11 | Exploration budget assignment | Phase 6 prerequisite, not earlier | Feedback loop only closes when ML models produce rankings |
| 12 | BPR contingency gate | Hybrid: automated detection, manual decision | Eval harness flags, human confirms skip, 7-day staleness alert |
| 13 | Timeline semantics | Build order, not calendar | Waves define dependency + parallelism, not deadlines |

---

## GPU Policy — NO GPU REQUIRED

**SASRec and all Phase 6 models train on CPU. Period.**

At Overplanned's data scale (5K-50K items, 10K-100K sequences, ~500K parameter model), CPU training completes in minutes. Do NOT provision T4/A100/any GPU instance. Do NOT add GPU to Docker Compose. Do NOT create Vertex AI custom training jobs. Do NOT request GCP GPU quota.

Everything trains in the same Cloud Run / Docker Compose environment that serves inference.

**Revisit trigger (ALL must be true):**
- 500K+ training sequences
- Single training epoch exceeds 30 minutes on CPU
- You have benchmarked CPU vs GPU and the speedup justifies the $0.35/hr+ cost

Until all three are true, the answer is no GPU. If someone asks "should we get a GPU for training?" — the answer is no. If a tutorial says "SASRec requires GPU" — it's written for Meta-scale, not ours. If a PR adds a `cuda()` call — reject it.

---

## Execution Strategy — Waves + Worktrees

### Wave A (week 1): Phase 0.1 Migration — Universal Blocker

Direct to main. Single Prisma migration.

**New tables:**
- `ArbitrationEvent` — user_id, trip_id, ml_top3, llm_top3, arbitration_rule, served_source, accepted, agreement_score, context_snapshot JSONB. **CHECK: `pg_column_size(context_snapshot) < 65536`** (64KB cap). Validate via Pydantic schema with known fields only (persona_vibes, ml_scores, llm_scores — no raw user text).
- `ImportJob` — user_id, status, parser_version, conversations_found, travel_conversations, signals_extracted
- `ImportPreferenceSignal` — import_job_id, dimension, direction, confidence, source_text (max 500 chars), `pii_scrubbed Boolean @default(false)`, `source_text_expires_at DateTime?` (set to created_at + 90 days). **PII regex scrub** (phone, email, SSN patterns) runs before persistence. source_text NULLed after 90-day retention window.
- `CorpusIngestionRequest` — user_id, trip_id, raw_place_name, source, status
- `WriteBackRun` — date, status, rows_updated, duration_ms. Audit log for write-back job idempotency tracking.

**New columns on existing models:**
- `ActivityNode`: `tourist_score Float?`, `tourist_local_divergence Float?`, `impression_count Int @default(0)`, `acceptance_count Int @default(0)`, `behavioral_quality_score Float @default(0.5)`, `llm_served_count Int @default(0)`, `ml_served_count Int @default(0)`
- `BehavioralSignal`: `subflow String?`, `signal_weight Float @default(1.0)`, `source String @default("user_behavioral")`
- `ItinerarySlot`: `completionSignal SlotCompletionSignal?` (Prisma enum per Decision #10, not raw String)

**New enum:**
- `SlotCompletionSignal`: confirmed_attended, likely_attended, confirmed_skipped, pivot_replaced, no_show_ambiguous

**New indexes:**
- `BehavioralSignal`: compound `@@index([userId, tripId, signalType, source])` (replaces existing `@@index([userId, tripId, signalType])`). The `source` column is heavily filtered in WHERE clauses (synthetic quarantine, rejection recovery, training extraction).

**New CHECK constraints:**
- `BehavioralSignal.signal_weight`: `>= -1.0 AND <= 3.0` (bounds damage from any bug)
- `ArbitrationEvent.context_snapshot`: `pg_column_size < 65536`

**Security invariant — signal_weight is SERVER-ONLY:**
`signal_weight` must NEVER be accepted from client input. The column is set exclusively by server-side middleware (subflow tagger, alteration detector, off-plan signal handler). The `BehavioralSignal` creation Pydantic model must exclude `signal_weight` from any client-facing schema. Per-user per-venue dedup for weight-sensitive signal types: max 1 `user_added_off_plan` per venue per trip.

**Test factory updates (Wave A deliverable):**
Update `make_activity_node()`, `make_behavioral_signal()`, `make_itinerary_slot()` with V2 column defaults. Create new factories: `make_arbitration_event()`, `make_import_job()`, `make_import_preference_signal()`, `make_corpus_ingestion_request()`.

No data backfill in the migration. All defaults are safe for existing rows.

---

### Wave B (weeks 1-2, parallel worktrees)

```
worktree: ml/signal-quality    → Phase 1.1-1.4
worktree: ml/city-seeding-v2   → Phase 7.1 + Arctic Shift US expansion
```

Zero file overlap. B1 is Python signal code, B2 is pipeline config + scraper expansion.

**B1: Signal Quality (Phase 1.1-1.4)**

Build order:
1. **1.1 Slot outcome classifier** — Pure function on trip completion. 5 states, static training weight dict. Hook into existing `completion.py`.
2. **1.2 Subflow tagging** — Middleware on BehavioralSignal write. Priority-ordered context check. Backfill job for existing signals.
3. **1.3 Alteration tagging** — Session-grouped swap analysis. 30-min windows, category shift detection (2+ same-category removals). 1.3-1.4x weights.
4. **1.4 Off-plan signal** — `user_added_off_plan` at 1.4x weight. Entity resolution (exact + fuzzy). Unmatched → `CorpusIngestionRequest`.

**B2: City Seeding (Phase 7.1)**

**PRE-FLIGHT (before writing any B2 code):** Verify Arctic Shift Parquet data availability for all 7 starter cities. If unavailable, identify cheapest paid Reddit data source. This is a go/no-go gate — 10 minutes of checking saves weeks of wasted work.

Blockers to fix first:
1. Expand Arctic Shift scraper `TARGET_CITIES` for all 7 US cities (subreddit lists, neighborhood terms, venue stopwords, Spanish character handling)
2. Download US city Parquet dumps from Arctic Shift (or paid alternative per pre-flight)
3. Add Spanish suffixes to entity resolution strip list
4. Run city_seeder: 1-2 cities/day (Foursquare quota). Bend first as canary. Mexico City = augment.
5. Validate per-city quality bar: nodes >= 200, vibe coverage >= 90%, convergence distribution, embedding diversity

---

### Wave C (weeks 2-3, parallel worktrees)

```
worktree: ml/tourist-correction → Phase 2.1-2.3
worktree: ml/nlp-extraction    → Phase 3.2
```

Requires at least Bend + one larger city seeded from Wave B.

**Phase 2.1: Tourist Correction**
- Post-filter after `rank_candidates_with_llm()`. Hard binary partition at `tourist_score > 0.65`.
- Only fires when `local_vs_tourist_bias > 0.55` AND `source_count >= 3`.
- Feature flagged (`TOURIST_CORRECTION_ENABLED`). Logs demoted count per ranking event.

**Phase 2.2: Behavioral Write-Back Job**
- Nightly cron. Time-windowed query (yesterday only). Single CTE transaction per day (truly atomic, not batched).
- Idempotency: Laplace formula is mathematically idempotent — safe to re-run. `WriteBackRun` audit table logs each execution.
- Laplace formula: `(acceptance_count + 1) / (impression_count + 2)`.
- Uses existing columns per Decision #3. Least-privilege DB role recommended (UPDATE on ActivityNode scoring columns + SELECT on BehavioralSignal only).

**Phase 2.3: Post-Trip Disambiguation**
- "Did you end up going?" for `no_show_ambiguous` slots only (where disambiguation.py hasn't already inferred).
- Yes = `confirmed_attended`, `signal_weight: 0.7`. No + "not my thing" = `confirmed_skipped`, `-0.3`. No + "timing" = `confirmed_skipped`, no persona update.
- Cap 3 prompts per completed trip.

**Phase 3.2: NLP Preference Extraction (shared infra)**
- Two-pass: rule-based patterns (dimensions 1-5, 9) then Haiku LLM (long tail).
- Output: `list[PreferenceSignal]` with dimension, direction, confidence, source_text.
- Used by ChatGPT import (3.1) and onboarding freetext. Pulled forward from Wave D.

---

### Wave D (weeks 3-4, parallel worktrees)

```
worktree: ml/cold-start → Phase 3.1, 3.3, 3.4
worktree: ml/subflows   → Phase 5.1-5.5
```

Minimal overlap. Cold start merges first (touches BehavioralSignal write path).

**Cold Start (3.1, 3.3, 3.4):**
1. **3.1 ChatGPT import** — ZIP upload, streaming `ijson` parser, tree-walk mapping dict, keyword pre-filter, Haiku classification, feeds 3.2 extraction. Privacy: in-memory only, `SensitiveField` wrapper, source_text capped 500 chars, cap 500 conversations. **Security safeguards (from security review):**
   - ZIP bomb defense: max 50MB compressed, max 500MB decompressed (track bytes during streaming), check `ZipInfo.file_size` per entry
   - Path traversal: validate every `ZipInfo.filename` — reject `..`, absolute paths, backslashes. Only read `conversations.json`
   - Streaming cap: enforce 500-conversation limit during streaming (not after parse completes), max 200MB JSON bytes read
   - Auth required: endpoint MUST require authenticated session, tie ImportJob to authenticated user_id, per-user rate limit (3 imports/hour)
   - DataConsent check: verify `DataConsent.modelTraining` before persisting ImportPreferenceSignal. If false, tag signals `training_excluded: true`
   - HTML-encode source_text before storage (prevent stored XSS if rendered in admin views)
   - PII regex scrub before persistence (phone, email, SSN, credit card patterns)
2. **3.3 Destination prior** — Static JSON lookup per city. 0.15 weight blend, confidence < 0.3 gate.
3. **3.4 Synthetic simulation** — 12 archetypes x 50, Sonnet + Haiku two-agent loop, ~$20/run, `source: "synthetic_agent_v1"`, excluded from ranking at 500+ real users. **Security safeguards:**
   - Admin-only endpoint (`systemRole == "admin"` check)
   - Per-day budget cap ($100/day cumulative Anthropic spend across all synthetic runs)
   - Circuit breaker: 5 consecutive Haiku failures → abort run
   - Hard-coded archetype definitions only — never interpolate user data into simulation prompts
   - Validate Haiku output schema strictly (dimension enum, direction enum, confidence 0-1 range)
   - Synthetic user IDs use `synth-` prefix. Parquet extraction filters on BOTH `source != 'synthetic_agent_v1'` AND `userId NOT LIKE 'synth-%'` (defense in depth)

**Subflows (5.1-5.5):**
1. **5.2 Repeat city boost** — Pre-filter, three-tier exclusion, "revisit favorites" toggle. ~3hrs.
2. **5.4 Diversifier** — MMR post-processing (lambda=0.6), async batch, 3 alternatives per slot. ~5hrs.
3. **5.3 Slot fitter** — Insert-after-active, cascade.py reuse, meal protection, 3-slot cascade limit, sub-100ms. ~4hrs.
4. **5.1 Rejection recovery** — Redis burst counter (TTL 120s), vibe_tag overlap, -0.4 cap, fires once per trip. ~6hrs.
5. **5.5 Split detector** — Bimodal preferences, mutually exclusive with Abilene, 1/day max, unanimous veto. ~6hrs.

All subflows log to `BehavioralSignal.subflow`. Trip tracks state via `trip_subflow_state` JSON.

---

### Wave E (week 4+, parallel worktrees)

```
worktree: ml/training-infra → Phase 4.1-4.3
worktree: ml/models         → Phase 6.1-6.10
```

Everything runs shadow or offline. Zero user-facing risk.

**Training Infra (4.1-4.3):**
1. **4.1 Parquet extraction** — Nightly, denormalized, date-partitioned, append-only. Cold-user and synthetic partitions separate.
2. **4.2 Shadow mode** — `ShadowModelRunner`, fire-and-forget async, 10% sampling start, logs to RankingEvent shadow columns. **Security: shadow models must run locally only — no external API calls in shadow inference path.** Network policy or code assertion that shadow runner makes zero outbound HTTP. Add `RankingEvent` retention policy (180 days). **Observability:** track `shadow_success_rate` (alert if <8%), `shadow_latency_p99` (alert if >2x primary), `shadow_error_rate` by type. Agreement drift monitor on `ArbitrationEvent.agreement_score` trend.
3. **4.3 Eval harness** — Temporal split only. HR@5, MRR, NDCG@10. Bootstrap CI promotion gates (95% non-overlap). BPR contingency: hybrid gate — harness auto-flags failure after 4 consecutive weeks + 3K signals, human confirms skip to Two-Tower, 7-day staleness alert if flagged but no action.

**ML Models (6.1-6.10):**

All train on CPU. No GPU.

Model progression is layering, not replacement:
- BPR (6.1) → may fail vs LLM, skip to Two-Tower if so
- Two-Tower (6.2) → retrieval layer, replaces Qdrant cosine. **Pre-req: define `ActivitySearchService` as formal protocol/ABC** so Two-Tower can swap in without touching `GenerationEngine` or callers
- SASRec (6.3) → sequential re-ranker on Two-Tower candidates
- DLRM (6.4) → cross-feature scoring head on SASRec output
- Arbitration (6.5) → deterministic rules, LLM + ML parallel
- HLLM triggers (6.6) → subflow routing
- Collab filtering (6.7), Pareto group (6.8) → specialized
- Learned arb (6.9) → DATA-GATED, GBM at 1,500+ events
- GPS (6.10) → DATA-GATED, v2 mobile app

BPR contingency: if CI doesn't clear LLM after 4 weeks + 3K signals, skip to Two-Tower + SASRec. Infra is reusable regardless.

---

## Worktree Merge Protocol

- Each worktree runs its own tests before merge
- Wave boundary = review checkpoint (review between phases, not blind automation)
- If a worktree touches shared files, it merges first and the other rebases
- Conflict analysis:
  - Wave B: zero overlap
  - Wave C: zero overlap
  - Wave D: minimal (BehavioralSignal write path). Cold start merges first.
  - Wave E: zero overlap

---

## Risk Mitigation

### Technical Risks
1. **Arctic Shift data availability** — **PRE-FLIGHT: verify before Wave B2.** Start Bend as canary. If Parquet unavailable, pay for cheapest alternative Reddit data source.
2. **Schema migration on live data** — All new columns have defaults. No backfill in migration. Test on DB dump first. Postgres DDL is transactional — migration is atomic.

### Data Risks
3. **Feedback loop bias amplification** — 10-15% exploration budget, assigned to Phase 6 as ML arm prerequisite. Monitor impression Gini per city (alert > 0.7). Nightly health check via GH Actions cron.
4. **Synthetic signal contamination** — Integration test verifies zero synthetic rows in ranking Parquet. Runs on every CI build. Defense in depth: filter on BOTH `source` column AND `synth-` user ID prefix.
5. **Cold start selection bias** — Track disambiguation response rate per cohort. Never weight absence as negative.
6. **PII in imported data** — Regex scrub before persistence + 90-day source_text retention TTL. Phase 2: evaluate spaCy NER for name/address detection.

### Security Risks
7. **Signal weight injection** — `signal_weight` is server-only with DB CHECK constraint `[-1.0, 3.0]`. Never accepted from client payloads. Per-user per-venue dedup for weight-sensitive signals. (Security review FAIL — must address before Phase 1.2)
8. **ChatGPT import attack surface** — ZIP bomb defense, path traversal validation, streaming caps, auth required, DataConsent check. (Security review WARN — must address before Wave D)
9. **Cost DoS on synthetic simulation** — Admin-only endpoint, $100/day budget cap, circuit breaker on consecutive failures.

### Product Risks
10. **Tourist correction on thin-data cities** — `source_count >= 3` gate. Nodes with thin data don't get corrected.
11. **Group split social friction** — Unanimous veto, max 1/day, empowerment framing, required sync-back activity.

---

## Testing Strategy

### Tier 1: Unit Tests (~155 tests, every commit, no Docker)

Pure functions with known inputs/outputs. Covers: slot classifier, subflow tagger, alteration detector, off-plan signal, tourist correction, Laplace formula, NLP extraction, destination prior, arbitration rules, MMR diversifier, slot fitter, rejection pattern, split detector, model forward passes.

**Required boundary test suites (from test review):**
- Laplace smoothing: 0/0→0.5, 1/0→0.333, impression_count=9 vs 10 DLRM trust gate, float precision at extremes
- Tourist correction: 0.649999/0.65/0.650001, guard conditions (bias ≤0.55, source_count <3), all three at boundary simultaneously
- Slot fitter cascade: depth 2 (allowed) vs 3 (blocked), locked slot counting, meal protection
- Burst counter TTL: 119s (active) vs 120s (boundary) vs expired, synthetic signal exclusion via `source` filter
- Subflow priority: 9 subflows each winning when present, tie-breaking, unknown/null handling
- Signal weight bounds: verify server-side assignment only, CHECK constraint range

### Tier 2: Integration Tests (~55 tests, PR merge, CI service containers)

Real Postgres + Redis via GH Actions service containers. Qdrant added as service container (not testcontainers — existing CI pattern works). Local runs via `docker-compose.test.yml` (~1hr setup).

Covers: migration correctness (including default values on existing rows), signal pipeline E2E (full chain: write → tag → write-back), write-back job atomicity + idempotency + audit log, disambiguation flow, off-plan E2E, city seed validation, shadow mode fire-and-forget contract, training pipeline, repeat city exclusion, slot fitter + cascade, synthetic quarantine (ranking Parquet + burst counter + cross-contamination).

**Added from review:** ChatGPT import E2E (ZIP → ImportPreferenceSignal), Arbitration E2E (ML+LLM parallel → ArbitrationEvent logged), chaos/degradation tests (~15: Redis down, Qdrant down, Haiku timeout, Postgres timeout — verify graceful degradation).

### Tier 3: Offline Eval + Regression (nightly/weekly scheduled)

**Triggering:** Nightly via GitHub Actions `schedule` cron. Weekly via GCP Cloud Scheduler → Cloud Run Job. Per-model-promotion triggered by model artifact push.

**Monitoring:** Slack webhook on failure. `write_back_runs` table for write-back observability. Shadow mode metrics dashboard. Impression Gini alert.

**Nightly (health checks, not tests):** signal distribution, training volume, write-back success, impression Gini, cold venue rate. Need baselines and alert thresholds.

**Weekly (metrics jobs):** embedding space analysis, vibe tag distribution, entity resolution audit, PSI feature drift.

**Per-model-promotion (real pass/fail gates):** offline eval harness, bootstrap CI non-overlap, shadow mode duration met.

**Full-stack smoke test (every Wave merge — first thing built):**
Seed city → generate trip for known persona → verify recommendations align → verify no duplicates → verify signal pipeline captured everything. Concrete, scripted, repeatable. Runs in CI.

### CI Integration

| Test Category | CI Stage | Blocks Merge? |
|--------------|----------|--------------|
| Tier 1 (unit) | PR track-tests matrix (`ml` track) | Yes |
| Tier 2 (integration) | PR track-tests matrix (Postgres + Redis + Qdrant) | Yes |
| Synthetic quarantine | PR track-tests | Yes (contamination is catastrophic) |
| Contract tests (V2 schema) | PR contract-tests | Yes |
| Tier 3 nightly | `nightly-ml.yml` scheduled workflow | No (alerting) |
| Tier 3 weekly | Cloud Scheduler | No (alerting) |
| Full-stack smoke | Wave merge validation | Soft block (manual sign-off) |
| Model promotion | Artifact-triggered workflow | Yes (for model deploy) |

### Test Data Strategy

**Existing foundation (strong):** Factory functions (`make_*()` pattern), `FakePool`/`FakeQdrantClient`/`FakeEmbeddingService` mocks, shadow training signal builders.

**V2 additions:** Update existing factories with V2 columns in Wave A. New factories per wave. Golden test fixtures in `services/api/tests/fixtures/`: ChatGPT export ZIP, NLP extraction input/output pairs, destination prior JSON, synthetic archetype definitions.

### Test Count Summary (revised after test review)

| Phase | Unit | Integration | Chaos | Regression | Total |
|-------|------|-------------|-------|------------|-------|
| 0+1 | ~40 | ~15 | ~3 | 4 | ~62 |
| 2 | ~20 | ~7 | ~3 | ~3 | ~33 |
| 3 | ~28 | ~8 | ~3 | ~2 | ~41 |
| 4+6 | ~30 | ~10 | ~3 | ~5 | ~48 |
| 5 | ~35 | ~10 | ~3 | ~3 | ~51 |
| 7 | ~12 | ~5 | 0 | ~2 | ~19 |
| **Total** | **~165** | **~55** | **~15** | **~19** | **~254** |
