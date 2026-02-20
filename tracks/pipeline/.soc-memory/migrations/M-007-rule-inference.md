# M-007: Rule-Based Vibe Inference

## Description
Apply deterministic category → vibe tag mapping rules. Baseline vibe tags for all nodes regardless of LLM availability.

## Task
Create services/api/pipeline/rule_inference.py:
- Rules config (JSON or Python dict): category → list of (vibeTag, score) mappings
  - nightlife → [("late-night", 0.9), ("high-energy", 0.7)]
  - dining + priceLevel >= 4 → [("splurge", 0.8)]
  - outdoors → [("fresh-air", 0.9)]
  - culture → [("deep-dive", 0.7)]
  - etc. for all 11 categories
- Write to ActivityNodeVibeTag with source: "rule_inference"
- Don't overwrite existing LLM-extracted tags (additive only)
- Runs after entity resolution, before convergence scoring

Deliverable: all ActivityNodes with a category get baseline vibe tags from rules.

## Output
services/api/pipeline/rule_inference.py

## Zone
tagging

## Dependencies
- M-005

## Priority
55

## Target Files
- services/api/pipeline/rule_inference.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
