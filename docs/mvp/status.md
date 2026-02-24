# MVP Status

*Last updated: 2026-02-23*

## Done

### Core Platform
- Auth (Google OAuth, DB sessions, max 30d/7d idle)
- User model + roles (beta/lifetime/free/pro)
- Prisma schema: 36+ models
- Settings page (account, display, notifications, privacy, travel interests, billing portal)

### Trip Planning
- Trip CRUD + status lifecycle (draft/planning/active/completed/archived)
- Onboarding flow (multi-step, group structure, scenario cards, tag cloud, dates)
- Itinerary slot management (add, remove, reorder, confirm, skip, swap)
- Trip detail page (WelcomeCard, FAB, progress nudge, day navigation)
- Generation engine + Trip DNA
- .ics calendar export
- Slot move between days

### Multi-City
- TripLeg + BackfillLeg schema
- Leg CRUD API (create, update, delete, reorder)
- Leg-aware onboarding (LegReviewStep)
- Leg-aware day navigation + dashboard display
- TripSettings leg management
- Phase C: Haiku-based multi-city extraction from diary text
- Phase C: BackfillLeg creation from extraction results
- Phase C: Venue-to-leg assignment by city match
- Phase C: DiaryTripCard route string display (truncation at 5+ cities)

### Backfill / Diary
- Backfill submit + pipeline (FastAPI)
- BackfillTrip + BackfillVenue + BackfillLeg + BackfillPhoto models
- Diary enrichment (venue extraction, entity resolution, anomaly detection)
- DiaryTripCard dashboard component

### Group Features
- Trip invites (create, preview, accept, revoke)
- Voting (per-slot polls, vote tallying)
- Trip sharing (token creation, public view, import with fresh UUIDs)
- Packing lists
- Pivot events (mid-trip replanning triggers)
- Reflection (per-slot loved/skipped/missed ratings)

### Search & Discovery
- Activity browser at /discover (feed, swipe deck, shortlist)
- Feed API (city filter, category filter, convergenceScore sort)
- Vibe tag system (42 tags + 2 location flags)
- VibeChips component
- Qdrant vector search client (async, HNSW, city+category filter)
- /explore page: vibe-first cold start (4 archetype cards, 3-city shortlist)
- CityVibeProfile schema + vibes API
- Dashboard "Explore destinations" nav link

### Post-Trip
- Reflection API (per-slot ratings, feedback text, BehavioralSignal creation)
- Reflection page with per-slot SlotRating component
- Vibe chips (4 options: Loved it / Good trip / Mixed bag / Not for me)
- trip_vibe_rating signal type
- Memory page at /trip/[id]/memory (TripSummary, PhotoStrip, VisitedMap, reflection summary, share, re-engage CTA)
- GCS signed URL endpoint for photo uploads (dev fallback included)
- TripPhoto schema
- TripSummary, PhotoStrip, VisitedMap components
- Trip status-aware routing (completed trips link to reflection/memory)

### Data / ML
- Synthetic training data (BPR-ready)
- BehavioralSignal schema (30+ signal types)
- Backfill enrichment pipeline (FastAPI)
- Vibe vocabulary (locked, 42 tags)

### Infrastructure
- 891+ tests (vitest), 58+ test files
- Prisma ORM + PostgreSQL 16
- FastAPI backend (Python 3.11)
- Design system (Sora + DM Mono, Terracotta, warm tokens, SVG only)

---

## Not Done

### Data Pipeline
- [ ] Scrapers (Reddit PRAW, Google Places, Tabelog, Naver, Dianping, blog RSS)
- [ ] Entity resolution across sources
- [ ] Qdrant sync (vector DB population from ActivityNodes)
- [ ] City seeding jobs (admin-triggered)
- [ ] CityVibeProfile seeding (need 3+ cities at 25+ nodes for /explore)

### Group Trip v2
- [ ] Fairness engine (who compromised most, voice dominance detection)
- [ ] Subgroup split logic (peel off, reconvene suggestions)
- [ ] Affinity matrix computation
- [ ] Poll proposer tracking

### Mid-Trip Intelligence
- [ ] Micro-stops (schema designed in docs, not implemented)
- [ ] Prompt bar (free-text mid-trip input)
- [ ] Push notifications (pivot triggers, nudges)
- [ ] Real-time reactivity beyond PivotEvent stubs

### Post-Trip v2
- [ ] Re-engagement emails (Python email service exists, needs Cloud Tasks trigger)
- [ ] Magic link auth (/auth/magic token validation)
- [ ] "Where next?" destination suggestion engine
- [ ] Social share card (downloadable PNG via Satori)
- [ ] EXIF extraction from uploaded photos
- [ ] Feedback-to-persona weight softening propagation

### Discovery v2
- [ ] Returning user "confident guess" (single destination recommendation)
- [ ] Behavioral re-ranking of results
- [ ] Qdrant wired to frontend (currently unused)
- [ ] Search/autocomplete (city resolution)
- [ ] Backfill signal integration for cold-start personalization

### Admin Tooling
- [ ] Model registry UI (promote staging/a_b_test/production/archived)
- [ ] A/B test monitoring dashboard
- [ ] Training data inspection
- [ ] City seeding control panel
- [ ] Pipeline health monitoring
- [ ] Cost dashboard (LLM spend tracking)

### Monetization
- [ ] Paywall enforcement (Stripe wired but not gating)
- [ ] Entitlement tracking (3 free trips/year, group pricing)
- [ ] Subscription lapse grace period logic
- [ ] Group billing (creator pays, members branch)

### Trust & Failure Recovery
- [ ] One-tap flag on slot card
- [ ] Credit system ($5 or 20% off)
- [ ] Anti-abuse signal triangulation
- [ ] Confidence decay on ActivityNodes

### Data Collection Gaps
- [ ] Card view duration on RankingEvent (client-side)
- [ ] Weather context at signal write time (synthetic backfill done, production append needed)
- [ ] Geo cluster denormalization on signals
- [ ] Search query events table
- [ ] Onboarding funnel step-level events
- [ ] Pre-trip modification signals
- [ ] Activity acceptance rate stats (nightly batch)
- [ ] Share/import feedback schema
- [ ] Inter-trip latency metric

---

## Pending Migrations
- None (CityVibeProfile + TripPhoto + trip_vibe_rating pushed via `prisma db push` 2026-02-23)
