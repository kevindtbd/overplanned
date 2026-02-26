# Pipeline D — Deepen Plan Review Notes

*Date: 2026-02-26*
*Reviewer: deepen-plan*
*Plan: docs/plans/2026-02-26-pipeline-d-llm-research-synthesis-design.md*

---

## Critical Gaps (must address before implementation)

### 1. GCS raw content store doesn't exist
- `gcs_raw_store.py` only stores `raw_places/` and `geocoded_venues/`
- Full-text content (Reddit threads, blog posts, Atlas entries, editorial) is NOT persisted
- **Fix**: New GCS prefix `research_bundles/{city_slug}/` with JSONL per source type
- **Impact**: Becomes a prerequisite step — scrapers must persist full text before Pipeline C extraction
- Common envelope: `{source_type, source_id, title, body, score, upvote_ratio, is_local, scraped_at}`

### 2. Venue name resolver is simpler than stated
- Plan says "reuses entity_resolution.py 4-tier cascade" but only 2 tiers fire
- Pipeline D has no coordinates or external IDs — only venue name strings
- **Fix**: Simplified 2-tier resolver (exact + fuzzy/substring) for v1
- `unresolved_research_signals` table catches misses for later enrichment pipeline
- Schema already supports retry (`resolutionAttempts`, `lastAttemptAt`)

### 3. No AggregatedCorpusSignal exists
- Cross-ref scorer spec assumes a separate Pipeline C aggregation record
- Reality: convergence.py writes directly to ActivityNode fields
- **Fix**: Cross-ref scorer reconstructs C signal from ActivityNode (`convergenceScore`, `tourist_score`, `vibe_confidence`) + QualitySignal mention count queries
- Not a blocker, just different data access pattern than spec implies

---

## Design Refinements

### 4. Trimmed bundle per Pass B batch (cost -60-70%)
- Problem: full 40K bundle repeated in every batch = 450-500K input tokens for large cities
- Fix: Pass A synthesis IS the cached city-wide context (~3-5K tokens)
- Each batch gets: Pass A synthesis + only source snippets mentioning those 50 venues + venue list
- Per-batch: ~10-15K tokens instead of 45-50K
- Large city cost: ~$3.85 → ~$1.50

### 5. Dry-run mode for canary
- `--dry-run` flag: runs Steps 1-6 fully, skips Step 7 (ActivityNode write-back)
- All D results land in their own tables (ResearchJob, VenueResearchSignal, CrossReferenceResult)
- Diff report: join cross_reference_results against activity_nodes, show old-vs-new per field
- `--apply-write-back` commits after admin review
- Use for Bend canary, then switch to write-through for production

---

## Decisions Confirmed

### 6. Regular API (not batch) for both passes
- Sync API calls for simplicity
- Batch API is a one-line optimization later
- Don't over-engineer orchestration for ~$0.75/city savings
- Pipeline runs infrequently (admin seed + quarterly refresh)

### 7. Dynamic VibeTag vocabulary
- Query `VibeTag WHERE isActive=true` at bundle assembly time
- Inject into Pass B prompt dynamically
- Single source of truth — no drift if tags added/removed

---

## Roadmap Items Identified
- **Enrichment pipeline**: geocoding for unresolved Pipeline D venues → enables full 4-tier resolution
- **Batch API migration**: switch Pass B to batch API if quarterly refresh costs add up
- **AggregatedCorpusSignal table**: if cross-ref scorer performance becomes an issue, materialize C aggregation

---

## Updated Implementation Sequence

Original Step 2 (Source bundle assembler) now has a prerequisite:

| Step | What | Depends on | Note |
|------|------|-----------|------|
| 0 | GCS raw content persistence (expand gcs_raw_store.py) | Existing scrapers | **NEW — prerequisite for bundle assembly** |
| 1 | Schema migration (5 tables + ActivityNode columns + RankingEvent fields) | Nothing | |
| 2 | Source bundle assembler | Step 0 + GCS store | Reads from new research_bundles/ prefix |
| 3 | Pass A prompt + parser | Schema + bundle | |
| 4 | Pass B prompt + parser (with batching + trimmed bundle) | Pass A | **Updated: trimmed bundle per batch** |
| 5 | Validation gate | Pass A + B parsers | |
| 6 | Venue name resolver (simplified 2-tier) | Schema | **Updated: exact + fuzzy only** |
| 7 | Cross-reference scorer | Schema + resolver | **Updated: reads C from ActivityNode fields** |
| 8 | ActivityNode write-back (with --dry-run) | Cross-ref scorer | **Updated: dry-run mode** |
| 9 | RankingEvent feature additions | Schema | |
| 10 | Admin UI (job log + conflict queue) | Schema + write-back | |
| 11 | Canary: Bend backfill (dry-run) | Everything above | **Updated: dry-run first, then apply** |
| 12 | Scale to remaining cities | Canary passes | |
