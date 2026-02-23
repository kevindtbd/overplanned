# Documentation Inventory (All 45 Files Read)

## Mapping: Doc → Vertical Track

### Foundation (Track 1)
- CLAUDE.md — tech stack, design system rules, architecture principles
- docker-compose.yml — Postgres 16 + Qdrant
- overplanned-rbac.docx — RBAC schema, tier logic, Stripe transition path
- overplanned-design-v4.html — canonical design system (tokens, components)
- overplanned-app-shell.html — mobile navigation shell (home/trips/explore/profile)
- overplanned-desktop-dashboard.html — desktop layout (sidebar + main + context)
- overplanned-architecture.html — system architecture diagram
- travel-design-v2.html — trip creation + itinerary layout (desktop)
- overplanned-landing-stripe.html — landing with pricing
- overplanned-philosophy.md — v1 product philosophy, design foundations
- overplanned-philosophy-v2.md — expanded philosophy, business model, archetypes
- overplanned-navigation-architecture.md — two-context nav model
- overplanned-devops-playbook.md — monitoring, alerts, deployment, security
- index.html — current landing page

### Data Pipeline (Track 2)
- overplanned-bootstrap-deepdive.md — ML bootstrap, scraping pipeline, LLM extraction, cost model
- overplanned-blog-sources.md — curated seed list with authority scores
- overplanned-reddit-access-addendum.md — Reddit alternatives (Arctic Shift, HTTP, Apify)
- overplanned-reddit-access-addendum-v2.md — same content as v1
- overplanned-vibe-vocabulary.md — 42 locked vibe tags, 9 categories
- overplanned-heuristics-addendum.md — temporal tags, tourist score velocity, author decay
- overplanned-data-sanitation.md — 3-layer sanitation architecture
- overplanned-city-seeding-strategy.md — 13 launch cities, tier model, costs
- overplanned-infra-data-strategy.docx — image sourcing, caching, memoization, cost model, platform adapters

### Solo Trip (Track 3)
- overplanned-onboarding.html — mobile onboarding funnel
- overplanned-day-view.html — day-by-day schedule
- overplanned-map-view.html — desktop map interface
- overplanned-solo-view.html — solo trip with 4 tabs
- overplanned-itinerary-reveal.html — generation loading → reveal
- overplanned-discover.html — cold start, shortlist, returning user
- overplanned-states.html — empty, loading, error, notification states
- overplanned-landing.html — marketing landing with feature demos
- overplanned-product-ml-features.md — offline mode, notifications, packing, calendar
- overplanned-open-questions-deepdive.md — onboarding, discovery, map, motion tokens

### Group Trip (Track 4)
- overplanned-group-planning.html — pre-trip slot voting
- overplanned-group-social.html — mid-trip group state dashboard
- overplanned-group-invite.html — invite landing + organizer view
- group-dynamics-research.md — fairness models, energy curves, Abilene paradox
- overplanned-shared-trips.md — shared activity list, commercial protection

### Mid-Trip (Track 5)
- overplanned-pivot-ui.html — real-time pivot drawer
- overplanned-midtrip.html — day view + pivot scenarios
- overplanned-slot-card.html — slot card + trust recovery
- overplanned-microstops.html — micro-stop list + add sheet
- architecture-addendum-pivot.md — PivotEvent schema, cascade model
- overplanned-microstops-backend.md — micro_stops table, proximity nudge

### Post-Trip (Track 6)
- overplanned-posttrip.html — trip memory & feedback capture

### Admin (Track 7)
- overplanned-admin-tooling.md — 6 admin surfaces, build priority

### Cross-cutting (multiple tracks)
- overplanned-open-decisions.md — all 12 items resolved
- overplanned-deepdive-agenda.md — 6 topic deep dives (monetization, reactivity, onboarding, post-trip, search, safety)
- overplanned-data-gaps.md — 10 gaps, priorities for v1
- overplanned-infra-data-strategy.docx — spans Pipeline + Foundation
