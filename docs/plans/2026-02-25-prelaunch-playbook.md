# Overplanned Pre-Launch Playbook

*Imported from overplanned-prelaunch-playbook.docx — February 2026*
*Data seeding + behavioral scaffolding before the first user hits the page*

## Overview

Two tracks run in parallel:
1. **TRACK 1 — Behavioral Scaffolding**: Schema migrations, signal taxonomy, logging infra, nightly jobs
2. **TRACK 2 — Data Seeding**: Corpus collection, LLM batch extraction, LLM fallback pipeline

Behavioral scaffolding first. If a user hits the app before candidateSetId and the write-back columns exist, that signal is gone permanently.

---

## TRACK 1 — Behavioral Scaffolding

### Phase 0 — Schema Migrations (BEFORE any user creates a trip)

| Step | What | Why |
|------|------|-----|
| 0.1 | `candidateSetId` + `candidate_ids` on BehavioralSignal | BPR negative examples — most critical missing piece |
| 0.2 | ActivityNode behavioral write-back columns (`impression_count`, `acceptance_count`, `llm_served_count`, `ml_served_count`, `behavioral_quality_score`, `behavioral_updated_at`) | User behavior as ranking feature |
| 0.3 | RawEvent extraction checkpoint (`training_extracted`, `extracted_at`) | Purge gate — never delete before extraction |
| 0.4 | `card_view_duration_ms` on RankingEvent payload (client-side) | 300ms dismiss != 7s dismiss |
| 0.5 | Weather context on RankingEvent payload (city-level) | Per-user weather resilience signal |

### Phase 1 — Signal Taxonomy & Logging Infrastructure

| Step | What | Why |
|------|------|-----|
| 1.1 | Signal hierarchy (high to low quality) | Training weight by confidence |
| 1.2 | RankingEvent core logging schema | Primary training data source |
| 1.3 | Persona dimension snapshot in RankingEvent | Denormalize at write time — can't reconstruct later |
| 1.4 | Pre-trip slot modification signals (`pre_trip_slot_swap`, `pre_trip_slot_removed`, `pre_trip_slot_added`, `pre_trip_reorder`) | Direct quality signal on initial generation |

### Phase 2 — Nightly Jobs (3am UTC)

| Step | What | Schedule |
|------|------|----------|
| 2.1 | Training data extraction → GCS Parquet | 3:00am UTC |
| 2.2 | Behavioral write-back (impression/acceptance → ActivityNode) | 3:15am UTC |
| 2.3 | Persona dimension updater (EMA, mid-trip 3x weight) | 3:30am UTC |

---

## TRACK 2 — Data Seeding

### Phase 3 — Corpus Collection ($0)

| Step | What | Source |
|------|------|--------|
| 3.1 | City scope: Bend (canary), Tacoma, Nashville, Portland, Austin, Denver, + Bangkok, Mexico City, Barcelona | Pre-seeded via full pipeline |
| 3.2 | Reddit — Arctic Shift | Primary, free, quality filter (upvote_ratio > 0.70 AND score > 10), local override flag |
| 3.3 | Editorial sources — RSS first | Rate limit 1 req/2 sec. Never: TripAdvisor, Thrillist, Lonely Planet, Culture Trip |

### Phase 4 — LLM Batch Extraction (~$130 one-time)

| Step | What | Detail |
|------|------|--------|
| 4.1 | Controlled 60-tag vibe vocabulary | No free-form tagging — extraction failures if tags outside vocab |
| 4.2 | Extraction output schema (per venue mention) | Structured JSON only, never prose |
| 4.3 | Aggregation → ActivityNode | overrated consensus (>40%), cross_ref_confidence (3+ sources), vibe_confidence (harmonic mean) |
| 4.4 | Cost & canary strategy | **Bend + Tacoma first** — validate pipeline before large cities |

### Phase 5 — LLM Fallback Pipeline (Any Unknown City)

| Step | What | Detail |
|------|------|--------|
| 5.1 | Architecture: Google Places + LLM enrichment | Quality bar: better than Googling |
| 5.2 | LLM enrichment prompt | Controlled vibe vocab, honest data_confidence, no venue identity bias |
| 5.3 | DB write-back from demand | Every unseen city → real ActivityNodes. Flywheel. |

---

## Launch Readiness Checklist

Behavioral scaffolding = **non-negotiable** (permanently lost training data).
Data seeding = **quality** (LLM fallback covers gaps).
