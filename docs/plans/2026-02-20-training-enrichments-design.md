# Training Data Enrichments — Design

Five post-blocker enrichments to improve BPR training data quality.
All operate on existing 765 shadow users / 225K signals.

Code: `enrich_training_data()` in `training_data_seeder.py` — separate
function from the blocker seeder, separate `/admin/seeding/enrich` endpoint.

## Pre-requisite: Add BehavioralSignal.slotId Index

```prisma
@@index([slotId])   // partial: WHERE slotId IS NOT NULL
```

Needed for WeatherContext UPDATE and IntentionSignal joins. Without this,
both queries do a seqscan on 225K rows.

---

## Enrichment 1: PivotEvent Records

1,044 swapped slots exist with `wasSwapped=true` but zero PivotEvent rows.

### Approach

For each swapped slot, find the (skipped, replacement) pair by joining on
`(tripId, dayNumber, sortOrder)` — verified: all 1,044 swaps have a matching
pair at the same position, zero orphans.

Insert PivotEvent:
- `tripId`, `slotId` = the original (skipped) slot
- `triggerType` = `'user_request'`
- `originalNodeId` = skipped slot's activityNodeId
- `selectedNodeId` = replacement slot's activityNodeId
- `alternativeIds` = `[selectedNodeId]`
- `status` = `'accepted'`
- `responseTimeMs` = random 500-3000ms

### Idempotency

DELETE PivotEvents where tripId belongs to a shadow user + re-INSERT
in transaction. Scoped to shadow user ownership, not triggerType.

### Expected

~1,044 PivotEvent rows.

---

## Enrichment 2: IntentionSignal Seeding

12,462 `slot_skip` signals with zero IntentionSignals explaining why.

### Approach

For 25% of skip signals, capped per user at `max(1, user_skip_count * 0.25)`:
- `intentionType` weighted random:
  - `not_interested` (32%) — wrong vibe
  - `bad_timing` (17%) — schedule conflict
  - `too_far` (15%) — logistics
  - `already_visited` (10%) — repeat
  - `weather` (10%) — 2x weight for outdoor/active category skips
  - `price_mismatch` (8%) — only when node priceLevel >= 3 AND user budget = 'low'
  - `group_conflict` (5%) — group trips only
  - fallback to `not_interested` (3%) — rounding
- `confidence` = 1.0
- `source` = `'user_explicit'`
- `userProvided` = true

Special rules:
- `group_conflict` only fires for users with social_mode containing "group"
- `weather` gets 2x weight for outdoor/active category skips
- `price_mismatch` only fires when priceLevel >= 3 AND budget_sensitivity = 'low'
- Per-user cap ensures coverage across all 300 archetypes, not concentrated
  in high-skip packed-pace personas

### Idempotency

DELETE shadow IntentionSignals + re-INSERT in transaction.

### Expected

~3,100 IntentionSignal rows.

---

## Enrichment 3: Discovery Swipe Signals

Zero discovery surface data. BPR needs to learn discovery context
separately from itinerary context.

### Approach

For ~30% of shadow users (~230), per trip:
- Pick 15 nodes from the trip's city (mix of high and low affinity)
- Per-user noise floor: +-15% jitter on thresholds (seeded from user index)
- Roll outcome based on affinity (after noise):
  - affinity > 0.6: 65% swipe right, 35% left
  - affinity 0.3-0.6: 40% right, 60% left
  - affinity < 0.3: 8% right, 92% left
- Swipe-rights with affinity > 0.7: 30% chance of `discover_shortlist`

The lower high-affinity rate (65% vs original 80%) and per-user noise
prevent discovery from being a redundant echo of itinerary confirms.
Forces BPR to learn item-level features from discovery context.

Insert BehavioralSignals (batched via executemany):
- `discover_swipe_right`, `discover_swipe_left`, `discover_shortlist`
- `tripPhase` = `'pre_trip'`
- `slotId` = null (not tied to a slot)
- `signalValue` = 1.0 for right/shortlist, -1.0 for left

Insert one RankingEvent per discovery session:
- `surface` = `'discovery'`
- `candidateIds` = all 15 shown nodes
- `rankedIds` = sorted by affinity
- `selectedIds` = swipe-rights only
- `modelName` = `'llm_ranker'`, `modelVersion` = `'0.1.0'`

### Missing data handling

Users without `category_affinities` PersonaDimension: skip and count.
If skipped > 10, add to errors list. Otherwise log warning only.

### Idempotency

DELETE shadow `discover_*` BehavioralSignals + discovery-surface
RankingEvents, then re-INSERT in transaction.

### Expected

~12,700 swipe signals + ~850 RankingEvents (surface='discovery').

---

## Enrichment 4: WeatherContext Backfill

43,595 outdoor/active signals with null weatherContext.

### Approach

Join path: BehavioralSignal -> ItinerarySlot (dayNumber) -> Trip (startDate, city).
Only tag signals WITH a slotId. Passive signals without slotId are skipped.

Compute month from trip's `startDate + dayNumber days`.

Weather format: pipe-delimited `label|temp_c|precip_index` to give the
Item Tower both categorical and numeric features without a schema change.
The weatherContext column is String — pipe format is parseable.

Weather data by city and month:
- **Tokyo**: Jan-Feb `cold_clear|6|0.1`, Mar-Apr `mild_sunny|15|0.2`,
  May `warm_humid|22|0.3`, Jun `rainy_warm|24|0.7`,
  Jul-Aug `hot_humid|30|0.5`, Sep `warm_rainy|26|0.6`,
  Oct-Nov `mild_sunny|17|0.2`, Dec `cold_clear|8|0.1`
- **NYC**: Jan-Feb `cold_clear|2|0.2`, Mar-Apr `cool_windy|10|0.3`,
  May-Jun `warm_sunny|22|0.2`, Jul-Aug `hot_humid|29|0.3`,
  Sep-Oct `mild_sunny|18|0.2`, Nov `cool_cloudy|8|0.4`,
  Dec `cold_clear|3|0.3`
- **CDMX**: Jan-May `dry_warm|22|0.1`, Jun-Oct `rainy_warm|20|0.6`,
  Nov-Dec `dry_cool|17|0.1`

Filter: outdoor/active category nodes, shadow users, weatherContext IS NULL,
slotId IS NOT NULL.

### Idempotency

WHERE weatherContext IS NULL — safe to re-run.

### Expected

~43,595 signals updated (may be slightly fewer after slotId filter).

---

## Enrichment 6: Trip Completion Realism

2,793 completed + 8 active + 0 everything else. Target ~10% rebalance.
Note: cosmetic for current BPR run, but future-proofs for User Tower
features that use trip metadata.

### Abandoned planning trips (~280)

Select ~280 oldest completed trips that have NO post_trip phase signals
(no post_loved, post_disliked). This avoids data consistency issues —
trips without post-trip reflections naturally look like abandoned planning.

UPDATE status to `'planning'`, clear `completedAt` to null.
Existing slots/signals stay (planning-phase signals are valid training data).

### Shortened recent trips (~80)

Take ~80 completed trips with startDate 30-90 days ago.
UPDATE endDate to 2-3 days after startDate (shorten duration).
Existing slots beyond new endDate stay — "planned but didn't get to."

### Idempotency

Check-before-write: if any shadow trips already have status='planning',
skip the abandoned step. If any have duration <= 2 days, skip shortening.

### Expected

~280 trips -> planning, ~80 trips shortened.

---

## Implementation Order

0. Add BehavioralSignal.slotId index (schema change + prisma db push)
1. PivotEvent records (reads ItinerarySlot swaps)
2. IntentionSignal seeding (reads BehavioralSignal skips)
3. Discovery swipe signals (reads PersonaDimension affinities + ActivityNodes)
4. WeatherContext backfill (UPDATE only, no deletes)
5. Trip completion realism (UPDATE only, no deletes)

All in `enrich_training_data()` in `training_data_seeder.py`.
New endpoint: `POST /admin/seeding/enrich`.
