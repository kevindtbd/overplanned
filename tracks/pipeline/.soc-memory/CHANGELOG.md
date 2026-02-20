# Data Pipeline Track — Changelog

## [M-000] COMMIT - 2026-02-20 13:52:01
Base scraper framework complete with retry, backoff, dead letter queue, rate limiting, and alerting. All 20 unit tests pass, verifying retry fires on 500 errors, dead letter queue handles permanent failures, and rate limiting works correctly.
### Verified
- [x] services/api/scrapers/base.py
- [x] services/api/scrapers/__init__.py
- [x] tests/api/scrapers/test_base.py
- [x] services/__init__.py
- [x] services/api/__init__.py
- [x] tests/__init__.py
- [x] tests/api/__init__.py
- [x] tests/api/scrapers/__init__.py

## [M-002] COMMIT - 2026-02-20 13:53:17
Atlas Obscura HTML scraper producing ActivityNode rows with hidden_gem QualitySignals. Follows BaseScraper contract, uses rate limiting and retry. Stages results in-memory for pipeline orchestrator consumption.
### Verified
- [x] services/api/scrapers/atlas_obscura.py

## [M-003] COMMIT - 2026-02-20 13:53:39
Foursquare Places API v3 client implementing BaseScraper contract with category mapping (70+ FSQ categories → 11 ActivityCategory), daily quota tracking (950/day), and structured output matching ActivityNode + QualitySignal schemas.
### Verified
- [x] services/api/scrapers/foursquare.py

## [M-001] COMMIT - 2026-02-20 13:54:09
Blog RSS scraper implementing BaseScraper contract. Parses 10 curated feeds (Infatuation primary), classifies signal types, deduplicates via content hash, stores QualitySignal rows with correct authority scores. Uses sentinel activityNodeId for M-005 entity resolution downstream.
### Verified
- [x] services/api/scrapers/blog_rss.py

## [M-004] COMMIT - 2026-02-20 13:56:22
Arctic Shift Reddit Parquet batch loader implementing BaseScraper interface. Reads historical archive dumps, extracts venue mentions from travel subreddits via regex patterns, computes authority scores from Reddit upvotes + subreddit weight, and produces QualitySignal rows for Tokyo/Kyoto/Osaka venues.
### Verified
- [x] services/api/scrapers/arctic_shift.py

## [M-005] COMMIT - 2026-02-20 13:58:44
### Verified
- [x] services/api/pipeline/__init__.py
- [x] services/api/pipeline/entity_resolution.py

## [M-007] COMMIT - 2026-02-20 14:00:03
Deterministic category→vibe tag mapping for all 11 ActivityCategory values. Pure function compute_tags_for_node for unit testing, async run_rule_inference for batch DB application. Writes source='rule_inference' per M-007 spec. Idempotent via upsert.
### Verified
- [x] services/api/pipeline/rule_inference.py

## [M-006] COMMIT - 2026-02-20 14:00:59
Created vibe extraction service that classifies ActivityNodes via Claude Haiku against the locked 42-tag vocabulary. Processes in batches of 10, validates against vocabulary, enforces 0.75 threshold, resolves contradictory tag pairs, writes to ActivityNodeVibeTag, and logs every batch to ModelRegistry with full cost/latency metrics.
### Verified
- [x] services/api/pipeline/vibe_extraction.py

## [M-008] COMMIT - 2026-02-20 14:02:09
Created convergence scoring service with cross-source agreement detection and source authority weighting. Multi-source nodes score higher on both convergence (unique source count / 3) and authority (weighted average of source quality).
### Verified
- [x] services/api/pipeline/convergence.py

## [M-009] COMMIT - 2026-02-20 14:04:12
Created qdrant_sync.py with full/incremental/specific sync modes, embedding text construction, Qdrant collection management, parity validation, and stats tracking. Uses foundation EmbeddingService via injection and matches foundation QdrantSearchClient payload contract.
### Verified
- [x] services/api/pipeline/qdrant_sync.py

## [M-010] COMMIT - 2026-02-20 14:06:33
End-to-end city seeder orchestrating all 6 pipeline steps with checkpoint/resume via JSON progress file. Each step calls the existing module APIs (scrapers, entity_resolution, vibe_extraction, rule_inference, convergence, qdrant_sync) in sequence, tracking per-step status and aggregate counters.
### Verified
- [x] services/api/pipeline/city_seeder.py

## [M-012] COMMIT - 2026-02-20 14:07:34
Compliance cron job that nulls QualitySignal.rawExcerpt for Reddit sources older than 30 days, using batched updates to avoid lock contention. All derived scoring/tagging data is untouched.
### Verified
- [x] services/api/pipeline/content_purge.py

## [M-011] COMMIT - 2026-02-20 14:08:56
Image validation pipeline step with 4-source waterfall, Cloud Vision quality/safety checks, lightweight fallback, and concurrency-controlled batch processing.
### Verified
- [x] services/api/pipeline/image_validation.py

## [M-013] COMMIT_CONFLICT - 2026-02-20 14:15:10
141 tests all green covering scrapers (unit), entity resolution (integration), pipeline integration, checkpoint/resume, LLM cost logging, content purge, and convergence scoring. Well exceeds the 25+ test minimum.
### Verified
- [x] services/api/tests/__init__.py
- [x] services/api/tests/pipeline/__init__.py
- [x] services/api/tests/pipeline/conftest.py
- [x] services/api/tests/pipeline/test_scrapers.py
- [x] services/api/tests/pipeline/test_entity_resolution.py
- [x] services/api/tests/pipeline/test_pipeline_integration.py
- [x] services/api/tests/pipeline/test_checkpoint.py
- [x] services/api/tests/pipeline/test_cost_logging.py
- [x] services/api/tests/pipeline/test_content_purge.py
- [x] services/api/tests/pipeline/test_convergence.py
- [x] services/api/pipeline/vibe_extraction.py
### CONFLICT (claimed by another task)
- [!] services/api/pipeline/vibe_extraction.py
