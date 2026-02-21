# Phase 2 + Non-MVP Sidebar
Items identified during agent review that are real but NOT launch blockers.
Address after MVP ships and user data is flowing.

**Update (2026-02-20):** Synthetic training data pipeline is BPR-ready.
3 blockers fixed (c4c8c0f), 5 enrichments complete (0fd5f6b). Item #1 below
(BPR triplet optimization) is less urgent now — RankingEvent seeding provides
clean (user, candidates, selected) tuples without JSON parsing. Items #3 and
#7 remain relevant for production training pipeline.

## Phase 2 Data Issues (Post-MVP, Pre-Two-Tower)

### 1. BPR Training Triplet Optimization
- Current: constructing (user, positive, negative) triplets requires cross-table
  join between BehavioralSignal and RawEvent, parsing JSON payloads
- Fix: add `candidateSetId String?` to BehavioralSignal so BPR training join
  is a simple WHERE instead of JSON parse
- When: Month 4, before BPR training begins (Month 5)

### 2. RawEvent Training Extraction Checkpoint
- Current: 90-day rolling purge could delete RawEvents before training pipeline extracts them
- Fix: add `lastExtractedAt DateTime?` to RawEvent or a separate extraction checkpoint table.
  Purge job must not delete records not yet processed by extraction.
- When: Month 4, before RawEvent volume gets serious

### 3. Materialized Training Views
- Three-signal join (Behavioral + Intention + Raw) is the slowest query in the system
- Fix: nightly materialized view or pre-joined training table that denormalizes
  the three tables for batch training consumption
- When: Month 5, when BPR training pipeline is built

### 4. ActivityNode typicalDurationMin
- Referenced by LLM ranker (compressed candidate schema), item tower feature list,
  offline prefetch scoring
- No scraper produces duration estimates at launch
- Fix: add `typicalDurationMin Int?` to ActivityNode with rule-based defaults by category
  (dining=60, culture=90, drinks=45, outdoors=120, active=90, etc.)
  Populated during entity resolution as a derived field
- When: Month 3, before itinerary generation quality matters

### 5. ActivityNode Status History
- When admin archives/flags a node, no record of who/when/why
- Fix: add `ActivityNodeStatusHistory` table (nodeId, previousStatus, newStatus,
  changedBy, reason, createdAt)
- When: Month 3, when admin panel (Track 7) is built

### 6. Qdrant Read Replica Strategy
- At 10K+ nodes across 13 cities, single Qdrant instance is fine
- At 50K+ nodes, consider Qdrant cluster mode or read replicas
- When: Month 6+, based on city expansion

### 7. IntentionSignal → Training Pipeline Integration
- IntentionSignal is confirmed as training feature (not analytics-only)
- The training extraction pipeline must read IntentionSignal alongside BehavioralSignal
- Intent-annotated actions teach the model: "skip because of weather" ≠ "skip because not interested"
- Fix: training extraction query includes IntentionSignal join, intent type becomes a
  feature column in the training dataset
- When: Month 5, when BPR training pipeline is built

### 8. Position Bias Debiasing
- RawEvent captures position in list (for impression events)
- Two-Tower needs position bias correction during training (items shown first get more clicks)
- Fix: inverse propensity weighting (IPW) or position feature in the model
- When: Month 9, when Two-Tower training begins

### 9. User Embedding Cache
- Cold-start: personaSeed from onboarding
- Warm: aggregated BehavioralSignals per user
- At scale, recomputing user embedding from signals on every request is expensive
- Fix: precomputed user embedding cache (Redis or Postgres), refreshed nightly
- When: Month 6+, when user signal volume justifies caching

### 10. Data-Gaps Doc Integration
- docs/overplanned-data-gaps.md has 10 items not reflected in any migration
- Gaps 3/5/10 (payload field additions) → Track 3 M-009
- Gaps 1/2 (new tables) → Foundation phase 2 migration
- Gap 8 (acceptance stats) → Track 7
- Gap 4 (import events) → Track 6
- When: sweep through during Month 2-3 as tracks ship

## Non-MVP Architecture Items (Important But Not Launch Blockers)

### 11. Codegen Script Specification
- Prisma→JSON Schema script has edge cases: Json fields (no type info), String[],
  @@unique/@@index (no JSON Schema equivalent), optional vs required, default values
- Need a specification doc mapping every Prisma type to JSON Schema output BEFORE writing the script
- Not a data issue but blocks Foundation M-002 quality
- When: during Foundation M-002 implementation

### 12. ActivitySearchService
- Qdrant search → Postgres hydration → merge is used by 4 consumers
  (itinerary gen, discover, pivot alternatives, micro-stops)
- Should be one reusable FastAPI service, not inline code
- When: Foundation M-005 or Track 3 M-002 (whichever comes first)

### 13. Two TypeScript Type Sets
- @prisma/client types (server, includes relations) vs packages/shared-types (API boundary, no relations)
- Must document distinction, enforce with ESLint: no @prisma/client imports in app/ frontend code
- When: Foundation M-006 monorepo wiring

### 14. OpenAPI Fragment Generation
- Contract system generates Pydantic + TS but no OpenAPI spec
- FastAPI auto-generates OpenAPI, but Next.js API routes don't
- Need response schema validation on Next.js routes in dev mode
- When: after Foundation, iterative improvement

### 15. GDPR/Privacy Architecture
- DSAR handler (data subject access request)
- Cascade delete path across 10+ tables
- Consent management for behavioral tracking
- Data processing agreement template
- Anonymization strategy for training data from deleted users
- RawEvent PII scanner on ingestion endpoint
- GCS archive deletion path (12-month retention)
- When: before public launch (beta users are lower risk, but must be addressed before open signup)

### 16. Rate Limiting Tiers (Redis-backed)
- Anonymous: 10 req/min
- Authenticated: 60 req/min general, 5 req/min for LLM-triggering endpoints
- Admin: 120 req/min, 2 req/min for scraper triggers
- /events/batch: 60 req/min per user, 1000 events max per batch
- When: Foundation M-005, using Redis

### 17. SLO for Itinerary Generation
- P95 latency under 8s, availability 99.5%
- Degradation cascade: LLM timeout 5s → deterministic ranking, Qdrant timeout 3s →
  Postgres fallback, both down → cached template
- When: Track 3 M-002 implementation

### 18. Security Headers
- CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy
- When: Foundation M-005 (FastAPI) and M-004 (Next.js)

### 19. Scraper Isolation
- Scrapers should run as separate Cloud Run service with own IP
- Not co-located with user-facing API
- When: Track 2 M-001, or Foundation M-007 deploy skeleton

### 20. Qdrant Authentication
- Enable API key auth in docker-compose (QDRANT__SERVICE__API_KEY)
- Bind to 127.0.0.1 in dev
- Internal-only Cloud Run service in prod
- When: Foundation M-001 (docker-compose update)

### 21. Connection Pooling
- PgBouncer in docker-compose from day one
- Prevents "too many connections" when background jobs + live traffic compete
- When: Foundation M-001

### 22. Test Infrastructure (68 files vs 7 planned)
- Cross-track test suite (tests/cross-track/)
- Contract parity tests
- Shadow training data quality tests
- Signal invariant helpers
- Fixture factories per model
- Performance tests (RawEvent throughput, Qdrant latency, generation latency)
- docker-compose.test.yml with RAM disk Postgres + tmpfs Qdrant
- Mock suite for all external APIs
- When: Foundation M-008, expanded significantly

### 23. Email Infrastructure
- SPF, DKIM, DMARC configuration on sending domain
- Unsubscribe mechanism (CAN-SPAM, GDPR)
- Rate limit: 1 re-engagement per user per 7-day window
- When: Track 6 M-005

### 24. Stripe Webhook Verification
- stripe.webhooks.constructEvent() on every incoming webhook
- Never expose Stripe IDs in API responses
- Restricted API keys (minimum permissions)
- Replace "manually set via SQL" for lifetime with admin action + AuditLog
- When: Foundation M-003 (wired but not gating)

### 25. Offline Mode (Explicit Descope)
- The docs describe offline swipe deck (40 nodes, 1.5km radius, zero LLM)
- This is explicitly descoped from MVP
- Requires service worker + IndexedDB — significant complexity
- When: Track 3 v2, post-MVP

### 26. Dependency Graph Correction
- Tracks 4 and 5 cannot truly parallel with Track 3
- Solo(3) M-001→M-006 (core components) must complete before Group(4) and MidTrip(5) UI work
- Track 4/5 schema migrations (their M-001s) CAN parallel with Track 3
- Admin(7) is truly parallel from Foundation
- When: plan revision before execution
