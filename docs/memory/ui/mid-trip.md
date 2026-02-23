# UI / Mid-Trip

## Components
- `PivotDrawer.tsx` — Pivot/swap drawer UI
- `SwapCard.tsx` — Alternative activity cards
- `PromptBar.tsx` — NLP input -> LLM parse -> structured trigger
- `FlagSheet.tsx` — Trust issue flagging
- `ResolutionPicker.tsx` — Two resolution paths for trust recovery

## Patterns
- PivotEvent system: 5 trigger types (weather, venue closed, time overrun, user mood, manual)
- Cascade evaluation: selective re-solve downstream
- Context drift guard: MAX_PIVOT_DEPTH=1
- Micro-stops: proximity nudge, GIST spatial index

## Learnings
- (space for future compound learnings)
