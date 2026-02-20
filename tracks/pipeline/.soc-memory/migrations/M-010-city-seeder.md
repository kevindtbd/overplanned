# M-010: City Seeding Orchestrator

## Description
End-to-end orchestrator that seeds a city with all data sources, resolves entities, tags, scores, and syncs to Qdrant.

## Task
Create services/api/pipeline/city_seeder.py:
- Pipeline steps (in order):
  1. Run all scrapers for city (blog, atlas, foursquare, reddit)
  2. Entity resolution (incremental mode for new nodes)
  3. LLM vibe extraction (untagged nodes)
  4. Rule-based vibe inference
  5. Convergence + authority scoring
  6. Qdrant sync (incremental)

- Checkpoint/resume:
  - Track per-step completion in a progress table or JSON file
  - On crash: restart from last completed step
  - Each step is idempotent (safe to re-run)

- Progress tracking per city:
  - nodes_scraped, nodes_resolved, nodes_tagged, nodes_indexed
  - Status: pending | in_progress | completed | failed

- 13 launch cities from docs/overplanned-city-seeding-strategy.md

Deliverable: seed 1 city end-to-end with checkpoint/resume. All tables + Qdrant populated.

## Output
services/api/pipeline/city_seeder.py

## Zone
orchestrator

## Dependencies
- M-009

## Priority
40

## Target Files
- services/api/pipeline/city_seeder.py

## Files
- services/api/scrapers/
- services/api/pipeline/entity_resolution.py
- services/api/pipeline/vibe_extraction.py
- services/api/pipeline/rule_inference.py
- services/api/pipeline/convergence.py
- services/api/pipeline/qdrant_sync.py
- docs/overplanned-city-seeding-strategy.md
- docs/plans/vertical-plans-v2.md
