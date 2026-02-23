# 7 Vertical SOC Plans (62 Migrations Total)

## Track 1: Foundation (8 migrations) — BLOCKS ALL
- M-001: Prisma schema (all 16 models) + Docker + seed (42 vibe tags, test user)
- M-002: Codegen pipeline (Prisma→JSON Schema→Pydantic+TS+Qdrant) + CI guard
- M-003: NextAuth.js + Google OAuth + RBAC (getEffectiveTier, FEATURE_GATES, middleware)
- M-004: App shell + design system (Tailwind tokens, fonts, mobile nav, desktop layout, responsive)
- M-005: FastAPI skeleton (health check, generated Pydantic models, CORS, Sentry)
- M-006: Monorepo wiring (workspaces, packages/schemas, packages/shared-types, packages/db)
- M-007: Deploy skeleton (Dockerfiles, Cloud Run config, env management)
- M-008: Tests + E2E wiring (Jest, Pytest, Playwright, test DB, auth smoke test)

Integration: exports to all tracks, imports from none.

## Track 2: Data Pipeline (12 migrations) — BLOCKS 3-7
- M-001: Blog RSS scrapers (seed list, authority scores → QualitySignal)
- M-002: Atlas Obscura scraper (HTML → ActivityNode + hidden_gem signal)
- M-003: Foursquare Places API (950/day → ActivityNode with foursquareId)
- M-004: Entity resolution pipeline (canonical name + dedup chain + ActivityAlias)
- M-005: LLM vibe tag extraction (Haiku batch → ActivityNodeVibeTag, costs logged)
- M-006: Rule-based vibe inference (category→tag map → ActivityNodeVibeTag)
- M-007: Convergence scorer + authority scorer (cross-ref → update ActivityNode scores)
- M-008: Qdrant sync + embedding (generate vectors, load collection, sync job)
- M-009: City seeding orchestrator (run all steps per city, 13 launch cities)
- M-010: Image validation pipeline (Cloud Vision, 4-tier waterfall)
- M-011: Content purge job (rawExcerpt > 30 days → null, compliance)
- M-012: Tests (unit per scraper, integration entity resolution, full pipeline 1 city)

Integration: writes ActivityNode/VibeTag/QualitySignal/Alias/Qdrant. Reads nothing from 3-7.

## Track 3: Solo Trip (10 migrations) — parallel after Pipeline
- M-001: Onboarding flow (fork, trip creation, Trip DNA, presets, personaSeed)
- M-002: Itinerary generation (Qdrant search + LLM ranking → ItinerarySlots, candidate_set RawEvent)
- M-003: Itinerary reveal animation (loading → progressive reveal → day view)
- M-004: Day view (timeline, slot cards, day navigation, status indicators)
- M-005: Slot card component (reusable, photo/vibes/actions, BehavioralSignal + RawEvent emit)
- M-006: Map view (desktop sidebar+canvas, mobile full-screen+sheet, pins by slotType)
- M-007: Discover/explore (cold start, personalized, shortlist, swipe deck, signals)
- M-008: Calendar view + .ics export
- M-009: RawEvent integration (sessionId, impression tracking, batch send, all surfaces emit)
- M-010: Tests (unit slot card, integration onboard→generate→view, E2E full flow, signal validation)

Integration: reads ActivityNode/Qdrant, writes Trip/Slot/BehavioralSignal/RawEvent. Slot card + map reused by Track 4/5.

## Track 4: Group Trip (7 migrations) — parallel, extends Track 3 components
- M-001: Schema extension (Trip group cols, Slot voteState/isContested, TripMember persona/energy)
- M-002: Invite flow (link gen, landing page, no-account join, organizer view)
- M-003: Group planning / async voting (vote states, camp detection, conflict resolution)
- M-004: Fairness engine (debt tracking, invisible rebalancing, Abilene paradox detection)
- M-005: Group social surface (pulse line, energy bars, moments, affinity matrix, subgroup split)
- M-006: Shared trip links (/s/:token, read-only, commercial protection)
- M-007: Tests (unit voting/fairness, integration invite→vote→resolve, E2E 3 members)

Integration: extends Foundation schema, reuses Solo components, writes same signal tables.

## Track 5: Mid-Trip (8 migrations) — parallel, extends Track 3 components
- M-001: Schema extension (Slot swap/pivot cols, PivotEvent now writeable)
- M-002: Pivot trigger detection (weather, venue closed, time overrun, user mood)
- M-003: Pivot drawer UI (swap cards, accept/reject/expire, signals)
- M-004: Cascade evaluation (selective re-solve, timing updates downstream)
- M-005: Micro-stops (proximity nudge, GIST index, lightweight flex slots)
- M-006: Prompt bar (NLP input → LLM parse → structured trigger)
- M-007: Trust recovery (flag sheet, two resolution paths, IntentionSignal explicit)
- M-008: Tests (unit triggers/cascade/proximity, integration pivot chain, E2E active trip)

Integration: extends Slot schema, writes PivotEvent, reads Qdrant for alternatives, writes signals.

## Track 6: Post-Trip (7 migrations) — parallel
- M-001: Trip completion trigger (auto on endDate or manual)
- M-002: Post-trip reflection (highlight rating, feedback question, signals + IntentionSignals)
- M-003: Photo strip + memory layer (upload, visited map, summary card)
- M-004: Shared trip artifact (public memory page)
- M-005: Re-engagement loop (next destination, 24hr push, 7-day email via Resend)
- M-006: Signal disambiguation batch (post_skipped → match context → IntentionSignal with confidence)
- M-007: Tests (unit completion/disambiguation, integration full post-trip, E2E lifecycle)

Integration: reads Trip/Slot/Signals from earlier tracks. Writes BehavioralSignal + IntentionSignal.

## Track 7: Admin (8 migrations) — parallel, lowest priority
- M-001: Admin auth guard + layout
- M-002: Model registry UI (list, promote, metrics, compare)
- M-003: City seeding control (trigger jobs, progress dashboard)
- M-004: Activity node review queue (flagged nodes, approve/edit/archive, alias mgmt)
- M-005: Source freshness dashboard (last scrape, alerts, authority management)
- M-006: User lookup + persona inspector (search, signals, trips, feature flag overrides)
- M-007: Pipeline health + cost dashboard (LLM costs, API calls, job rates)
- M-008: Tests (unit auth/promotion, integration admin actions, E2E all surfaces)

Integration: read-only all tables. Writes ModelRegistry, ActivityNode status, User feature flags.
