# M-002: Itinerary Generation

## Description
Core generation engine: query Qdrant, rank with LLM, assign to time slots, with triple fallback cascade.

## Task
Create services/api/generation/:

1. Generation pipeline:
   - Query Qdrant via ActivitySearchService with persona-weighted vector
   - LLM ranking (Sonnet): personaSeed + candidate nodes → ranked slots
   - Slot assignment rules: anchors first (must-do items), flex around them, meals at mealtimes (12-1pm lunch, 7-8pm dinner)
   - Write ItinerarySlot rows linked to ActivityNodes
   - Log full candidate set to RawEvent (entire ranked pool, not just selected items — critical for training)
   - Register prompt version in ModelRegistry

2. Triple fallback cascade:
   - Primary: Sonnet LLM ranking (timeout: 5s)
   - Fallback 1 (LLM timeout): deterministic ranking by convergenceScore × persona_match_score, skip narrative descriptions
   - Fallback 2 (Qdrant timeout 3s): Postgres query with category + city + priceLevel filter
   - Fallback 3 (both down): cached template itinerary for destination

3. Set Trip.generationMethod: "llm" | "deterministic_fallback" | "template_fallback"

4. POST /generate endpoint with Trip ID

## Output
services/api/generation/engine.py

## Zone
generation

## Dependencies
- M-001

## Priority
95

## Target Files
- services/api/generation/engine.py
- services/api/generation/ranker.py
- services/api/generation/slot_assigner.py
- services/api/generation/fallbacks.py
- services/api/routers/generate.py

## Files
- services/api/search/service.py
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
