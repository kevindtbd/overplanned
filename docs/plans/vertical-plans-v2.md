# Overplanned — Vertical SOC Plans v2 (Revised)
Post agent review (architect + security + test-engineer). All gaps addressed.

## Dependency Graph (CORRECTED)
```
Foundation (1) ──→ Pipeline (2) ──→ Solo (3) M-001→M-007 [core components]
                                         │
                                         ├──→ Group (4) UI migrations
                                         ├──→ MidTrip (5) UI migrations
                                         └──→ PostTrip (6)

                   Admin (7) ──→ parallel from Foundation (reads everything, blocks nothing)
```

Track 4/5 schema migrations (their M-001s) CAN start after Foundation.
Track 4/5 UI migrations REQUIRE Solo(3) core components (slot card, day view, map).
PostTrip(6) reads from 3/4/5.
Admin(7) truly parallel.

## Schema: 22 Models
User, Session, Account, VerificationToken, Trip, TripMember, ItinerarySlot,
ActivityNode, ActivityNodeVibeTag, VibeTag, ActivityAlias, QualitySignal,
BehavioralSignal, IntentionSignal, RawEvent, ModelRegistry, PivotEvent,
SharedTripToken, InviteToken, AuditLog

---

## Track 1: Foundation (12 migrations) — BLOCKS ALL

### M-001: Docker + PostGIS + Redis
- docker-compose.yml: Postgres 16, Redis 7, Qdrant (API key auth), PgBouncer
- All services bound to 127.0.0.1
- Env var substitution with required flags (no hardcoded passwords)
- Enable PostGIS extension in Postgres (needed by Track 2 entity resolution + Track 5 micro-stops)
- .env.example with all required vars documented
- Deliverable: `docker compose up` → all 4 services healthy, `SELECT PostGIS_version()` returns

### M-002: Prisma Schema (22 models)
- Full schema.prisma with all 22 models and enums
- Split into logical migration groups:
  - 002a: core (User, Session, Account, VerificationToken, Trip, TripMember, ItinerarySlot)
  - 002b: world knowledge (ActivityNode, VibeTag, ActivityNodeVibeTag, ActivityAlias, QualitySignal)
  - 002c: signals (BehavioralSignal + indexes, IntentionSignal, RawEvent + clientEventId unique)
  - 002d: ml + admin (ModelRegistry + artifactHash, PivotEvent, AuditLog)
  - 002e: tokens (SharedTripToken, InviteToken)
- Seed script: 42 vibe tags from vibe-tags.json, test user (beta tier), test admin
- Deliverable: `npx prisma studio` shows all tables, seed data present

### M-003: Codegen Pipeline
- Write codegen specification doc FIRST (maps every Prisma type/modifier to JSON Schema output)
  - Explicit decisions: Json fields → per-field schema override, String[] → array, optionals, enums
- scripts/prisma-to-jsonschema.ts (~100 LOC, implements spec)
- scripts/jsonschema-to-qdrant.ts (~50 LOC)
- Wire datamodel-code-generator (pip) → Pydantic output at services/api/models/generated.py
- Wire json-schema-to-typescript (npm) → TS API types at packages/shared-types/api.ts
- npm run codegen runs the full chain
- CI guard: GitHub Action diffs generated files, fails if stale
- Deliverable: change Prisma model → run codegen → Pydantic + TS + Qdrant all update

### M-004: Auth + Session Management
- NextAuth.js with Google OAuth (database-backed sessions, NOT JWT)
- Session config: max lifetime 30 days, idle timeout 7 days
- Concurrent session limit: 5 per user
- getEffectiveTier() utility
- FEATURE_GATES config constant
- Auth middleware for Next.js API routes
- Protected route wrapper component
- User.lastActiveAt updated via middleware on every authenticated request
- Deliverable: Google login → session row in DB → user row with beta tier → session expires correctly

### M-005: App Shell + Design System
- Tailwind config with all design tokens mapped to CSS custom properties
- Global CSS with :root vars (light + dark mode)
- Font loading: Sora + DM Mono via next/font (eager). Lora lazy-loaded (detail views only).
- Mobile nav shell: Home / Trips / Explore / Profile
- Desktop layout: sidebar + main + context panel
- Responsive breakpoint: mobile-first, desktop at 1024px
- Env var validation: zod schema for Next.js env
- Security headers middleware (CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- Deliverable: empty shell with nav, correct fonts/colors, responsive, security headers present

### M-006: FastAPI Skeleton
- Project structure under services/api/
- Health check endpoint (/health) with API envelope
- Generated Pydantic models wired in
- CORS: restrict to overplanned.app + dev URLs only (no wildcards)
- Sentry instrumentation (server-side only, before_send strips auth headers)
- Env var validation: pydantic-settings
- Rate limiting middleware (Redis-backed): 60 req/min authenticated, 10 req/min anon
- LLM-triggering endpoints: 5 req/min per user
- /events/batch endpoint for RawEvent ingestion (accepts buffered events, ON CONFLICT DO NOTHING for clientEventId dedup)
- Request body size limit: 1MB default
- Deliverable: curl localhost:8000/health → 200 with envelope, rate limits enforced

### M-007: Monorepo Wiring
- npm workspaces for packages/* and apps/*
- packages/schemas/ with generated JSON Schemas
- packages/shared-types/ with generated TS types (API boundary shapes, no relations)
- packages/db/ with Prisma schema + client
- ESLint rule: no @prisma/client imports in apps/web/ (frontend uses shared-types only)
- Makefile for polyglot build orchestration (npm codegen + Python codegen in one command)
- Deliverable: apps/web imports from @overplanned/shared-types, types resolve, ESLint enforced

### M-008: Deploy Skeleton
- Dockerfile for Next.js (multi-stage, non-root user, pinned base image)
- Dockerfile for FastAPI (multi-stage, non-root user, pinned base image)
- GCP Cloud Run config / cloudbuild.yaml
- FastAPI deployed as internal-only service (no public ingress, IAM authenticated by Next.js service)
- Env management: GCP Secret Manager references for all API keys in prod
- Deliverable: both services build as Docker images, health checks pass, non-root verified

### M-009: ActivitySearchService
- Reusable FastAPI service: Qdrant vector search → Postgres batch hydration → merge
- Consumed by: itinerary generation, discover, pivot alternatives, micro-stops
- Handles: nomic-embed-text-v1.5 embedding generation (768 dim, local inference)
- sentence-transformers installed, model auto-downloads (~270MB)
- Deliverable: search("quiet coffee shop", city="austin") → hydrated ActivityNode results

### M-010: Embedding Infrastructure
- nomic-embed-text-v1.5 model wrapper in FastAPI
- Batch embedding endpoint for pipeline use
- Single query embedding for search use
- Model registered in ModelRegistry (type: "embedding", version: "nomic-v1.5")
- Deliverable: embed text → 768-dim vector, batch of 100 texts embeds under 5s

### M-011: Tests + E2E Wiring
- Jest config for Next.js, Pytest config for FastAPI, Playwright setup
- docker-compose.test.yml (Postgres on RAM disk, Qdrant with tmpfs, Redis)
- Conftest with testcontainers (auto-provision test DB)
- Codegen contract tests: per-model schema parity (Prisma ↔ JSON Schema ↔ Pydantic ↔ TS)
- Enum sync test: SignalType values match across all stacks
- CI guard test: modify Prisma → run codegen check → assert fails if stale
- Auth tests: RBAC tiers, session lifecycle, concurrent session limit
- API envelope tests: success/error/paginated shapes, requestId present, modelVersion on ML responses
- Env var validation tests: missing vars → clear startup crash
- Rate limiting tests: verify limits enforced per tier
- Fixture factory pattern: one factory per core model with nullable extension fields
- Signal invariant helper: assert_signal_integrity(db) — reusable across all tracks
- Smoke E2E: Google OAuth mock → session → protected route → logout
- Deliverable: npm test + pytest + npx playwright test all green, 20+ tests minimum

### M-012: Migration Merge Protocol
- Document schema staging branch strategy for parallel track extensions
- PR template for schema changes (must run codegen, must pass contract tests)
- Regression gate: all track tests run on every PR to main
- Deliverable: CONTRIBUTING.md with schema change protocol

Integration: exports to all tracks, imports from none. Redis, PgBouncer, Qdrant auth, PostGIS all available.

---

## Track 2: Data Pipeline (14 migrations) — BLOCKS 3-7

### M-000: Scraper Framework
- Base scraper class with: retry (exponential backoff, max 3), dead letter queue, rate limiting, respectful User-Agent
- Source registry table pattern: name, URL, authority score, scrape frequency, last_scraped_at
- Alert hook: 3+ consecutive failures → log warning (Sentry alert in prod)
- Deliverable: base class tested with mock HTTP, retry and dead letter verified

### M-001: Blog RSS Scrapers
- RSS feed parser using base scraper framework
- Seed list from docs/overplanned-blog-sources.md
- Output: raw content → QualitySignal rows + temporary rawExcerpt
- Deliverable: scrape The Infatuation → QualitySignal rows in DB, authority scores populated

### M-002: Atlas Obscura Scraper
- HTML scraper using base framework
- Extract: name, coordinates, description, hidden-gem signal
- Map to ActivityNode with status: pending
- Deliverable: scrape 1 city → ActivityNode rows with hidden_gem QualitySignals

### M-003: Foursquare Places Integration
- Foursquare Places API client (950 free calls/day)
- Search by city + category
- Map to ActivityNode: name, coordinates, price, hours, category, foursquareId
- Deliverable: query "restaurants in Austin" → ActivityNode rows with Foursquare IDs

### M-004: Arctic Shift Reddit Loader
- Download Parquet dumps for target travel subreddits (r/JapanTravel, r/solotravel, etc.)
- Parse posts/comments → extract travel recommendations
- Feed into LLM extraction pipeline (same as blog content)
- Batch job pattern (not live scraper — historical archive)
- Deliverable: load r/JapanTravel archive → QualitySignal rows for Tokyo/Kyoto/Osaka venues

### M-005: Entity Resolution Pipeline
- Canonical name normalization (lowercase, strip punctuation, CJK handling)
- Resolution chain: external ID match → geocode proximity (<50m) + same category → fuzzy name (trigram)
- Tiebreaker: when external IDs conflict, geocode proximity wins
- Merge logic: set resolvedToId, isCanonical: false, create ActivityAlias, migrate QualitySignals to canonical
- Full-table sweep mode + incremental mode (sweep catches retroactive dupes)
- PostGIS spatial query for proximity check
- Deliverable: scrape same venue from 3 sources → single canonical node, all signals preserved

### M-006: LLM Vibe Tag Extraction
- Haiku classification prompt: raw text → vibe tags with scores
- Structured output (JSON mode, fixed schema): only valid tags from 42-tag vocabulary
- Score clamping to [0, 1]
- Batch processing: queue of untagged ActivityNodes
- Write to ActivityNodeVibeTag with source: "llm_extraction"
- Prompt versioned in ModelRegistry, cost logged per batch
- Deliverable: run extraction on 50 nodes → vibe tags populated, costs + model version logged

### M-007: Rule-Based Vibe Inference
- Category → tag mapping rules (nightclub → late-night + high-energy, etc.)
- Write to ActivityNodeVibeTag with source: "rule_inference"
- Runs after entity resolution, before convergence scoring
- Deliverable: all ActivityNodes with a category get baseline vibe tags

### M-008: Convergence Scorer + Authority Scorer
- Cross-reference: 3+ sources agree on vibe tag → score increases
- Authority weighting: The Infatuation > random blog
- Update ActivityNode.convergenceScore and authorityScore
- Deliverable: multi-source nodes show higher convergence than single-source

### M-009: Qdrant Sync + Embedding
- Generate embeddings via nomic-embed-text-v1.5 (768 dim, local) using ActivitySearchService from Foundation M-009
- Load to Qdrant activity_nodes collection with payload fields
- Qdrant API key auth on all calls
- Sync job: detect changed nodes in Postgres, re-embed, upsert
- is_canonical: true filter validated on every query
- Deliverable: vector search "quiet coffee shop in Austin" returns relevant hydrated nodes

### M-010: City Seeding Orchestrator
- Given a city, runs: scrapers → entity resolution → tagging → scoring → Qdrant sync
- Checkpoint/resume: per-step completion tracking, restart from last completed step on failure
- 13 launch cities from docs/overplanned-city-seeding-strategy.md
- Progress tracking per city (nodes scraped, resolved, tagged, indexed)
- Deliverable: seed 1 city end-to-end with checkpoint/resume, all tables + Qdrant populated

### M-011: Image Validation Pipeline
- Cloud Vision API: quality check, inappropriate content detection
- 4-tier waterfall: Unsplash → Foursquare → Google → none
- Set imageValidated: true on pass
- Deliverable: nodes with images validated, bad images flagged

### M-012: Content Purge Job
- Scheduled: delete QualitySignal.rawExcerpt where extractedAt > 30 days
- Compliance requirement (Reddit addendum)
- Deliverable: cron runs, old excerpts nulled, vibe tags + scores preserved

### M-013: Tests
- Unit tests per scraper (mock HTTP, retry verification, dead letter)
- Entity resolution integration: 3-source dedup (Foursquare + blog + Atlas Obscura)
- Entity resolution edge cases: CJK normalization, chain stores at different locations, merge preserves signals
- Full pipeline integration: 1 city end-to-end (scrape → resolve → tag → score → Qdrant)
- Qdrant parity: pg count == qdrant count for seeded city
- Checkpoint/resume: simulate crash mid-pipeline, verify restart
- LLM cost logging: every Haiku call logged with model_version, prompt_version, latency, cost
- Content purge: rawExcerpt null after 30 days
- Deliverable: pytest services/api/tests/pipeline/ all green, 25+ tests

Integration: writes ActivityNode, VibeTag junction, QualitySignal, Alias, Qdrant. Reads nothing from 3-7.

---

## Track 3: Solo Trip (11 migrations) — core components block 4/5

### M-001: Onboarding Flow
- Fork screen: "Plan a trip" vs "Just exploring"
- Trip creation: destination, dates, trip name
- Timezone auto-populated from destination city (IANA format)
- Trip DNA: pace, morning preference, food chips
- Preset templates: "Foodie Weekend", "Culture Deep Dive", "Adventure", "Chill"
- Write Trip + TripMember rows, personaSeed JSON
- Deliverable: complete onboarding → Trip row with timezone + personaSeed, TripMember with organizer role

### M-002: Itinerary Generation
- Query Qdrant via ActivitySearchService with persona-weighted vector
- LLM-based ranking (Sonnet): personaSeed + candidates → ranked slots
- Slot assignment: anchors first, flex around them, meals at mealtimes
- Write ItinerarySlot rows linked to ActivityNodes
- Log candidate set to RawEvent (full ranked pool, not just selected)
- Register prompt version in ModelRegistry
- Fallback on LLM timeout (5s): deterministic ranking by convergenceScore × persona_match, skip narrative
- Fallback on Qdrant timeout (3s): Postgres query (category + city + priceLevel filter)
- Fallback on both down: cached template itinerary for destination
- Generation method flag on Trip: "llm" | "deterministic_fallback" | "template_fallback"
- Deliverable: create trip → itinerary generated, candidate_set RawEvent logged, fallback tested

### M-003: Itinerary Reveal Animation
- Loading state during generation
- Progressive reveal: slots appear one by one
- Transition to day view on completion
- Deliverable: generation → loading → reveal → day view

### M-004: Day View
- Timeline layout per day
- Slot cards: photo, name, vibe chips, time, duration
- Day navigation (swipe or tabs)
- Status indicators (confirmed, proposed, completed)
- Deliverable: generated itinerary renders as day-by-day timeline

### M-005: Slot Card Component (SHARED — used by Track 4/5)
- Reusable component
- Photo, activity name, vibe tag chips, booking badge placeholder
- Confirm / skip / lock actions
- Write BehavioralSignal on every deliberate action
- Deliverable: slot card renders, actions fire structured signals

### M-006: Map View
- Desktop: sidebar list + map canvas
- Mobile: full-screen map with bottom sheet
- Pins colored by slotType
- Pin tap → slot detail popup
- Day filter
- Deliverable: map shows all slots with correct pins

### M-007: RawEvent Integration (BEFORE discover — emitter needed first)
- Frontend event emitter: sessionId generation (UUID on app open)
- Impression tracking: every card entering viewport = implicit RawEvent
- Dwell time capture, scroll depth, navigation events
- intentClass tagging (explicit/implicit/contextual)
- Batch send: buffer events, flush every 5s or on navigation
- clientEventId generated on device for dedup
- All surfaces emit: day view, map, detail card
- Deliverable: browse app 60 seconds → 50+ RawEvents with correct intentClass + sessionId

### M-008: Discover/Explore Surface
- Cold start: trending in city, editorial picks
- Returning user: Qdrant vector search weighted by behavioral signals (rules, not ML at launch)
- Shortlist: save activities for later
- Swipe deck (online only at MVP — offline descoped to v2)
- Write BehavioralSignal for every swipe/shortlist/remove
- Write RawEvent impressions with position for every item shown
- Deliverable: discover feed loads, interactions captured, impressions include position data

### M-009: Calendar View + .ics Export
- Calendar grid showing trip days
- .ics generation with correct VTIMEZONE (uses Trip.timezone)
- Deliverable: view trip as calendar, download .ics opens correctly in native calendar app

### M-010: Shadow Training Validation Tests
- Dedicated test file: tests/shadow_training/test_training_data_quality.py
- Positive pair tests: confirm/complete/loved → valid positives with activityNodeId
- Explicit negative tests: skip/swipe_left/disliked → valid negatives
- Implicit negative tests: impression without tap = implicit negative
- Candidate set tests: generation logs full ranked pool (rejected > selected)
- Position bias tests: impression events include position field
- Session sequence tests: events ordered within session
- Signal integrity: assert_signal_integrity(db) after full flow
- Deliverable: shadow training suite green, training data pipeline validated end-to-end

### M-011: E2E + Integration Tests
- Unit: slot card rendering, vibe chip display, signal emission
- Integration: onboarding → generation → day view renders correct slots
- E2E (Playwright): login → onboard → generate → view → interact → signals verified
- Fallback test: mock LLM timeout → verify template fallback fires
- Deliverable: all suites green, 30+ tests

Integration: reads ActivityNode/Qdrant (Pipeline), writes Trip/Slot/BehavioralSignal/IntentionSignal/RawEvent. Slot card + map + day view reused by Track 4/5.

---

## Track 4: Group Trip (8 migrations) — UI work after Solo(3) M-006

### M-001: Schema Extension (can start after Foundation, before Solo completes)
- Add to Trip: fairnessState Json?, affinityMatrix Json?, logisticsState Json?
- Add to ItinerarySlot: voteState Json?, isContested Boolean @default(false)
- Add to TripMember: personaSeed Json?, energyProfile Json?
- Prisma migration, codegen runs, all track tests still pass
- Deliverable: migration applied, existing Track 3 tests unbroken

### M-002: Invite Flow (requires Google OAuth signup)
- InviteToken generation (crypto.randomBytes(32), base64url)
- Default: single-use, 7-day expiry, role: member (never organizer)
- Organizer view: see active tokens, revoke, view usage
- Invite landing page: shows trip preview → "Sign in with Google to join"
- On join: create TripMember row, increment InviteToken.usedCount
- Reject if token expired, revoked, or maxUses reached
- Deliverable: create invite → share link → recipient signs in → joins trip → token used count incremented

### M-003: Group Itinerary Generation
- N members' personaSeeds → weighted vector for Qdrant search
- Fairness-weighted ranking: balance across member preferences
- Same fallback cascade as solo (LLM timeout → deterministic → template)
- Candidate set logged to RawEvent with all member preference scores
- Deliverable: group trip with 3 members → itinerary reflects all preferences, not just organizer

### M-004: Async Voting
- Slot voting UI (uses Track 3 slot card component)
- Vote states: propose → vote → confirm/contest
- Camp detection: when members split on a slot
- Conflict resolution: show alternatives, re-vote
- Update ItinerarySlot.voteState and isContested
- Deliverable: 2+ members vote on slots, contested slots flagged

### M-005: Fairness Engine
- Algorithm: debt_delta = member_preference_rank - group_choice_rank per member per vote
- Accumulate debt per member in Trip.fairnessState
- Next conflict: weight alternatives by inverse cumulative debt (most-compromised gets boosted)
- Abilene paradox detection: if all votes are lukewarm (enthusiasm < 0.4), trigger dissent prompt
- Deterministic: same input → same output (testable)
- Deliverable: 5+ votes → debt scores diverge, rebalancing visible, Abilene detection fires on unanimous lukewarm

### M-006: Shared Trip Links
- SharedTripToken generation (crypto.randomBytes(32), base64url, 90-day default expiry)
- Public page /s/:token — read-only itinerary, no auth required
- Rate limit: 30/min per IP, identical 404 for nonexistent and revoked tokens
- XSS prevention: HTML entity encoding on all user-provided content (owner tips, display names)
- CSP on shared pages: script-src 'none'
- Commercial protection: no affiliate links, no booking redirects
- Deliverable: share link → public page renders, XSS payloads rejected, revocation works

### M-007: Group Social Surface (requires Solo core components)
- Pulse line, energy bars, moments
- Group affinity matrix visualization
- Subgroup split suggestions
- Deliverable: mid-trip dashboard shows group state

### M-008: Tests
- Unit: voting logic, fairness debt_delta calculation, camp detection, Abilene paradox, token generation/validation
- Integration: invite → signup → join → vote → resolve → fairness updates correctly
- Integration: SharedTripToken create → view → expire → revoke
- E2E: full group trip lifecycle with 3 members, fairness rebalancing verified
- Token security: expired tokens rejected, revoked tokens rejected, max uses enforced
- Cross-track: Track 3 slot card works in group context, signals still write correctly
- Deliverable: all green, 25+ tests

Integration: extends Foundation schema, reuses Solo components, writes same signal tables. InviteToken and SharedTripToken for all token operations.

---

## Track 5: Mid-Trip (9 migrations) — UI work after Solo(3) M-006

### M-001: Schema Extension (can start after Foundation)
- Add to ItinerarySlot: swappedFromId String?, pivotEventId String?, wasSwapped Boolean @default(false)
- PivotEvent table already exists (empty until now)
- Prisma migration, codegen runs
- Deliverable: migration applied, PivotEvent writeable, Track 3 tests unbroken

### M-002: Weather Service
- OpenWeatherMap integration (1000 free calls/day)
- Cache per city per hour in Redis (multiple trips in same city share weather)
- Check cached weather against outdoor activity slots
- Populate BehavioralSignal.weatherContext from cache
- Deliverable: weather query for active trip city → cached result → weather context available for signals

### M-003: Pivot Trigger Detection
- Weather change: compare cached weather against slot's activity category (outdoor = vulnerable)
- Venue closure: Google Places hours check against current time
- Time overrun: slot endTime vs current time (timezone-aware using Trip.timezone)
- User mood: explicit "not feeling it" button
- Each trigger creates PivotEvent with status: proposed, ranked alternatives from ActivitySearchService
- Deliverable: simulate weather change for outdoor slot → PivotEvent created with alternatives

### M-004: Pivot Drawer UI (requires Solo slot card)
- Swap card interface showing original vs alternatives
- Accept / reject / let expire actions
- MAX_PIVOT_DEPTH=1 enforced at app layer
- Write BehavioralSignal: pivot_accepted/rejected/expired
- Write RawEvent with candidate set (alternatives shown)
- PivotEvent.responseTimeMs captured
- Deliverable: pivot proposed → drawer appears → user resolves → slot updated, signals written

### M-005: Cascade Evaluation
- Scope: same-day slots after the changed slot ONLY
- Cross-day impact = new PivotEvent, not automatic cascade
- Selective re-solve: update sortOrder and startTime for affected slots
- Timezone-aware time calculations using Trip.timezone
- Deliverable: swap lunch slot → afternoon slots shift, next day unaffected

### M-006: Micro-Stops
- Proximity nudge: detect nearby interesting nodes during transit using PostGIS GIST index
- Raw SQL migration for spatial index (Prisma doesn't support GIST):
  CREATE INDEX idx_activity_nodes_location ON activity_nodes USING GIST (ST_MakePoint(longitude, latitude))
- Micro-stop as lightweight ItinerarySlot (slotType: flex, short duration)
- Deliverable: user in transit → nearby suggestion → add as micro-stop

### M-007: Prompt Bar
- NLP input: user types natural language
- LLM parsing: Haiku, structured JSON output only (classification + extracted entities)
- Output schema: { classification: "<one of PivotTrigger values>", confidence: float, entities: [] }
- Latency budget: 1.5s Haiku, fallback to keyword matching on timeout
- Input cap: 200 characters
- No ActivityNode data or user persona in prompt (injection prevention)
- [USER_DATA_START]/[USER_DATA_END] delimiters on user text
- Log all inputs + responses for security audit
- Deliverable: type "I want something quieter" → classified as user_mood → PivotEvent created

### M-008: Trust Recovery
- Flag sheet on slot card
- Two resolution paths: "wrong for me" vs "wrong information"
- IntentionSignal written with source: "user_explicit", confidence: 1.0
- "Wrong information" → ActivityNode flagged for admin review (Track 7 queue)
- Deliverable: flag slot → resolution → IntentionSignal + BehavioralSignal created

### M-009: Tests
- Unit: trigger detection, cascade scope (same-day only), proximity calculation, prompt bar parsing
- Unit: keyword fallback on LLM timeout, structured output validation, MAX_PIVOT_DEPTH enforcement
- Integration: weather trigger → pivot proposed → accepted → cascade updates downstream slots
- Integration: prompt bar input → Haiku parse → PivotEvent → resolution → signals
- E2E: active trip → trigger fires → user resolves pivot → all signals captured
- Prompt injection tests: malicious input in prompt bar → rejected, structured output only
- Cross-track: pivot signals visible to Track 6 post-trip disambiguation
- Deliverable: all green, 25+ tests

Integration: extends Slot schema, writes PivotEvent/BehavioralSignal/IntentionSignal/RawEvent, reads Qdrant via ActivitySearchService. Weather cached in Redis.

---

## Track 6: Post-Trip (8 migrations) — after Solo, can parallel with 4/5

### M-001: Trip Completion Trigger
- Auto-transition: Trip.status → completed when endDate passes in Trip.timezone
- Timezone-aware: convert endDate to UTC using Trip.timezone, compare to now()
- Manual: user marks trip as done
- Set Trip.completedAt
- Deliverable: trip endDate passes in destination timezone → status flips to completed

### M-002: Post-Trip Reflection Screen
- Highlight rating per slot: loved / skipped / missed
- Single feedback question: "What would you do differently?"
- Write BehavioralSignal: post_loved, post_skipped, post_missed, post_disliked
- Post-trip feedback CAN override slot status (completed → skipped if user says "I didn't actually go")
- Deliverable: trip completes → reflection screen → ratings captured, status override works

### M-003: IntentionSignal from Post-Trip Feedback
- User says why they skipped → IntentionSignal with source: "user_explicit", confidence: 1.0
- Options: "not interested" | "bad timing" | "too far" | "already visited" | "weather" | "group conflict"
- Deliverable: user provides skip reason → IntentionSignal row with explicit source

### M-004: Signal Disambiguation Batch
- Rule heuristics config (not ad-hoc if/else):
  disambiguation_rules mapping (signalType, weatherContext, slotType, activityCategory) → intentionType + confidence
- Example rules:
  - post_skipped + rain + outdoors → weather_dependent (0.7)
  - post_skipped + clear + dining → not_interested (0.6)
  - post_skipped + time_overrun_in_trip → bad_timing (0.8)
- Write IntentionSignal with source: "rule_heuristic"
- Explicit user feedback (M-003) always wins on read — higher confidence
- Process full backlog on first run
- Deliverable: batch processes 20 post_skipped signals → intent types assigned with correct confidence

### M-005: Photo Strip + Memory Layer
- Photo upload per slot (server-generated signed URL for direct GCS upload)
- Max 10MB per photo, image/jpeg + image/png + image/webp only
- Visited map: read-only map of completed slots
- Trip summary card
- Deliverable: add photos → memory view renders with photos + visited map

### M-006: Shared Trip Artifact
- Public memory page (extends Track 4 SharedTripToken or creates new token for solo)
- Photo strip + itinerary + highlights
- Same security as Track 4 M-006 (XSS prevention, CSP, rate limiting)
- Deliverable: share memory → public page with photos and highlights

### M-007: Re-Engagement Loop
- Next destination suggestion based on behavioral signals (Qdrant search with accumulated persona)
- 24hr push notification: "How was [trip]?" → deep link to reflection (no session token in link)
- 7-day email via Resend: trip memory + "Where next?"
- Push infra: FCM setup, PushToken model (device token storage), notification queue in Redis
- Email: SPF/DKIM/DMARC configured, unsubscribe mechanism, rate limit 1 per 7-day window
- One-time-use login links for email deep links (15-minute expiry, invalidated after use)
- Deliverable: trip completes → 24hr push fires → 7-day email sends → both link to correct surfaces

### M-008: Tests
- Unit: timezone-aware completion trigger (freeze_time across zones), disambiguation rules, photo upload validation
- Integration: trip completes → reflection → signals + intentions written correctly
- Integration: disambiguation batch produces correct IntentionSignals from rules config
- Integration: slot status override (completed → skipped) works
- E2E: full trip lifecycle ending with post-trip flow, re-engagement push/email verified
- Cross-track: pivot signals from Track 5 visible in post-trip disambiguation
- Deliverable: all green, 20+ tests

Integration: reads Trip/Slot/Signals from earlier tracks. Writes BehavioralSignal + IntentionSignal. Push via FCM, email via Resend.

---

## Track 7: Admin (9 migrations) — parallel from Foundation

### M-001: Admin Auth Guard + AuditLog
- systemRole: admin check middleware
- Admin layout (separate from user app shell)
- AuditLog write on every admin action (append-only, no UPDATE/DELETE at DB level)
- Captures: actorId, action, targetType, targetId, before/after state, ipAddress, userAgent
- Deliverable: admin route → 403 for non-admins, all actions logged to AuditLog

### M-002: Model Registry UI
- List all models with stage badges
- Promotion requires: metrics comparison (new must beat current production on primary metric)
- Promotion path: staging → ab_test (auto_eval OK) → production (admin-only, requires confirmation)
- 2-minute cooldown between promotion actions
- artifactHash verification: display hash, warn if mismatch on load
- All promotions logged to AuditLog
- Deliverable: register model → view metrics → promote with safety gate → AuditLog entry

### M-003: City Seeding Control
- Trigger city seed job from admin UI
- Confirmation step with estimated cost before execution
- Progress dashboard per city (scraped, resolved, tagged, indexed — from Track 2 orchestrator)
- Rate limit: 2 seed triggers per minute
- Deliverable: click "Seed Austin" → confirm cost → pipeline runs → progress updates

### M-004: Activity Node Review Queue
- List nodes with status: flagged or low convergence
- Approve / edit / archive actions (all logged to AuditLog with before/after state)
- Alias management: view/add/remove aliases
- Status change logged to AuditLog (replaces phase-2 StatusHistory table for now)
- Deliverable: flagged nodes appear → admin resolves → AuditLog captures change

### M-005: Source Freshness Dashboard
- Last scrape time per source
- Alert if source hasn't been scraped in > configured threshold
- Source authority score management (changes logged to AuditLog)
- Deliverable: dashboard shows all sources with freshness, stale sources highlighted

### M-006: User Lookup + Persona Inspector
- Search users by email/name
- View: behavioral signals, trips, subscription tier, feature flags
- Feature flag overrides (logged to AuditLog, featureFlags only writable by admin)
- Subscription tier changes via admin (replaces "manually set via SQL" for lifetime)
- All lookups logged to AuditLog (action: "user_lookup")
- Deliverable: search user → see history → override flag → AuditLog entry

### M-007: Pipeline Health + Cost Dashboard
- LLM costs aggregated by model, date, pipeline stage
- API call counts (Foursquare, Google, OpenWeatherMap)
- Pipeline job success/failure rates
- Cost alerting: configurable thresholds per pipeline stage, alert on exceed
- Deliverable: dashboard shows daily costs + call counts + error rates, alerts fire on threshold

### M-008: Trust & Safety
- SharedTripToken management: view active tokens, revoke (logged to AuditLog)
- InviteToken management: view, revoke
- Injection detection review queue (prompt bar inputs flagged as suspicious)
- Deliverable: admin can manage all tokens, review flagged inputs

### M-009: Tests
- Unit: admin auth guard, promotion safety gate (worse metrics blocked), cost alerting thresholds
- Integration: admin actions → correct DB state + AuditLog entries
- Integration: AuditLog is append-only (verify UPDATE/DELETE rejected at DB level)
- E2E: admin login → navigate all surfaces → perform actions → verify AuditLog
- Deliverable: all green, 20+ tests

Integration: read-only all tables. Writes to ModelRegistry, ActivityNode (status), User (feature flags), AuditLog. All writes audited.

---

## Cross-Track Test Suite (owned by Foundation, run after all merges)

### tests/cross-track/
- test_signal_flow.py: Track 3 writes signals → Track 6 reads them for disambiguation
- test_schema_extension.py: Track 4/5 extend Track 1 tables → base fields still work
- test_entity_to_itinerary.py: Track 2 nodes → Track 3 generation produces valid itineraries
- test_pivot_to_posttrip.py: Track 5 pivot signals → Track 6 reflection sees them
- test_admin_reads_all.py: Track 7 can read everything from all tracks
- conftest.py: full seeded state (user, trip, slots, signals, nodes, vibes)

### Regression gate
All track tests run on every PR to main. If Track 5 breaks a Track 3 assertion, Track 5 owns the fix.

---

## Migration Count Summary
| Track | Migrations | Tests |
|-------|-----------|-------|
| Foundation | 12 | 20+ |
| Data Pipeline | 14 | 25+ |
| Solo Trip | 11 | 30+ |
| Group Trip | 8 | 25+ |
| Mid-Trip | 9 | 25+ |
| Post-Trip | 8 | 20+ |
| Admin | 9 | 20+ |
| Cross-Track | — | 6 files |
| **Total** | **71** | **~170+ tests, ~68 files** |
