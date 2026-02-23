# ML / LLM Usage & Patterns

## Model Selection
- claude-sonnet-4-6 — Generation, enrichment, complex NLP
- claude-haiku-4-5-20251001 — Classification, vibe tag extraction, lightweight tasks

## LLM-as-Interface Philosophy
- LLMs parse input (NLP) and narrate output (descriptions, summaries)
- LLMs do NOT make recommendation decisions
- All LLM calls log: model version, prompt version, latency, cost estimate
- Model registry tracks: staging -> a/b_test -> production -> archived

## Bootstrap Transition (LLM -> ML)
- See `docs/overplanned-bootstrap-deepdive.md` for full strategy
- LLM handles cold-start, ML takes over as behavioral data accumulates
- Admin dashboard tracks bootstrap progress (LLM vs ML %)

## Cost Tracking
- Pipeline health + cost dashboard in admin
- Per-call cost estimates logged
- Haiku for high-volume classification to minimize cost

## Learnings
- (space for future compound learnings)
