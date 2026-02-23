# ML / Generation Engine

## Architecture
- Hybrid: deterministic scoring/placement first, async LLM enrichment after HTTP response
- Fire-and-forget: LLM enrichment failure = no-op, deterministic itinerary stands alone
- Pace -> slots/day: packed=6, moderate=4, relaxed=2
- Diversity cap: no single category > 1/3 of total slots

## Key Files
- `lib/generation/generate-itinerary.ts` — Main generation pipeline
- `lib/generation/scoring.ts` — Activity scoring algorithm
- `lib/generation/slot-placement.ts` — Temporal slot placement
- `lib/generation/llm-enrichment.ts` — Async LLM description enrichment
- `lib/generation/promote-draft.ts` — Draft -> active with generation
- `lib/generation/transit-suggestion.ts` — Inter-leg transit suggestions
- `lib/generation/types.ts` — Generation type definitions

## Functions
- `generateLegItinerary` — Per-leg generation
- `generateTripItinerary` — Multi-leg orchestrator

## LLM Models
- claude-sonnet-4-6 for generation/enrichment
- claude-haiku-4-5-20251001 for classification tasks

## Learnings
- Module-level `new Anthropic()` throws in jsdom — needs vi.mock before import in tests
