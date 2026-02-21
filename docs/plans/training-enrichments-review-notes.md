# Plan Review Notes: Training Data Enrichments

*Reviewed: 2026-02-20*
*Reviewer: deepen-plan*

---

## Refinements Applied

### 1. Swap pairing verified in data
Ran a query confirming all 1,044 swapped slots have matching pairs at the
same (tripId, dayNumber, sortOrder). Zero orphans. Join logic is solid.

### 2. Trip realism: only flip trips without post_trip signals
Flipping completed trips to 'planning' would create inconsistency if those
trips have post_loved/post_disliked signals. Fixed: only select trips with
no post_trip phase signals as abandoned candidates. Naturally represents
users who didn't engage deeply enough to leave reflections.

### 3. Discovery: graceful handling of missing affinities
Users without category_affinities PersonaDimension: skip and count.
Threshold: >10 skipped = add to errors list, otherwise warning only.
Missing a few users won't affect BPR quality.

### 4. Weather: only tag signals with slotId
Passive signals without slotId can't be day-level weather-tagged.
Skip them — weather features are slot-level decisions.

---

## No Critical Issues Found

All 5 enrichments are clean additive operations on existing data.
No schema changes needed. The main risk was data consistency in
Enrichment 6 (trip status flip), resolved by the post_trip signal filter.

---

## Ready for Agent Review

Recommend dispatching: data-scientist, backend-architect.
Focus areas:
- data-scientist: Discovery signal distribution quality, intention type weights
- backend-architect: Query performance for the weather UPDATE (43K rows with 3-way join)
