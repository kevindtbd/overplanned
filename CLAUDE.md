# Overplanned — Claude Code Context

## What This Is
Overplanned is a travel planning app that generates personalized itineraries 
through behavioral-driven recommendations, not demographic profiling. 
Local intelligence (Reddit, Tabelog, local forums) + ML persona modeling 
drives all recommendations. Not TripAdvisor. Not Yelp. Local-first signals only.

## Design System (LOCKED — do not deviate)
- Fonts: Sora (headings) + DM Mono (data/labels)
- Accent: Terracotta (#C4694F)
- Tokens: warm-background, warm-surface, warm-border
- Icons: SVG only, no icon libraries
- Images: Unsplash URLs, no placeholder boxes
- No emoji anywhere in the product
- Reference: docs/overplanned-design-v4.html for all component patterns

## Tech Stack
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind
- Backend: FastAPI (Python 3.11) for ML/scraping services
- Database: PostgreSQL 16 via Prisma ORM
- Vector DB: Qdrant (Docker locally, Cloud Run in prod)
- Auth: NextAuth.js with Google OAuth only
- Payments: Stripe (wired in but not gating anyone — beta mode)
- Email: Resend
- Errors: Sentry
- LLM: Anthropic API — claude-sonnet-4-6 for generation, 
         claude-haiku-4-5-20251001 for classification tasks
- Hosting: GCP Cloud Run

## Access Control (Current State: Beta)
User roles: 'beta' | 'lifetime' | 'free' | 'pro'
- All new signups default to role = 'beta'
- Lifetime users are manually set via SQL — they never hit a paywall
- Access check: ['beta', 'lifetime', 'pro'].includes(user.role)
- Stripe is wired but not enforcing payment for anyone yet
- Do NOT add paywalls or feature gates until explicitly instructed

## Architecture Principles
- ML + LLM at the edges, deterministic logic in the middle
- LLMs are interface layers (input parsing, output narration) NOT decision-makers
- All recommendation decisions logged as behavioral_signals
- Every LLM call logs: model version, prompt version, latency, cost estimate
- Three layers: User Graph (behavioral) / Trip State (real-time) / World Knowledge (Qdrant)

## Key Database Tables
users, trips, itinerary_slots, activity_nodes, behavioral_signals,
vibe_tags, quality_signals, model_registry, pivot_events

## Do Not
- No demographic profiling (no age, home city, income fields)
- No TripAdvisor or Yelp as primary recommendation sources
- No separate CSS/JS files — single-file components
- No localStorage in artifacts
- No emoji anywhere
- No paywalls until explicitly told to add them

## Docs to Read When Uncertain
- docs/overplanned-bootstrap-deepdive.md — ML strategy, LLM→ML transition
- docs/architecture-addendum-pivot.md — real-time reactivity, PivotEvent schema
- docs/overplanned-product-ml-features.md — behavioral signals, model registry
- docs/overplanned-philosophy.md — product voice, UX principles
- docs/overplanned-design-v4.html — canonical design reference