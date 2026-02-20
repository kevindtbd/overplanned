# M-005: Entity Resolution Pipeline

## Description
Deduplication system that resolves multiple references to the same real-world venue into a single canonical ActivityNode. The "7-Eleven problem" — seven spellings, one store.

## Task
Create services/api/pipeline/entity_resolution.py:
- Resolution chain (in order):
  1. External ID match: foursquareId or googlePlaceId exact match → merge
  2. Geocode proximity: PostGIS ST_DWithin(<50m) + same ActivityCategory → candidate merge
  3. Fuzzy name: pg_trgm trigram similarity > 0.7 on canonicalName → candidate merge
  4. Content hash: SHA-256 of normalized (name + lat + lng + category) → exact match

- Tiebreaker: when external IDs conflict, geocode proximity wins

- Merge logic:
  - Set losing node: resolvedToId = winning node ID, isCanonical = false
  - Create ActivityAlias row: aliasName = losing node's name, source = losing node's source
  - Migrate all QualitySignals from losing to winning node (update activityNodeId)
  - Migrate all ActivityNodeVibeTag entries

- Canonical name normalization:
  - Lowercase, strip punctuation, collapse whitespace
  - CJK handling: normalize Unicode (NFKC), handle katakana/hiragana equivalence
  - Strip common suffixes: "Restaurant", "Cafe", "Bar", etc.

- Two modes:
  - Incremental: new nodes only (fast, run after each scrape)
  - Full sweep: all nodes (slow, catches retroactive dupes, run weekly)

- PostGIS spatial query for proximity check

Deliverable: scrape same venue from 3 sources → single canonical node, all signals preserved, aliases created.

## Output
services/api/pipeline/entity_resolution.py

## Zone
resolution

## Dependencies
- M-001
- M-002
- M-003
- M-004

## Priority
70

## Target Files
- services/api/pipeline/entity_resolution.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
