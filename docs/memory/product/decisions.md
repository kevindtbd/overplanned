# Product / Locked Decisions & Anti-Patterns

## Locked Decisions
- 34+ Prisma models (TripLeg, BackfillLeg added)
- Tech: Next.js 14, FastAPI, Postgres 16+PostGIS, Redis 7, Qdrant, PgBouncer
- Embedding: nomic-embed-text-v1.5 (768 dim, Apache 2.0, local inference)
- Auth: Google OAuth only, DB sessions (not JWT), max 30d/7d idle
- Design: 3 fonts (Sora + DM Mono + Lora), Terracotta #C4694F, warm tokens, SVG only, no emoji
- Ink scale INVERTED: ink-100 = darkest, ink-900 = lightest
- No TripAdvisor/Yelp as primary recommendation sources
- No demographic profiling
- No emoji anywhere

## Anti-Patterns
- No column without a data source
- Don't abstract for payment providers you don't use
- Don't create stubs without design docs
- Settings sections that don't connect to product features are theater
- Never collapse per-source quality signals to single score

## Open Docs
- `docs/overplanned-open-decisions.md`
- `docs/overplanned-open-questions-deepdive.md`

## Learnings
- (space for future compound learnings)
