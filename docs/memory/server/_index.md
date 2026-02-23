# Server Vertical — Memory Bank

## Sub-topic Files
- `auth.md` — NextAuth, Google OAuth, sessions, RBAC, gates
- `trips.md` — Trip CRUD, legs, generation, draft/status state machine
- `settings.md` — Settings API routes, field whitelisting, Zod validation
- `signals.md` — BehavioralSignal, IntentionSignal, RawEvent pipelines
- `invites.md` — Invite create/preview/join, TOCTOU prevention
- `voting.md` — Vote schema, quorum logic, camp detection
- `sharing.md` — Share tokens, public view, import (clone with fresh UUIDs)
- `pivot.md` — Pivot creation/resolution, scoring, active caps
- `packing.md` — LLM-generated packing lists, item toggle
- `reflection.md` — Post-trip reflection, HTML strip, signal logging
- `backfill.md` — Past trip backfill, venue enrichment, photo pipeline
- `slots.md` — Slot swap, move, status, vote endpoints
- `billing.md` — Stripe integration, billing portal
- `discover.md` — Discover feed API, cold start, personalization
- `cities.md` — City resolver, city photos

## Cross-Cutting Patterns
- ALL trip-scoped queries MUST include `status: "joined"` on TripMember (security)
- `getServerSession` defense-in-depth on every API route
- Zod validation on all POST/PATCH bodies
- Rate limiting: 3 tiers (see infra/testing.md for details)
