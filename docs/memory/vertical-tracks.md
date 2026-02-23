# 7 Vertical SOC Tracks

## Dependency Graph
```
Foundation (1) → Data Pipeline (2) → [Solo(3), Group(4), MidTrip(5), PostTrip(6), Admin(7)]
                                      ↑ all parallel after Pipeline lands
```

Minor cross-deps within parallel tier:
- Mid-Trip (5) extends Solo Trip (3) components
- Group Trip (4) extends Solo Trip (3) components
- Post-Trip (6) reads trip state from 3/4/5
- Admin (7) reads from everything, nothing depends on it

## Track 1: Foundation
- Prisma schema (all core tables)
- NextAuth.js + Google OAuth
- RBAC columns (subscription_tier, system_role, feature_flags, access_cohort)
- Next.js App Router shell + design system (Tailwind tokens from HTML refs)
- Docker compose (Postgres 16 + Qdrant)
- Codegen pipeline (Prisma → JSON Schema → Pydantic + TS)
- FastAPI skeleton with health check
- GCP Cloud Run deploy skeleton
- Sentry instrumentation

## Track 2: Data Pipeline
- Blog RSS scrapers (curated seed list, authority scores)
- Atlas Obscura scraper
- Foursquare Places API integration (950 free calls/day)
- Arctic Shift Reddit archive loader
- LLM vibe tag extraction (Haiku batch)
- Rule-based vibe inference (category→tag map)
- Cross-reference convergence scorer
- Source authority scorer
- Qdrant collection setup + loader
- City seeding jobs (13 launch cities)
- Image validation pipeline (Cloud Vision)
- Content hash dedup (SHA256)

## Track 3: Solo Trip
- Onboarding flow (fork: plan trip vs inspiration)
- Trip DNA collection (pace, mornings, food chips)
- Preset templates + persona seeding
- Itinerary generation (LLM-based ranking → cached)
- Itinerary reveal animation
- Day view (timeline, slots, map strip)
- Map view (sidebar + canvas, pins, popups)
- Calendar view + .ics export
- Offline swipe deck (40 nodes, 1.5km radius, zero LLM)
- Slot card component (photo, vibe chips, booking badges)
- Discover/explore surface (cold start, shortlist, returning user)

## Track 4: Group Trip
- Invite flow (link, persona seed questions, no-account join)
- Group planning (async voting, camps, conflict resolution)
- Fairness engine (debt tracking, invisible rebalancing)
- Group social surface (pulse line, energy bars, moments)
- Subgroup split logic
- Group affinity matrix
- Group logistics (shared items, constraints, pre-purchased)
- Abilene paradox detection ("not for me" dissent path)
- Shared trip links (/s/:token_id)

## Track 5: Mid-Trip
- PivotEvent system (5 trigger types, latency budgets)
- Pivot drawer UI (swap cards, alternatives, feedback)
- Cascade evaluation (selective re-solve)
- Mood signal detection (passive + active)
- Context drift guard (MAX_PIVOT_DEPTH=1)
- Micro-stops (proximity nudge worker, GIST spatial index)
- Prompt bar (NLP input, chips)
- Push notifications (morning briefing)
- Trust recovery (flag sheet, two resolution paths)

## Track 6: Post-Trip
- Post-trip reflection screen
- Highlight rating (loved/skipped/missed)
- Photo strip + memory layer
- Feedback capture (single question)
- Visited map (read-only)
- Shared trip artifact (public page)
- Re-engagement hook (next destination suggestion)
- 24hr push + 7-day email
- Behavioral signal disambiguation (planned-but-skipped vs went-and-disliked)

## Track 7: Admin
- ML model registry + promotion UI (staging → a/b_test → production → archived)
- A/B test monitoring (per-version metrics)
- City seeding control (admin-triggered, job pipeline UI)
- Activity node review queue (low-confidence flags)
- Source freshness dashboard
- User lookup + persona inspector
- Recommendation explainability
- Trust & safety (shared trip tokens, injection detection)
- Pipeline health + cost dashboard
- Bootstrap progress metric (LLM vs ML %)

## Each Track's Internal SOC Structure
Every track decomposes horizontally:
- M-001: Schema / Prisma migrations
- M-002: API endpoints (FastAPI or Next.js API routes)
- M-003: Frontend components (Next.js + Tailwind)
- M-004: Unit + integration tests
- M-005: E2E wiring + contract validation
