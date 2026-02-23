# ML Vertical — Memory Bank

## Sub-topic Files
- `generation.md` — Itinerary generation, scoring, slot placement, LLM enrichment
- `signals.md` — Behavioral modeling, persona, three-layer signal architecture
- `embeddings.md` — Qdrant, nomic-embed-text, vector search, city seeding
- `training-data.md` — Synthetic data generation, BPR-ready pipeline
- `city-seeding.md` — City seeding strategy, launch cities, activity nodes
- `llm-usage.md` — Prompt patterns, model selection, cost tracking, LLM->ML transition

## Architecture Principles
- ML + LLM at the edges, deterministic logic in the middle
- LLMs are interface layers (input parsing, output narration) NOT decision-makers
- All recommendation decisions logged as behavioral_signals
- Every LLM call logs: model version, prompt version, latency, cost estimate
- Three layers: User Graph (behavioral) / Trip State (real-time) / World Knowledge (Qdrant)
