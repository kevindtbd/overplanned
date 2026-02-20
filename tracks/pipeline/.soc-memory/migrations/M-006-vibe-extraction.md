# M-006: LLM Vibe Tag Extraction

## Description
Use Haiku to classify ActivityNodes into vibe tags from the 42-tag vocabulary.

## Task
Create services/api/pipeline/vibe_extraction.py:
- Haiku classification prompt: raw text (name + description + quality signals) → vibe tags with scores
- Structured JSON output (Anthropic JSON mode): only valid tags from 42-tag vocabulary
- Score clamping: all scores between 0.0 and 1.0
- Batch processing: queue untagged ActivityNodes, process in batches of 10
- Write to ActivityNodeVibeTag with source: "llm_extraction"
- Prompt versioned in ModelRegistry
- Log per batch: model_version, prompt_version, latency, estimated cost (input tokens * rate + output tokens * rate)
- Rate limiting: respect Haiku API limits
- Max 5 vibe tags per node per source

Deliverable: run extraction on 50 nodes → vibe tags populated, costs + model version logged in ModelRegistry.

## Output
services/api/pipeline/vibe_extraction.py

## Zone
tagging

## Dependencies
- M-005

## Priority
60

## Target Files
- services/api/pipeline/vibe_extraction.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
