# Deepening Findings (27 Gaps + 5 Cross-Track Issues)

## Track 1: Foundation
1. M-001 too monolithic — split into 4 focused sub-migrations (core/signals/pipeline/future-shells)
2. M-006 monorepo tool unspecified — decision: npm workspaces (Turborepo later)
3. No RawEvent ingestion endpoint — Foundation M-005 needs `/events/batch`
4. M-008 tests too vague — must validate codegen CI guard, not just "1 test each"
5. Font loading: Lora should lazy-load (only detail views/post-trip), not every page
6. No env var validation — add zod (Next.js) + pydantic-settings (FastAPI)

## Track 2: Data Pipeline
7. No scraper error handling framework — add M-000: base scraper with retry/backoff/dead-letter/alerting
8. Entity resolution ordering — needs full-table sweep mode, not just incremental
9. **No Arctic Shift / Reddit integration** — Tier 1 signal source missing entirely. Add M-002b.
10. Embedding model unspecified — need explicit decision (OpenAI text-embedding-3-small vs open source)
11. M-009 city seeding needs checkpoint/resume — orchestrator with per-step restart
12. Entity resolution test gap — need 3-source dedup test (Foursquare + blog + Atlas Obscura)

## Track 3: Solo Trip
13. M-002 itinerary generation has no fallback — LLM timeout needs template-based fallback
14. M-005 slot card depends on event emitter (M-009) — reorder or extract shared utility earlier
15. **Offline mode not in plan** — docs describe it, plan ignores it. Explicit descope needed.
16. Discover feed "personalization" undefined — at launch it's Qdrant vector + rules, not ML
17. Shadow training validation buried in E2E — needs its own dedicated contract test file

## Track 4: Group Trip
18. No-account join auth model undefined — ephemeral sessions vs require signup. Needs decision.
19. Fairness engine has no concrete algorithm — define debt_delta formula, make it testable
20. **Group itinerary generation missing** — N members' personaSeeds + fairness = different gen than solo

## Track 5: Mid-Trip
21. Weather polling should be per-city cached, not per-trip — share across trips in same city
22. Cascade evaluation scope undefined — define: same-day only, cross-day = new pivot event
23. GIST index needs PostGIS — Prisma doesn't support, needs raw SQL migration
24. Prompt bar LLM parsing has no latency budget — Haiku, 1.5s, fallback to keyword match
25. **Push notification infra homeless** — needed by Track 5, 6, maybe 4. Not in any track.

## Track 6: Post-Trip
26. Auto-completion timezone problem — Trip needs `timezone` field. endDate without timezone = wrong trigger.
27. Push dependency on Track 5 infra — soft dep not captured
28. Disambiguation rules need concrete config — not ad-hoc if/else, a testable rules table
29. Post-trip feedback must be able to override slot status (completed→skipped)

## Track 7: Admin
30. Model promotion needs safety gate — metrics comparison required, no blind promote
31. **No audit log** — admin actions need AuditLog model (append-only, who/what/when)
32. No cost alerting — thresholds per pipeline stage, alert on exceed

## Cross-Track Issues
CT-1: Migration conflicts when parallel tracks extend same table — branch + PR + rebase strategy
CT-2: Push notification infra homeless — move to Foundation M-007b
CT-3: Trip.timezone missing — affects Mid-Trip, Post-Trip, Solo Trip. Add to Foundation schema.
CT-4: PostGIS dependency — needed by Track 5 + Track 2. Move to Foundation docker + initial migration.
CT-5: Offline mode descoped but not acknowledged — make explicit: "post-MVP, Track 3 v2"
