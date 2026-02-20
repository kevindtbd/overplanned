# Overplanned — Admin Tooling

*Internal Reference · February 2026*

---

## Overview

Admin tooling is gated behind `system_role = 'admin'` via the RBAC layer. `get_effective_tier()` always returns `lifetime` for admin accounts — access is enforced at the application layer, not the DB. All surfaces described here are invisible to standard users.

Five surface areas. Priority order reflects build sequence.

---

## 1. ML Model Management

Highest-leverage surface. Built around the `model_registry` table.

**Model lifecycle control** — promote models through `staging → a_b_test → production → archived`. A unique index enforces exactly one production model per `model_name` at any time. Admin UI is the only promotion path.

**A/B test monitoring** — every recommendation logs `X-Model-Version` in the response header and behavioral signal. Admin view shows per-version metrics side by side:

| Model | Key Metrics |
|---|---|
| `ranking_model` | nDCG@10, MRR, coverage |
| `pivot_acceptance_model` | AUC, precision@3 |
| `persona_dimension_tagger` | label_accuracy, dimension_mae |

Kill an underperforming variant before it causes trust damage. Promote via UI, not script.

**Training data inspection** — view nightly extraction job output. Check signal distributions (completions vs. skips vs. pivots). Flag anomalies before they enter a training run.

---

## 2. City Seeding Control (On-Demand)

Admin triggers city seeding for any city globally — primarily used for international cities and Tier 2 graduations on behalf of users.

### Flow

```
Admin inputs city → Job configuration → Scrape & normalize →
Pre-enrichment validation → ML scoring → LLM batch enrichment (async) →
Post-enrichment quality gate → DB commit → Cache invalidation
```

### Stage Detail

**Job configuration** — city name resolves to canonical identifier (country code, region, regional platform mappings: Tokyo → Tabelog, Seoul → Naver, Shanghai → Dianping). Source priorities and node count target optionally configurable.

**Scrape & normalize (non-LLM blitz)** — Reddit PRAW pull, Google Places API grid sweep, curated blog RSS crawl, regional platform scrapes (rate-limited). Everything writes to raw GCS logs as `CityTierEvent`. No scoring yet.

**Pre-enrichment validation gate** — runs before any LLM spend:
- Node count threshold (enough candidates to justify batch cost?)
- Deduplication (same venue from 3 sources = 1 node)
- Structural checks (coordinates, name, at least one source attribution)

Failures are held out of the enrichment batch. LLM does not spend tokens on malformed records.

**ML scoring** — deterministic pass before LLM:
- Cross-reference convergence scoring (`convergence_score` on `CrossReferenceSignal`)
- Overrated detector — local vs. tourist platform divergence captured before any narrative is attached
- Source authority scoring

ML output is a scored, structured feature set. LLM consumes this, not raw noise.

**LLM enrichment (async, Haiku batch)** — ~$4–8/city at batch pricing. Strictly tag extraction and narrative scaffolding:
- Vibe tags from community text
- Persona dimension signals
- Local tip extraction from high-authority community posts

Job runs in background. Admin sees status: `Queued → Scraping → Scoring → Enriching → Review / Complete`. No blocking.

**Post-enrichment quality gate:**
- `vibe_confidence < 0.4` → flagged for human review, not auto-committed
- Tag distribution sanity check — >80% of city nodes sharing a top tag indicates upstream problem
- Local/tourist divergence conflict check — LLM enthusiasm vs. ML overrated flag surfaces for review

**DB commit** — atomic per-city. Calls `graduate_city_to_tier1(city)` directly, bypassing the organic graduation threshold. Writes `seeding_job` audit record: admin ID, timestamp, node counts per stage, flagged vs. auto-committed, LLM batch cost.

### Admin UI States

```
[ Queued ]  →  [ Scraping ]  →  [ Scoring ]  →  [ Enriching ]  →  [ Review (X flagged) / Complete ]
```

Review queue shows: node, conflict description, and three actions — Accept, Reject, Re-tag manually. Accepted nodes commit immediately. Rejected nodes stay out of DB but raw data persists in GCS for future backfill.

### Cost Per City

| Item | Cost |
|---|---|
| Scraping | ~$0 |
| LLM batch extraction (Haiku) | $4–8 |
| Cloud Vision validation | ~$1.50/1K images |
| **Total per city** | **~$6–13** |

---

## 3. Activity & Source Intelligence Management

**Activity node review queue** — nodes flagged as low-confidence by the source authority scorer surface here. Manual verify or reject. Critical during bootstrap when LLM extraction quality varies across sources.

**Overrated detector tuning** — view cross-reference scores between tourist-heavy and local platforms. Adjust thresholds. Manually flag venues as `tourist_trap` or `authentic_local` to inject ground truth labels into training.

**Source freshness dashboard** — last scraped timestamp per source. Alert when a source hasn't updated in N days. Trigger manual re-scrapes.

---

## 4. User & Behavioral Graph Oversight

**User lookup** — search by user ID. View persona dimension scores, behavioral signal history, active trips.

**Recommendation explainability** — for any recommendation event: model version that scored it, features that drove the score, source of the activity, persona dimensions targeted. Ground truth for debugging "why did we recommend X."

**Deletion & privacy cascade management** — view cascade state for account deletions: behavioral signals anonymized, group contributions scrubbed, training data quarantined. Manual override if a cascade stalls.

**Commercial import flagging** — accounts flagged by the coordinated pumping detector. View cluster signals, confirm or clear flag, see which venues are affected and their quarantine status.

---

## 5. Trust & Safety

**Shared trip token monitoring** — tokens with anomalous view/import rates (>500 views/hour, >50 imports/day). Revoke tokens, flag accounts directly.

**Owner tip injection attempts** — accounts flagged for URL injection in `owner_tip` field. Hard-stripped server-side at write time; admin sees flagged accounts with context.

---

## 6. Operational Observability

**Pipeline health** — nightly extraction job status, training data export success/failure, vector DB indexing lag, Cloud Run service health.

**Bootstrap progress** — percentage of recommendations served by LLM vs. ML ranker. North star metric for cold start graduation. Target: >80% ML-ranked = bootstrapped.

**Cost dashboard** — LLM call volume, cost per recommendation, trend over time. Tight loop on this keeps the self-hosted, cost-recovery-first approach intact.

---

## Build Priority

| Priority | Surface | Reason |
|---|---|---|
| 1 | ML model registry + promotion UI | Can't safely deploy ML without it |
| 2 | Recommendation explainability | Catch bad recs before user churn |
| 3 | City seeding control | Bootstrap quality requires human-in-the-loop |
| 4 | User lookup + persona inspector | Debug individual recommendation failures |
| 5 | Pipeline health + cost dashboard | Operational visibility |
| 6 | Trust & safety surfaces | Needed before significant user volume |

---

## Access Control

All admin routes require `system_role = 'admin'` checked via `can_access(user, 'admin_dashboard')`. Admin implies `lifetime` tier via `get_effective_tier()` — no separate entitlement needed. See RBAC doc for full schema.

---

*Overplanned Internal · February 2026*
