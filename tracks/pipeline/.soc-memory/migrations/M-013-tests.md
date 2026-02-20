# M-013: Pipeline Tests

## Description
Comprehensive test suite for the entire data pipeline.

## Task
Create tests in services/api/tests/pipeline/:

1. **Unit tests per scraper** (test_scrapers.py):
   - Mock HTTP responses for each scraper
   - Verify retry on 500, dead letter on permanent failure
   - Rate limiting verification
   - Correct QualitySignal output format

2. **Entity resolution integration** (test_entity_resolution.py):
   - 3-source dedup: Foursquare + blog + Atlas Obscura for same venue → 1 canonical node
   - CJK normalization: Japanese venue names resolved correctly
   - Chain stores at different locations: don't merge (different coordinates)
   - Merge preserves all signals: QualitySignals transferred to canonical node
   - Alias creation verified

3. **Pipeline integration** (test_pipeline_integration.py):
   - Full 1-city pipeline: scrape → resolve → tag → score → Qdrant
   - Qdrant parity: Postgres canonical count == Qdrant count

4. **Checkpoint/resume** (test_checkpoint.py):
   - Simulate crash mid-pipeline → restart → verify resumes from correct step

5. **LLM cost logging** (test_cost_logging.py):
   - Every Haiku call logged with model_version, prompt_version, latency, cost

6. **Content purge** (test_content_purge.py):
   - rawExcerpt null after 30 days
   - VibeTags and scores preserved

7. **Convergence scoring** (test_convergence.py):
   - Multi-source nodes > single-source nodes

Deliverable: pytest services/api/tests/pipeline/ all green, 25+ tests.

## Output
services/api/tests/pipeline/conftest.py

## Zone
tests

## Dependencies
- M-012

## Priority
20

## Target Files
- services/api/tests/pipeline/conftest.py
- services/api/tests/pipeline/test_scrapers.py
- services/api/tests/pipeline/test_entity_resolution.py
- services/api/tests/pipeline/test_pipeline_integration.py
- services/api/tests/pipeline/test_checkpoint.py
- services/api/tests/pipeline/test_cost_logging.py
- services/api/tests/pipeline/test_content_purge.py
- services/api/tests/pipeline/test_convergence.py

## Files
- services/api/scrapers/
- services/api/pipeline/
- docs/plans/vertical-plans-v2.md
