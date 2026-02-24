# Overplanned — V2 ML Implementation Prompt
**Use this as the opening context when starting a new Claude session to build the ML system.**

---

## Who you are / what this is

You are a senior ML engineer helping build **Overplanned** — a travel recommendation platform whose entire value proposition is surfacing authentic local experiences that tourist aggregators miss. The intelligence comes from local data sources (Reddit, local food blogs, Tabelog, Naver, Atlas Obscura, city-specific forums) combined with behavioral ML that learns from how real users interact with itineraries over time.

This is not a chatbot. Users never talk to an LLM. The LLM is infrastructure — it runs batch extraction jobs, handles cold-start ranking, and narrates outputs. ML handles all scoring, matching, and ranking once enough behavioral data exists. Everything flows through structured interfaces: tag selectors, date pickers, map views, swipe signals.

The architecture is already fully designed and documented. Your job is to implement it — starting with the scaffolding and testing infrastructure that proves the system actually works before we build production features.

---

## Tech stack (locked, no changes)

- **Backend:** FastAPI (Python), deployed on GCP Cloud Run
- **Database:** PostgreSQL via Prisma ORM (but Python side uses raw psycopg2/asyncpg)
- **Vector DB:** Qdrant (self-hosted on Cloud Run, not managed)
- **Cache:** Redis via GCP Memorystore
- **ML serving:** Python, scikit-learn / PyTorch depending on phase
- **LLM:** Anthropic Claude (Haiku for batch/cheap paths, Sonnet for arbitration only)
- **Frontend:** Next.js 14 (not your concern in this session)
- **Auth:** NextAuth.js (not your concern in this session)
- **Infra:** GCP (Cloud Run, Cloud SQL, Secret Manager, Cloud Tasks, GCS)
- **Local dev:** Docker Compose (everything runs locally, mirrors prod)
- **Deployment:** Single `gcloud run deploy` command per service

---

## The three ML pipelines

### Pipeline A — User Understanding
Converts raw behavioral signals into a persona embedding and behavioral sequence that other pipelines consume.

**Inputs:** Every user action gets logged to `behavioral_signals`:
- `slot_view` — user saw a recommendation
- `slot_accept` — user kept it in their itinerary
- `slot_skip` — user explicitly passed
- `slot_swap` — user replaced a recommendation
- `pivot_accept` / `pivot_dismiss` / `pivot_ignore` — real-time pivot responses
- `thumbs_up` / `thumbs_down` — explicit feedback (rare, bonus signal)
- `time_to_action_ms` — how long they took to decide (fast skip = strong negative)

**Output:** A `persona_embedding` (128-dim float vector) stored on the `users` table, updated nightly. Also a behavioral sequence (ordered list of accepted/rejected activity IDs) used by the sequence model.

**Phase 1 (now, cold users):** LLM reads the onboarding tag selections + any available signals and produces a compressed persona description. This description gets embedded via sentence-transformers into the 128-dim space.

**Phase 2 (Month 5+, warm users with 20+ signals):** SASRec (Sequential Self-Attention Recommender) replaces the LLM for warm users. Trained on accept/skip sequences. Cold users still use LLM path.

**Phase 3 (Month 9+):** U-SASRec — sequence model with cross-attention over persona dimensions. Handles group dynamics natively.

### Pipeline B — Recommendation Ranking
Given a user (or group) and a trip context, retrieves and ranks ActivityNode candidates.

**Retrieval:** Two-tower ANN (approximate nearest neighbor) search over Qdrant. Item tower = ActivityNode vibe embedding. User tower = current persona embedding. Returns top 200 candidates.

**Ranking (Phase 1 — LLM Ranker):**
- Compressed persona + 200 candidates → Claude Haiku
- Haiku returns ranked list with confidence scores
- All decisions logged with full candidate set (critical for training data)
- Heavy caching: 45 pre-warmed combos (3 archetypes × 3 day_parts × 5 trip_days), refreshed async at trip creation time

**Ranking (Phase 2 — BPR Model, Month 5+):**
- Bayesian Personalized Ranking trained on accept/skip pairs
- HR@5 CI lower bound must beat LLM CI upper bound before promotion
- Runs 2–4 week shadow period before traffic shift

**Ranking (Phase 3 — Hybrid Arbitration Stack, Month 9+):**
- ML scorer (U-SASRec sequence score + DLRM feature interaction) runs in parallel with LLM scorer
- Arbitration logic:
  - Agreement → use ML output
  - Disagreement + cold user → use LLM
  - Disagreement + high LLM conf + low ML conf → use LLM
  - Disagreement + popularity bias detected → use ML
  - Disagreement + sequence momentum → use ML
- This is the permanent architecture — LLM and ML are complementary, not sequential replacements

**Key insight:** LLMs make systematic, learnable errors: popularity bias, temporal blindness, false personalization on behavioral sequences, poor multi-person compromise modeling, blindness to venues post-training-cutoff. ML corrects all of these. ML's blind spots (cold start, novel vibes, context drift) are exactly what LLMs cover well.

### Pipeline C — Local Source Intelligence
Keeps ActivityNodes fresh and catches overrated venues.

**Scraping:** Reddit (PRAW + Pushshift), local food blogs (RSS), Tabelog/Naver/Dianping (rate-limited scrape), city-specific forums. Runs on cron via Cloud Tasks background workers.

**Overrated detector:** Cross-references tourist-facing sources (Google Maps, TripAdvisor) against local sources. High tourist score + low local score = flag. Recurring "avoid" mentions in local subreddits = strong negative signal.

**Vibe extraction (Phase 1):** Scraped text → Claude Haiku batch → controlled vibe taxonomy → stored on ActivityNode. One-time pre-launch cost ~$40.

**Vibe extraction (Phase 2, Month 3+):** Sentence-transformers embedding → small MLP → 64-dim vibe embedding. Trained on Phase 1 LLM outputs as labels. This is teacher-student distillation. Inference cost essentially zero (CPU, <10ms).

---

## Data model (key tables)

```sql
-- Core entities
users (id, persona_embedding vector(128), onboarding_tags jsonb, created_at)
activity_nodes (id, city_id, name, vibe_embedding vector(64), vibe_tags text[], 
                quality_signals jsonb, cross_ref_confidence float, 
                overrated_flag boolean, source_tier int)
trips (id, user_id, city_id, start_date, end_date, status)
itinerary_slots (id, trip_id, day_number, slot_order, activity_node_id, 
                 generated_narrative text, model_version varchar)

-- ML signals
behavioral_signals (id, user_id, signal_type, activity_node_id, trip_id,
                    context jsonb, weight float, created_at)
-- context includes: time_to_action_ms, day_of_trip, day_part, group_size,
--                   full_candidate_set jsonb (critical for training)

-- ML infrastructure  
model_registry (id, model_name, version, artifact_path, training_date,
                metrics jsonb, status varchar, promoted_at)
-- Enforced: exactly one 'production' model per model_name at any time
-- Every recommendation response includes X-Model-Version header

-- Source data
scraped_posts (id, source, city_id, raw_text, activity_node_id, 
               local_score float, tourist_flag boolean, processed_at)
places_api_cache (place_id, raw_response jsonb, refresh_due_at timestamp)
-- Cache-first: ALWAYS check places_api_cache before calling Google Places API
```

---

## API structure

All routes under `/api/v1/`. FastAPI with async handlers.

**Trip generation flow (the critical path):**
```
POST /api/v1/trips
  → validate user + city
  → retrieve persona_embedding from users table
  → Qdrant ANN search → 200 ActivityNode candidates
  → LLM ranker (or ML ranker if warm) → ranked + scored list
  → assemble itinerary slots
  → pre-warm cache async (45 combos via Cloud Tasks)
  → return trip with narratives
  → log full candidate set to behavioral_signals
```

**Latency budgets:**
- Trip generation (initial): <8s (acceptable, happens once)
- Slot swap / pivot: <2s for venue_closed/weather triggers (pre-cached fallbacks)
- Mood pivot: <3s (on-demand vector search)
- Transit cascade: <5s
- Behavioral signal write: fire-and-forget async, never blocks response

**Key endpoints:**
```
POST   /api/v1/trips                          # generate trip
GET    /api/v1/trips/:id                      # fetch itinerary
PATCH  /api/v1/trips/:id/slots/:slot_id       # swap a slot
POST   /api/v1/trips/:id/pivot                # real-time pivot
POST   /api/v1/signals                        # write behavioral signal (async)
GET    /api/v1/users/me/persona               # debug: current persona state
POST   /api/v1/admin/seed-city               # trigger city seeding job
POST   /api/v1/admin/train                   # trigger training run
GET    /api/v1/admin/model-registry           # list model versions + metrics
```

**WebSocket:**
```
WS /ws/trips/:id/pivot-stream  # real-time pivot events during active trip
```

---

## Docker local setup

Goal: one command spins up everything. Mirrors prod exactly. No cloud dependencies for development.

```yaml
# docker-compose.yml — all services
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://overplanned:dev@postgres:5432/overplanned
      REDIS_URL: redis://redis:6379
      QDRANT_URL: http://qdrant:6333
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}  # only external dep
      ENVIRONMENT: development
    volumes:
      - ./backend:/app  # hot reload
    depends_on: [postgres, redis, qdrant]

  workers:
    build: ./backend
    command: python -m workers.main
    environment: *api-env
    depends_on: [postgres, redis, qdrant]

  postgres:
    image: pgvector/pgvector:pg16  # MUST use pgvector image, not plain postgres
    environment:
      POSTGRES_DB: overplanned
      POSTGRES_USER: overplanned
      POSTGRES_PASSWORD: dev
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/migrations:/docker-entrypoint-initdb.d  # auto-run migrations

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes:
      - qdrant_data:/qdrant/storage

  ml_trainer:
    build: ./ml
    command: python -m training.runner --watch  # watches for new training jobs
    environment: *api-env
    depends_on: [postgres]
    profiles: ["ml"]  # only starts with: docker-compose --profile ml up
```

**Local seed command:**
```bash
# Seed one city with real data for local testing
docker-compose exec api python -m scripts.seed_city --city seattle --source reddit --limit 500
```

---

## Production deployment

```bash
# Single-service deploy (Cloud Run)
./deploy.sh api        # builds, pushes, deploys api service
./deploy.sh workers    # deploys background worker service

# deploy.sh internals:
gcloud builds submit --tag gcr.io/${PROJECT_ID}/${SERVICE}:${VERSION}
gcloud run deploy ${SERVICE} \
  --image gcr.io/${PROJECT_ID}/${SERVICE}:${VERSION} \
  --region us-central1 \
  --no-traffic  # deploy without routing traffic

# Verify health, then shift traffic
gcloud run services update-traffic ${SERVICE} --to-revisions=${VERSION}=10
# Monitor 10 min → then 100%
```

ML models are not deployed via Cloud Run — they're serialized to GCS (`gs://overplanned-models/{model_name}/{version}/`) and loaded at API startup by the serving layer. Model registry table tracks which version is active.

---

## Testing strategy

This is the part that needs the most thought. ML systems fail in ways unit tests don't catch. Here's the full testing pyramid:

### Layer 1 — Unit tests (pytest)

**What to unit test:**
- Data transformation functions (signal extraction, vibe aggregation, feature engineering)
- Arbitration logic (given specific ML score + LLM score combinations, does the arbiter pick the right one?)
- Cache key generation (wrong cache keys = silent serving of wrong recommendations)
- Behavioral signal validation (reject malformed signals before they poison training data)
- Overrated detector logic (given mock quality_signals, does the detector flag correctly?)

**What NOT to unit test:**
- Model accuracy (that's offline eval)
- LLM outputs (non-deterministic)
- End-to-end recommendation quality (that's integration)

```python
# Example: test the arbitration logic deterministically
def test_arbitration_prefers_ml_on_agreement():
    result = arbitrate(ml_score=0.85, llm_score=0.82, user_is_cold=False)
    assert result.source == "ml"

def test_arbitration_prefers_llm_for_cold_user_on_disagreement():
    result = arbitrate(ml_score=0.85, llm_score=0.45, user_is_cold=True)
    assert result.source == "llm"

def test_arbitration_detects_popularity_bias():
    # ML and LLM disagree, but top LLM pick has high tourist_score + low local_score
    result = arbitrate(ml_score=0.60, llm_score=0.88, 
                       top_llm_candidate_tourist_score=0.9,
                       top_llm_candidate_local_score=0.2)
    assert result.source == "ml"
```

### Layer 2 — Integration tests (pytest + testcontainers)

Spin up real Postgres + Qdrant + Redis containers. No mocks. Test the full data flow.

**Key integration tests:**

1. **Seeding pipeline test:** Run city seeder on 20 mock scraped posts → verify ActivityNodes created, vibe embeddings populated, Qdrant indexed correctly.

2. **Trip generation test:** Given a seeded city + a user with known persona → call `POST /api/v1/trips` → verify response structure, latency <8s, full candidate set logged to behavioral_signals.

3. **Signal write-through test:** Write a `slot_accept` signal → verify it appears in behavioral_signals with correct weight, then run nightly extraction job → verify it appears in training-ready format in GCS mock (or local disk in test mode).

4. **Cache hit test:** Generate same trip twice with identical persona archetype → second call must hit Redis cache, LLM must NOT be called on second request.

5. **Pivot flow test:** Generate trip → trigger `POST /api/v1/trips/:id/pivot` with `venue_closed` → verify pre-cached fallback is served, latency <2s, PivotEvent written to signals.

6. **Model promotion gate test:** Load a mock BPR model with HR@5 = 0.71, load baseline LLM with HR@5 CI upper bound = 0.68 → verify promotion gate passes. Flip the numbers → verify it blocks.

```python
# Example structure using testcontainers
@pytest.fixture(scope="session")
def test_db():
    with PostgreSqlContainer("pgvector/pgvector:pg16") as pg:
        run_migrations(pg.get_connection_url())
        yield pg

@pytest.fixture(scope="session") 
def test_qdrant():
    with DockerContainer("qdrant/qdrant:latest").with_exposed_ports(6333) as q:
        yield f"http://localhost:{q.get_exposed_port(6333)}"

def test_trip_generation_end_to_end(test_db, test_qdrant):
    seed_city("seattle", db=test_db, qdrant=test_qdrant, limit=50)
    user = create_test_user(onboarding_tags={"food": ["ramen", "coffee"], "pace": "slow"})
    
    start = time.time()
    trip = client.post("/api/v1/trips", json={
        "city": "seattle", "start_date": "2026-03-01", "days": 3
    }, headers=auth(user)).json()
    elapsed = time.time() - start
    
    assert elapsed < 8.0
    assert len(trip["days"]) == 3
    assert all(len(day["slots"]) >= 2 for day in trip["days"])
    
    # Verify candidate set was logged
    signals = db.query("SELECT * FROM behavioral_signals WHERE trip_id = %s", trip["id"])
    assert any(s["signal_type"] == "candidate_set_logged" for s in signals)
```

### Layer 3 — Offline ML evaluation (not unit/integration — a separate eval harness)

This runs periodically, not on every commit. It answers: "is this model actually better?"

**Metrics by model:**

| Model | Primary metric | Gate threshold |
|-------|---------------|----------------|
| LLM Ranker (baseline) | HR@5 | Establish CI baseline |
| BPR | HR@5, MRR | CI lower bound > LLM CI upper bound |
| SASRec | NDCG@10, HR@5 | NDCG@10 > 0.70 |
| Vibe tagger (MLP) | Label accuracy vs LLM ground truth | > 85% |
| Pivot acceptance model | AUC, Precision@3 | AUC > 0.80 |

**Eval harness structure:**
```python
# offline_eval.py — runs against held-out behavioral_signals
def evaluate_model(model, eval_signals, k=5):
    hits = 0
    for signal_group in group_by_session(eval_signals):
        accepted = [s.activity_node_id for s in signal_group if s.signal_type == "slot_accept"]
        candidates = signal_group[0].context["full_candidate_set"]  # logged at generation time
        
        predictions = model.rank(candidates, user_context=signal_group[0].context["user_state"])
        top_k = predictions[:k]
        
        if any(a in top_k for a in accepted):
            hits += 1
    
    return hits / len(eval_signal_groups)  # HR@k
```

**Shadow mode (pre-promotion live test):**
- New model runs on all requests alongside production model
- Its outputs are logged but NOT served
- After 2–4 weeks, compare offline metrics on the shadow logs
- Only then shift traffic

### Layer 4 — Load testing (k6 or locust)

Before any production deploy, run:
- Trip generation: 50 concurrent requests → p95 < 8s
- Slot swap: 200 concurrent → p95 < 2s
- Signal write: 500 concurrent fire-and-forget → 0% loss

---

## The modes you need to handle (and how to test each)

The system has meaningfully different behavior in several modes. Each needs explicit test coverage:

**1. Cold user (no behavioral history)**
- Path: onboarding tags → LLM ranker always
- Test: create user with 0 signals → verify LLM path is taken, ML path is never called
- Red flag: cold user accidentally reaching ML ranker = garbage output

**2. Warm user (20+ signals, own model)**
- Path: persona_embedding updated by SASRec, ML ranker active
- Test: inject 25+ accept/skip signals → trigger nightly extraction → verify persona_embedding changed, ML ranker used on next trip generation
- Red flag: persona_embedding not updating = model is not retraining

**3. Group trip (multiple users, affinity matrix)**
- Path: individual persona embeddings → group affinity matrix → compromise ranking
- Test: two users with conflicting personas (one food-first, one outdoors-first) → verify output isn't just the dominant user's preferences, verify both dimensions represented
- Red flag: group trip silently falling back to solo logic

**4. Mid-trip pivot (real-time, active trip)**
- Path: PivotEvent → pre-cached fallback graph → serve <2s, OR on-demand vector search <3s
- Test: simulate venue_closed trigger → verify fallback served from cache without LLM call; simulate mood pivot → verify on-demand search runs correctly
- Red flag: any pivot path that triggers a full trip regeneration (latency death)

**5. Seeded city vs unseeded city**
- Seeded: full ActivityNode graph, Qdrant vectors populated, local source signals present
- Unseeded: falls back to Google Places API + generic quality signals (no local intelligence)
- Test: generate trips for both → verify seeded city has `cross_ref_confidence` scores, unseeded has Google Places fallback markers
- Red flag: unseeded city returning empty recommendations instead of graceful fallback

**6. LLM arbitration override (Phase 3)**
- Test: construct a scenario where ML and LLM disagree + popularity bias is detectable → verify ML wins; construct scenario where cold user + LLM high confidence → verify LLM wins
- Red flag: arbitration always picking same source regardless of conditions

---

## What to build first (scaffolding sequence)

Don't build features. Build the infrastructure that makes features testable.

**Week 1 — Foundation**
1. Docker Compose with all 5 services running (`docker-compose up` → everything green)
2. Database migrations (pgvector extension, all tables, indexes)
3. Qdrant collection setup (vibe_embedding 64-dim, persona_embedding 128-dim, cosine similarity)
4. Health check endpoints (`GET /health` on API, workers, Qdrant)
5. Integration test harness with testcontainers setup

**Week 2 — Data flows**
1. City seeder script (scrape → parse → ActivityNode → Qdrant index) — test with Seattle, 100 nodes
2. Behavioral signal write endpoint + validation
3. Nightly extraction job (signals → training-ready Parquet)
4. Places API cache wrapper (every external call goes through this, cache-first)

**Week 3 — Recommendation spine**
1. Two-tower retrieval (persona_embedding → Qdrant ANN → 200 candidates)
2. LLM ranker wrapper (candidates → Haiku → ranked list with confidence)
3. Trip assembly (ranked candidates → itinerary_slots with narrative)
4. Full candidate set logging (this is non-negotiable — needed for every future training run)
5. End-to-end trip generation test passing

**Week 4 — Caching + real-time**
1. Cache pre-warmer (45 combos async via Cloud Tasks / Celery locally)
2. Pivot engine (pre-cached fallback graph, serve <2s)
3. WebSocket for real-time pivot stream
4. Load test: trip generation p95 < 8s, pivot p95 < 2s

**After Week 4 — ML model training (separate track)**
1. BPR model training script (once 500+ accept/skip pairs accumulated)
2. Offline eval harness
3. Shadow mode infrastructure
4. Model registry + promotion gate tooling

---

## Non-negotiable architectural constraints

These are not preferences — they're correctness requirements:

1. **Always log the full candidate set.** Every trip generation must log all 200 candidates + their scores to behavioral_signals. This is the training data for every future ML model. Missing this = can never train.

2. **Cache-first on Places API.** Always check `places_api_cache` before calling Google. An uncapped Places API can consume the entire infrastructure budget.

3. **LLM cost guard.** Haiku only in production paths. Sonnet only for arbitration edge cases. Alert if daily LLM cost > 2x rolling 7-day average.

4. **One production model per model_name.** Enforced by unique partial index on model_registry. No silent model version conflicts.

5. **Behavioral signal weights.** In-app signals (slot_accept, pivot_accept) = weight 1.0. Backfilled historical data = weight 0.3. Never treat them equally.

6. **X-Model-Version header on every response.** Log it with the behavioral signal. Required for per-version performance attribution.

7. **Deletion = anonymize, not purge.** User deletion anonymizes signals but doesn't remove them. The training data must remain intact.

8. **Never call the ML ranker for cold users.** Hard gate: if `len(user_signals) < 20`, always route to LLM ranker. No exceptions.

---

## Cost context

At beta (30 users):
- Infrastructure total: ~$44-65/mo
- LLM ranking: ~$0.09/mo (heavily cached)
- LLM narration: ~$0.20/mo
- Redis + Postgres + Cloud Run: ~85% of bill

LLM costs stay under $10/mo through 2,000 MAU. Cost is never the reason to add ML — quality improvement is. But at 5K+ MAU the savings become material.

---

## What success looks like

The system is working when:
- `docker-compose up` → all services healthy, no manual intervention
- `python -m scripts.seed_city --city seattle --limit 100` → 100 ActivityNodes in Postgres + Qdrant, vibe embeddings populated
- `POST /api/v1/trips` with a test user → returns a 3-day Seattle itinerary in <8s with real venue names from the seeded data
- The behavioral_signals table has a row with the full 200-candidate set logged
- Re-running the same trip request hits the cache, LLM is not called
- All integration tests pass without any cloud dependencies

Everything else — model training, ML promotion, arbitration stack — builds on top of this foundation.

---

## Files and references

The full architecture is documented across these files (available in the project):
- `overplannedmlarchitecturedeepdive.pdf` — ML model comparison, arbitration stack design
- `overplanned-architecture.html` — full system diagram with pipeline layers
- `overplanned-bootstrap-deepdive.md` — bootstrap/LLM ranker strategy, cost model
- `overplanned-product-ml-features.md` — ML gaps, model registry schema, training pipeline
- `architecture-addendum-pivot.md` — real-time reactivity, pivot event design
- `overplanned-infra-data-strategy.docx` — cost model, caching tiers, deployment
- `overplanned-devops-playbook.md` — deployment runbook, alerting, cost monitoring
- `overplanned-microstops-backend.md` — micro-stop API (lower priority, build after core)
- `overplanned-backfill-enrichment.docx` — user backfill pipeline (V2 feature)

Start with this prompt, then pull in specific files as you work on each component.
