# Overplanned Project Memory

## Memory Bank Structure
Organized by vertical, then sub-topic. Each file has a `## Learnings` section for compound learning saves.

### Verticals
| Vertical | Index | Sub-topics |
|----------|-------|------------|
| **UI** | `ui/_index.md` | design-system, landing, dashboard, trips, settings, onboarding, discover, groups, mid-trip, post-trip, admin, nav |
| **Server** | `server/_index.md` | auth, trips, settings, signals, invites, voting, sharing, pivot, packing, reflection, backfill, slots, billing, discover, cities |
| **ML** | `ml/_index.md` | generation, signals, embeddings, training-data, city-seeding, llm-usage |
| **Data** | `data/_index.md` | schema, pipeline, privacy |
| **Infra** | `infra/_index.md` | devops, testing, conductor |
| **Product** | `product/_index.md` | philosophy, access-control, decisions, roadmap |

### Legacy Files (still valid, referenced from new structure)
- `schema-contracts.md`, `schema-revisions.md` — Detailed schema history
- `feature-units-conductor.md` — Feature units sprint details
- `frontend-overhaul.md` — Full token specs (referenced from ui/design-system.md)
- `training-data-pipeline.md` — Detailed pipeline docs
- `vertical-plans.md`, `vertical-tracks.md` — 7-track SOC plan

## Compound Learning Protocol
When "compound our learnings" is invoked:
1. **Identify** which verticals/sub-topics the session touched
2. **Extract** reusable insights (patterns, anti-patterns, decisions, gotchas)
3. **Route** each insight to the correct `<vertical>/<sub-topic>.md` file's `## Learnings` section
4. **Cross-link** if an insight spans verticals (add note in both files)
5. **Deduplicate** — check if the insight already exists before writing

## CRITICAL Rules
- **Never bypass conductor without asking** — present fixes, don't route around
- **Always present choices before overriding workflows** — non-negotiable
- Kill old conductor processes before starting new ones on same port

## Project State (updated 2026-02-23)
- 716 tests passing across 46 files
- All backend SOC tracks complete
- UI Overhaul phases 0-4 committed
- Feature Units Sprint complete (invite, vote, share, reflection, packing, pivot)
- TripLeg migration complete (multi-city)
- Settings page complete
- Training data BPR-ready
- See `product/roadmap.md` for full status + remaining work

## User Style
- Casual but thorough: "let it cook", "bet", "fire", "that jawn"
- Challenges over-engineering — lean MVP + data capture
- "No column without a data source" discipline
- Review between phases, not blind automation

## Quick-Reference Rules
- Ink scale INVERTED: ink-100 = darkest, ink-900 = lightest
- BehavioralSignal = user actions ONLY (system events -> RawEvent)
- ALL trip-scoped queries: `status: "joined"` on TripMember
- Vitest (not Jest), Playwright (mobile/tablet/desktop)
- `vi.resetAllMocks()` not `vi.clearAllMocks()`
- Valid UUIDs in test payloads (Zod catches non-UUIDs first)
- Plans from memory may have wrong API shapes — verify against source
