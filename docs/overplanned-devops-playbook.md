# Overplanned — DevOps & Incident Playbook

*February 2026 · Internal*
*Stack: Cloud Run · Cloud SQL (Postgres) · Redis Memorystore · Qdrant (self-hosted) · GCS*
*Philosophy: self-hosted where possible, alert early, fail gracefully, never surprise the user*

---

## Monitoring Stack

**GCP Cloud Monitoring** — primary infrastructure metrics. All services on GCP emit metrics natively; no additional instrumentation needed for CPU, memory, network, instance count.

**Cloud Logging** — structured application logs. All Cloud Run services write JSON logs. Severity levels: DEBUG (dev only), INFO (operational events), WARNING (degraded state, not yet broken), ERROR (broken, needs attention), CRITICAL (user-facing failure, wake someone up).

**Uptime Checks** — Cloud Monitoring uptime checks on:
- `/health` endpoint (API server, returns 200 with service status JSON)
- `/ready` endpoint (checks Postgres connectivity, Redis connectivity, returns 503 if either is down)
- Qdrant health endpoint

**Alerting policy** — all alerts route to PagerDuty (or equivalent). Two severity levels:
- **P1 (page immediately):** user-facing failures, data loss risk, security events
- **P2 (notify, no page):** degraded performance, non-critical service issues, cost anomalies

At MVP scale (< 500 MAU), P1 is "check this within 2 hours." P2 is "check this tomorrow morning." There is no on-call rotation at this scale — Kevin is the on-call.

---

## Alert Definitions

### Cloud Run — API Server

| Metric | Warning threshold | Critical threshold | Action |
|---|---|---|---|
| Error rate (5xx/total) | >0.5% over 5 min | >2% over 5 min | P2 / P1 |
| P99 request latency | >1.5s over 5 min | >3s over 5 min | P2 / P1 |
| Instance count at ceiling | — | Yes (2+ min) | P1 — scale ceiling may be too low |
| Cold start rate | >20% of requests | >50% of requests | P2 — min instances need tuning |
| Memory utilization | >75% | >90% | P2 / P1 |

**Scale ceiling risk:** Cloud Run autoscales to a configured max instance count. If traffic hits the ceiling and requests are queued, latency spikes without an error rate spike — the alert won't fire. Set a separate alert on request queue depth > 0 for more than 60 seconds.

```yaml
# Cloud Monitoring alert policy (pseudoconfig)
alert_policy:
  name: "API Server — Error Rate Critical"
  conditions:
    - metric: run.googleapis.com/request_count
      filter: resource_labels.service_name="api-server" AND metric_labels.response_code_class="5xx"
      comparison: COMPARISON_GT
      threshold_value: 0.02   # 2% error rate
      duration: 300s          # sustained for 5 minutes
  notification_channels: [pagerduty-p1]
```

---

### Cloud SQL — Postgres

| Metric | Warning | Critical | Action |
|---|---|---|---|
| CPU utilization | >70% sustained 10 min | >90% sustained 5 min | P2 / P1 |
| Memory utilization | >75% | >90% | P2 / P1 |
| Active connections | >80% of max_connections | >95% | P1 — PgBouncer may be misconfigured |
| Replication lag (if replica exists) | >30s | >120s | P2 / P1 |
| Disk utilization | >70% | >85% | P2 — P1 at 85, disk full = catastrophic |
| Query duration P99 | >500ms | >2s | P2 / P1 |
| Failed connections | >10/min | >50/min | P2 / P1 |

**PgBouncer connection pool:** Cloud SQL with PgBouncer is the architecture. `max_connections` on db-g1-small is 100. PgBouncer pool_size should be set to 20 — enough concurrency, well below the hard limit. Alert fires at 80 active connections (before PgBouncer starts queuing). If this alert fires frequently, the pool size needs tuning or the instance needs upgrading.

**Disk full is catastrophic.** Postgres stops accepting writes when disk is full. Alert at 70% (plan), alert again at 85% (act immediately). At MVP scale (50K ActivityNodes, behavioral signals accumulating), disk grows ~2-5GB/month. db-g1-small comes with 10GB — plan your upgrade.

**Runbook — Postgres CPU Spike:**
1. Check Cloud Logging for slow queries: `resource.type="cloudsql_database" severity>=WARNING`
2. Run `SELECT * FROM pg_stat_activity WHERE state = 'active' ORDER BY query_start ASC LIMIT 20;` — identify long-running queries
3. Check if a training data extraction job is running concurrently with user traffic — these should be time-gated to 3–5am UTC
4. If a specific query is spiking: `EXPLAIN ANALYZE <query>` — likely a missing index
5. If it's the nightly job: kill it (`SELECT pg_cancel_backend(pid)`) and reschedule for off-hours

---

### Redis Memorystore

| Metric | Warning | Critical | Action |
|---|---|---|---|
| Memory utilization | >70% | >85% | P2 / P1 |
| Eviction rate | >0 (any eviction) | >100/min | P1 immediately |
| Cache hit rate | <80% | <60% | P2 / P1 |
| Connected clients | >80% of maxclients | >95% | P2 / P1 |
| Latency P99 | >5ms | >20ms | P2 / P1 |
| Replication lag (if HA) | >1s | >5s | P2 / P1 |

**Why eviction is a P1:** Any Redis eviction means the LRU policy is kicking in — a cached narrative or ranked candidate set is being dropped to make room. The fallback (recompute from Postgres + ML inference) works correctly, but it causes a cascade: suddenly every cache miss hits Postgres and potentially triggers an LLM call. At low MAU this is manageable. At 500 MAU with simultaneous eviction spikes, you can melt Postgres and spike LLM costs simultaneously.

**Runbook — Redis Crash / Unavailable:**
1. Immediate impact: all cache reads fail-open to Postgres + recompute. System continues to function, just slower and more expensive.
2. Check Memorystore console for instance status. If it's auto-recovering (GCP HA failover), wait — usually <60 seconds.
3. If it's not auto-recovering: Cloud Support ticket + manually restart instance via gcloud CLI:
   ```bash
   gcloud redis instances failover INSTANCE_ID --region=REGION
   ```
4. After recovery: cache is empty. Do NOT immediately warm it — let it fill organically to avoid a thundering herd of LLM calls. The system handles cold cache correctly.
5. Monitor LLM costs for the next 2 hours — expect a temporary spike as cache refills.
6. Post-incident: check if eviction preceded the crash. If memory utilization was >90% before crash, upgrade instance tier immediately.

**Runbook — High Eviction Rate:**
1. Check which key patterns are being evicted: `redis-cli --hotkeys` (requires maxmemory-policy = allkeys-lru)
2. If LLM narrative keys are evicting: TTL is set to 30 days but memory is insufficient. Either increase Redis memory or reduce narrative cache TTL.
3. If ranked candidate keys are evicting: session traffic is higher than provisioned for. Scale Redis memory.
4. Check if a batch cache-warming job ran without rate limiting — can over-fill cache and cause a subsequent eviction cascade.

---

### Qdrant (self-hosted on Cloud Run)

Qdrant runs as a separate Cloud Run service. It is not a managed service — it requires more explicit monitoring.

| Metric | Warning | Critical | Action |
|---|---|---|---|
| Service availability | — | Returns non-200 on health check | P1 |
| Query latency P99 | >10ms | >50ms | P2 / P1 |
| Memory utilization | >70% | >85% | P2 / P1 |
| Index build time | >5 min | >20 min | P2 — nightly reindex taking too long |
| Collection size drift | >10% from expected | >30% | P2 — investigate unexpected writes |

**Runbook — Qdrant Unavailable:**
Qdrant down means vector search (two-tower retrieval) is unavailable. At MVP, BPR or LLM ranker is the active model — neither uses Qdrant. Impact is zero until two-tower goes live at Month 9.

Post Month 9 runbook:
1. Two-tower retrieval fails. Serving layer falls back to BPR model automatically (shadow mode infrastructure stays warm for exactly this reason).
2. Check Cloud Run logs for Qdrant service. Most common cause: OOM — container exceeds memory limit.
3. Immediate fix: restart Cloud Run service revision (`gcloud run services update qdrant --region=REGION`)
4. If OOM: increase Cloud Run memory limit for Qdrant service. At 50K nodes × 64-dim float32 = ~12MB for just the vectors. Total Qdrant memory usage is ~3-4x that including HNSW graph. 256MB minimum, 512MB comfortable.
5. Qdrant data is not persistent in Cloud Run by default — rebuild index from Postgres on restart:
   ```bash
   python scripts/rebuild_qdrant_index.py --source=postgres --collection=activity_nodes
   # Runtime: ~5 minutes for 50K nodes
   ```
6. Verify index integrity: compare Qdrant collection size with `SELECT COUNT(*) FROM activity_nodes WHERE vibe_embedding IS NOT NULL`

---

### Background Workers

| Job | Expected duration | Alert if | Action |
|---|---|---|---|
| Training data extraction (nightly 3am) | <10 min | >30 min | P2 — check for DB lock or large signal volume |
| Scrape refresh (weekly) | <2 hours | >4 hours | P2 — check for rate limiting / bot detection |
| LLM batch extraction | Varies | Job fails | P1 — check LLM API quota and content hash cache |
| Cache pre-warmer (at trip creation) | <30s | >60s | P2 — may indicate Redis slowness |
| ML shadow mode runner | <5 min | >20 min | P2 — check model serving infrastructure |
| Nightly score history append | <5 min | >15 min | P2 — check DB write throughput |

**Job monitoring pattern:** Every background job writes a `job_run` record to Postgres on start, and updates it on completion or failure. A Cloud Monitoring alerting policy checks for jobs that started but have no completion record after 2x expected duration.

```sql
CREATE TABLE job_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- running | success | failed
    records_processed INT,
    error_message TEXT,
    duration_seconds INT GENERATED ALWAYS AS 
        (EXTRACT(EPOCH FROM (completed_at - started_at))::INT) STORED
);
```

Alert: `SELECT * FROM job_runs WHERE status = 'running' AND started_at < NOW() - INTERVAL '30 minutes'`

---

## Cost Monitoring

**The self-hosted, cost-recovery-first approach requires tight cost visibility.** An unexpected LLM cost spike can 3x the monthly bill. An uncapped Places API can eat the entire budget.

### LLM Cost Dashboard

Track per day:
- Total LLM API calls
- Calls by model (Haiku vs Sonnet — never Sonnet in production paths)
- Calls by purpose (ranking / narration / extraction / cold-start)
- Cost per recommendation (total LLM cost / recommendations served)
- Cache hit rate for narratives (cache hit = $0 LLM cost)

**Alert:** LLM daily cost > 2x rolling 7-day average → P2. This catches a runaway loop or uncached path immediately.

**Alert:** Narrative cache hit rate < 60% → P2. This means narratives are being generated per-user instead of shared — investigate the cache key logic.

### Google Places API Cost

Places Details API is not on the same quota as Maps loads. Track separately.

**Alert:** Places API calls/day > 500 during beta phase → P2. The cache-first policy should keep this very low. If it spikes, something is bypassing the `places_api_cache` table check.

```python
# Every Places API call must go through this wrapper
def get_place_details(place_id: str) -> dict:
    # Check cache FIRST — always
    cached = db.query(
        "SELECT raw_response FROM places_api_cache WHERE place_id = %s AND refresh_due_at > NOW()",
        place_id
    )
    if cached:
        metrics.increment("places_api.cache_hit")
        return cached.raw_response
    
    # Cache miss — make the API call and store result
    metrics.increment("places_api.cache_miss")
    result = google_places_client.get_details(place_id)
    db.execute(
        "INSERT INTO places_api_cache (place_id, raw_response, refresh_due_at) VALUES (%s, %s, %s) ON CONFLICT (place_id) DO UPDATE SET raw_response = EXCLUDED.raw_response, refresh_due_at = EXCLUDED.refresh_due_at",
        place_id, result, compute_refresh_due(result['type'])
    )
    return result
```

---

## Deployment Runbook

### Standard Deploy (Cloud Run)

Cloud Run deploys are zero-downtime by default — traffic is shifted to the new revision gradually.

```bash
# Build and push container
gcloud builds submit --tag gcr.io/PROJECT_ID/api-server:VERSION

# Deploy new revision (traffic stays on old until verified)
gcloud run deploy api-server \
  --image gcr.io/PROJECT_ID/api-server:VERSION \
  --region us-central1 \
  --no-traffic  # deploy without shifting traffic

# Verify new revision health
curl https://api-server-VERSION-hash-uc.a.run.app/health

# Shift traffic gradually
gcloud run services update-traffic api-server \
  --to-revisions=VERSION=10  # 10% canary

# Monitor error rate on new revision for 10 minutes
# If clean: shift to 100%
gcloud run services update-traffic api-server \
  --to-revisions=VERSION=100
```

**Rollback:** Traffic shift is instant. If the new revision shows elevated error rate:
```bash
gcloud run services update-traffic api-server \
  --to-revisions=PREVIOUS_VERSION=100
```

### Database Migrations

Never run migrations during peak hours. Always run them in a transaction with a rollback plan.

```bash
# Check migration plan before executing
psql $DATABASE_URL -f migrations/NNNN_description.sql --dry-run  # if supported

# Run migration
psql $DATABASE_URL -f migrations/NNNN_description.sql

# Verify
psql $DATABASE_URL -c "\d table_name"  # check schema matches expectation
```

**Zero-downtime migration pattern for large tables:**
1. Add new column as nullable with no default
2. Deploy code that writes to both old and new column
3. Backfill new column in batches (1000 rows at a time, sleep 100ms between batches)
4. Add NOT NULL constraint after backfill completes
5. Deploy code that reads from new column only
6. Drop old column (optional, safe at this point)

Never add a NOT NULL column without a default on a live table — Postgres will lock the table for the duration of the migration.

---

## Failure Mode Catalog

### Redis unavailable
**Behavior:** All cache reads return miss. System falls through to Postgres + ML inference for every request.
**User impact:** Latency increases (200ms → 1-2s). No errors visible to user if timeouts are configured correctly.
**Auto-recovery:** Yes, if Memorystore HA is enabled. Failover <60 seconds.
**Cost impact:** LLM costs spike until cache refills (hours).
**Action:** Monitor LLM cost dashboard. Do not aggressively warm cache — let it fill organically.

### Postgres unavailable
**Behavior:** All requests fail. No graceful degradation possible for write paths.
**User impact:** App shows error state. Itinerary generation fails. Mid-trip pivots fail.
**Auto-recovery:** Cloud SQL HA failover, typically <120 seconds.
**Action:** P1 immediately. Monitor Cloud SQL failover status in console. If failover completes and connections still fail, restart API server (connection pool may have stale connections).

### Qdrant unavailable (post Month 9)
**Behavior:** Two-tower vector search unavailable. Serving layer routes to BPR fallback automatically.
**User impact:** Recommendation quality degrades to BPR level (still good, not optimal). No visible errors.
**Auto-recovery:** No — Cloud Run service restart is manual.
**Action:** P2. Restart Qdrant Cloud Run service. Rebuild index from Postgres. Takes ~5 minutes.

### LLM API unavailable (Anthropic outage)
**Behavior:** Narration layer fails. Ranking layer fails for cold users (LLM ranker path).
**User impact:** New itinerary generation fails. Cached narratives still serve (existing itineraries unaffected).
**Auto-recovery:** No — dependent on Anthropic uptime.
**Action:** P1 if outage >15 minutes. Surface a friendly "we're having trouble generating your itinerary right now — try again in a few minutes" to users attempting new trip generation. Do not queue — LLM outages are unpredictable. Log the attempt, prompt user to retry manually.

### Scraper blocked / rate-limited
**Behavior:** Pipeline C refresh fails for affected source. ActivityNode freshness degrades over time.
**User impact:** None immediate. Stale data accumulates over days/weeks.
**Auto-recovery:** No.
**Action:** P2. Check scraper logs. For Reddit: check Arctic Shift as fallback per reddit-access-addendum. For Tabelog: reduce request rate, implement longer delays, check if user-agent rotation is needed. For blogs: usually temporary — retry next day.

### Cloud Run scaling failure (max instances hit)
**Behavior:** Requests queue. Latency spikes. Error rate may not spike immediately.
**User impact:** Slow response or timeout on new requests.
**Auto-recovery:** Auto-scales as soon as capacity is available. Usually self-resolves unless max_instances is the bottleneck.
**Action:** P1 if sustained >5 minutes. Check if max_instances limit needs increasing (`gcloud run services update api-server --max-instances=20`). Check if a specific endpoint is consuming disproportionate resources (likely itinerary generation endpoint — it's the most expensive path).

---

## Security Runbook

### Unusual API traffic
Signs: request rate 10x normal, identical user agents, high rate of 4xx on scraping-pattern URLs.
Action: check Cloud Armor (if enabled) for block rules. Rate-limit by IP at the Cloud Run ingress level if needed. Log anomaly — check if it's a competitor scraping ActivityNode data.

### Coordinated venue pumping detected
The data sanitation layer flags this automatically (coordinated pumping detector). Admin tooling surfaces flagged accounts.
Action: quarantine affected venue signals (not the ActivityNode — just new signals). Human review of flagged accounts. If confirmed: ban accounts, remove contributed signals, trigger Pipeline C recrawl of affected venues.

### Account deletion cascade stalled
The privacy deletion cascade anonymizes behavioral signals rather than hard-deleting them (group contribution preservation). If a cascade stalls, the user has requested deletion but their signals aren't being processed.
Action: check `deletion_cascades` table for stalled records. Manual re-trigger via admin tooling. SLA: deletion cascade must complete within 30 days of request (GDPR requirement even for US-only users — good practice to hold to this standard).

---

## Health Check Endpoint Spec

Every service exposes `/health` (liveness) and `/ready` (readiness).

```python
@app.get("/health")
def health():
    return {"status": "ok", "service": "api-server", "version": VERSION}

@app.get("/ready")
def ready():
    checks = {}
    
    # Check Postgres
    try:
        db.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"
    
    # Check Redis
    try:
        redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
    
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=status_code
    )
```

Cloud Run uses `/ready` for startup probe and liveness probe. A 503 from `/ready` means Cloud Run won't route traffic to this instance. This is the correct behavior — if Postgres is down, no traffic should come here.

---

## Monthly Operational Checklist

- [ ] Review LLM cost trend — is cost/recommendation decreasing as cache fills?
- [ ] Check Places API usage — approaching free tier ceiling?
- [ ] Run city graduation query — any cities ready for Tier 1 upgrade?
- [ ] Check ML shadow mode results — any models ready for promotion gate?
- [ ] Review error rate trends — any slow-building issues?
- [ ] Check Postgres disk utilization — on track for upgrade timeline?
- [ ] Review job_runs table — any chronic failures or slow jobs?
- [ ] Audit Redis eviction metrics — any evictions in past 30 days?
- [ ] Check coordinated pumping detector — any flagged venues?
- [ ] Review blog source freshness dashboard — any sources not crawled in 2x expected cadence?

---

*Overplanned Internal · February 2026*
*This playbook should be reviewed after every P1 incident and updated with new failure modes as they're discovered. Living document.*
