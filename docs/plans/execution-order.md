# Overplanned — SOC Execution Order

## Structure
7 separate SOC projects. Each track is its own conductor run.
Manual review + course-correction between tracks.

## Locked Decisions
- 22 Prisma models (schema-revisions.md has additions over original 16)
- Tech: Next.js 14, FastAPI, Postgres 16 + PostGIS, Redis 7, Qdrant, PgBouncer
- Embedding: nomic-embed-text-v1.5 (768 dim, Apache 2.0, local)
- Auth: Google OAuth only, database-backed sessions, no JWT
- No-account join: KILLED — must sign up
- IntentionSignal: training feature for ranking model
- Offline mode: descoped to Track 3 v2
- Design system: LOCKED (Sora + DM Mono, Terracotta #C4694F, warm tokens)
- Contract system: Prisma → JSON Schema → Pydantic + TS + Qdrant config
- Phase 2 items: 26 deferred (see phase-2-and-non-mvp-sidebar.md)

## Dependency Graph
```
Phase 1:  Foundation (Track 1)         — 12 migrations, BLOCKS ALL
Phase 2:  Data Pipeline (Track 2)      — 14 migrations, BLOCKS 3-7 for data
          Admin (Track 7)              — 9 migrations, PARALLEL from Foundation
Phase 3:  Solo Trip (Track 3)          — 11 migrations, core components block 4/5/6
Phase 4:  Group Trip (Track 4)         — 8 migrations, UI needs Solo core
          Mid-Trip (Track 5)           — 9 migrations, UI needs Solo core
Phase 5:  Post-Trip (Track 6)          — 8 migrations, reads from 3/4/5
```

## Execution Sequence

### Phase 1: Foundation (Track 1) — RUN FIRST
```
Project: tracks/foundation/
Migrations: 12 (M-001 through M-012)
Workers: 3-5 (migrations are mostly sequential)
Estimated scope: Docker, 22-model Prisma schema, codegen, auth, app shell,
                 FastAPI, monorepo, deploy, ActivitySearchService, embedding,
                 tests, merge protocol
Exit criteria: docker compose up healthy, prisma studio shows all tables,
               codegen chain works, auth flow complete, both services build
```

### Phase 2a: Data Pipeline (Track 2) — AFTER Foundation
```
Project: tracks/pipeline/
Migrations: 14 (M-000 through M-013)
Workers: 3-5 (some scrapers can parallel, but most are sequential)
Estimated scope: Scraper framework, 4 sources (blog/atlas/foursquare/reddit),
                 entity resolution, vibe extraction, scoring, Qdrant sync,
                 city seeding, image validation, content purge, tests
Exit criteria: seed 1 city end-to-end, Qdrant search returns hydrated results,
               entity resolution deduplicates cross-source, all tests green
```

### Phase 2b: Admin (Track 7) — PARALLEL with Pipeline (after Foundation)
```
Project: tracks/admin/
Migrations: 9 (M-001 through M-009)
Workers: 3-5
Estimated scope: Admin auth + AuditLog, model registry, city seeding control,
                 node review, source freshness, user lookup, pipeline costs,
                 trust & safety, tests
Exit criteria: admin surfaces functional, all actions logged to AuditLog,
               promotion safety gate enforced
```

### Phase 3: Solo Trip (Track 3) — AFTER Pipeline
```
Project: tracks/solo/
Migrations: 11 (M-001 through M-011)
Workers: 3-5
Estimated scope: Onboarding, itinerary generation (with fallbacks), reveal,
                 day view, slot card (SHARED), map view, RawEvent integration,
                 discover, calendar, shadow training tests, E2E
Exit criteria: full solo trip lifecycle works, shadow training data validates,
               slot card + map + day view ready for reuse by Track 4/5
```

### Phase 4a: Group Trip (Track 4) — AFTER Solo M-006
```
Project: tracks/group/
Migrations: 8 (M-001 through M-008)
Workers: 3-5
Estimated scope: Schema extension, invite flow, group generation, voting,
                 fairness engine, shared links, group social, tests
Exit criteria: group trip lifecycle works, fairness rebalancing verified,
               invite/share token security tested
```

### Phase 4b: Mid-Trip (Track 5) — PARALLEL with Group (after Solo M-006)
```
Project: tracks/midtrip/
Migrations: 9 (M-001 through M-009)
Workers: 3-5
Estimated scope: Schema extension, weather service, pivot triggers, pivot drawer,
                 cascade evaluation, micro-stops (PostGIS), prompt bar,
                 trust recovery, tests
Exit criteria: pivot flow works end-to-end, cascade is same-day only,
               prompt bar injection-safe, all tests green
```

### Phase 5: Post-Trip (Track 6) — AFTER Solo, can overlap late Phase 4
```
Project: tracks/posttrip/
Migrations: 8 (M-001 through M-008)
Workers: 3-5
Estimated scope: Completion trigger, reflection, IntentionSignal feedback,
                 disambiguation batch, photo strip, shared artifact,
                 re-engagement (push + email), tests
Exit criteria: trip completion timezone-correct, disambiguation rules produce
               correct IntentionSignals, push + email fire on schedule
```

### Phase 6: Cross-Track Test Suite — AFTER ALL TRACKS
```
Location: tests/cross-track/ (not a separate SOC project — manual or CI)
Files: 6 test files + conftest
Scope: signal flow, schema extension, entity→itinerary, pivot→posttrip,
       admin reads all
Exit criteria: all cross-track tests green on merged main
```

## Between-Phase Review Protocol
After each phase completes:
1. Review conductor output + CHANGELOG
2. Run all existing tests (regression gate)
3. Check if any plan revisions needed for next phase
4. Course-correct before starting next SOC run

## Totals
| Phase | Track(s) | Migrations | Parallel? |
|-------|----------|-----------|-----------|
| 1 | Foundation | 12 | — |
| 2a | Pipeline | 14 | Yes (with 2b) |
| 2b | Admin | 9 | Yes (with 2a) |
| 3 | Solo | 11 | — |
| 4a | Group | 8 | Yes (with 4b) |
| 4b | Mid-Trip | 9 | Yes (with 4a) |
| 5 | Post-Trip | 8 | — |
| 6 | Cross-Track | 6 files | — |
| **Total** | **7 tracks** | **71 migrations** | |
