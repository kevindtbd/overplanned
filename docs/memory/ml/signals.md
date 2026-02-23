# ML / Signals & Persona

## Three-Layer Architecture
1. **BehavioralSignal** — User actions only. Feeds ML training. NEVER system events.
2. **IntentionSignal** — Explicit "why" signals (reflection, feedback). Higher confidence.
3. **RawEvent** — Firehose (impressions, sessions). System events go here.

## Signal Types (9 added in feature units sprint)
- invite_created, invite_accepted, vote_cast, share_created, share_imported
- reflection_submitted, packing_generated, pivot_created, pivot_resolved

## Per-Source Quality Signals
- NEVER collapse to single score
- Each source (blog, Foursquare, Atlas Obscura, Reddit) has own authority score
- Cross-reference convergence scoring

## Persona Modeling
- personaSeed from Trip DNA (onboarding)
- Behavioral signals accumulate into user graph
- "Invisible intelligence" — persona insights show in recommendation quality, never in UI

## Learnings
- BehavioralSignal pollution (system events) degrades ML training data quality
