# Agent Review Summary

## Architect Review — Key Findings
1. **Tracks 3-7 are NOT truly parallel** — Group(4) and MidTrip(5) depend on Solo(3) core components (slot card, day view, map). Real graph: Foundation→Pipeline→Solo→[Group,MidTrip]→PostTrip. Admin truly parallel.
2. **BehavioralSignal missing indexes** — no composite index for most common query (userId+createdAt, userId+tripId+signalType, activityNodeId+signalType)
3. **Trip.timezone required, not optional** — affects completion trigger, morning notifications, cascade evaluator, .ics export. IANA timezone string.
4. **ActivityNode missing typicalDurationMin** — referenced by LLM ranker, item tower, offline deck. Rule-based default by category or derive at runtime. Must decide.
5. **VibeTag model missing** — junction table has vibeTagId but no VibeTag table. Either add the table or rename to vibeTagSlug.
6. **Codegen spec unwritten** — Prisma→JSON Schema script is critical but has no specification. Edge cases: Json fields, String[], @@unique, optional vs required. Spec needed before code.
7. **No ActivitySearchService** — Qdrant search → Postgres hydration → merge is 4-consumer pattern, needs one reusable service.
8. **RawEvent 90-day purge creates training data cliff** — extraction job must run BEFORE purge. Need last_extracted_at checkpoint.
9. **BPR training triplet construction expensive** — cross-table JSON parse. Add candidateSetId to BehavioralSignal.
10. **IntentionSignal has no downstream consumer** — decide: training feature, persona update signal, or analytics-only.
11. **Two TypeScript type sets will diverge** — @prisma/client (server) vs shared-types (API boundary). Document distinction, enforce with ESLint.
12. **No Redis in stack** — referenced in bootstrap doc for ranking cache but not in docker-compose or any track.
13. **No rate limiting architecture**
14. **No SLO for itinerary generation** — 4 external deps in critical path, no degradation cascade defined.
15. **GDPR/privacy architecture missing** — DSAR handler, cascade delete path, consent management, anonymization strategy.
16. **RawEvent idempotency** — mobile retry duplicates events. Need client-generated clientEventId + unique constraint.
17. **Data-gaps doc has 10 items not in any migration** — floating outside execution plan.

## Security Review — 27 Findings (7 Critical, 7 High, 9 Medium, 6 Low)

### Critical
1. **No-account group join = unauthenticated write access** — require account or quarantine ephemeral signals
2. **Shared trip token predictability** — mandate crypto.randomBytes(32), add SharedTripToken model, expiration, revocation
3. **Prompt bar = direct LLM injection surface** — structured output only, no context in prompt, 200 char cap
4. **Admin panel lacks audit log + granular RBAC** — AuditLog model, append-only, separation of duties
5. **RawEvent GDPR gap** — no consent mechanism, no deletion path for GCS archives, no PII scanner on ingestion
6. **Session management unspecified** — no timeout, no revocation, no concurrent limits, NextAuth models missing from schema
7. **Stripe webhook verification missing** — forged webhooks could grant subscriptions

### High
8. CORS/security headers not configured
9. Rate limiting absent system-wide
10. Invite token: no expiration, no revocation, no single-use option
11. Scraper infra exposes internal IPs, needs isolation
12. Qdrant has no authentication
13. XSS via owner_tip and Google display name
14. ML model supply chain: no artifact hash verification

### Medium
15-23: Input validation, Sentry PII leakage, GCS bucket security, email SPF/DKIM, geolocation privacy, CSRF, LLM cost injection, API key management, featureFlags bypass

### Low
24-27: Docker image security, push notification security, DB connection strings

## Test Engineer Review — 68 Test Files Needed (vs 7 planned)

### Critical Gaps
1. **No cross-track test suite** — add tests/cross-track/ with signal flow, schema extension, entity→itinerary tests
2. **Contract tests are "CI guard" not actual tests** — per-model schema parity assertions needed
3. **Shadow training data quality has no dedicated tests** — positive pairs, explicit/implicit negatives, candidate sets, position bias
4. **Entity resolution edge cases untested** — CJK normalization, chain stores, merge-preserves-signals
5. **Signal invariants not reusable** — extract assert_signal_integrity(db) helper, call from every track
6. **No fixture factory pattern** — nullable extensions break older track fixtures without factories
7. **No regression gate** — all track tests must run on every PR to main

### LLM Testing Strategy
- Never test the LLM. Test output schema validation + business logic with mocked LLM.
- Golden file tests from recorded real LLM calls.
- Structural invariants (no time overlap, transit slots between distant activities, meal slots at reasonable times)

### Performance Tests Needed
- RawEvent batch: 100 events under 200ms
- Qdrant search: under 100ms with filters
- Itinerary generation: under 8s end-to-end

### Test Infrastructure Needed
- docker-compose.test.yml (Postgres on RAM disk, Qdrant with tmpfs)
- conftest.py with testcontainers
- Mock suite: foursquare, google, weather, oauth, haiku
- Fixture factory per core model
- tests/fixtures/ with JSON seed files per launch city
