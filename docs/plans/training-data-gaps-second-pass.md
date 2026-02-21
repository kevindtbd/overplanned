# Training Data Gaps — Second Pass

After fixing the 3 blockers (RawEvent, PersonaDimension, ModelRegistry),
these quality improvements should be addressed before any real BPR training run.

## 1. PivotEvent Records

The persona seeder already computes swaps (`_pick_swap_node`, `wasSwapped=True`)
but doesn't write PivotEvent rows. For each swap, generate:
- `trigger_type='user_request'`
- `status='accepted'`
- `response_time_ms` between 500-3000ms
- Link `original_node_id` and `selected_node_id`

Low effort — swap logic already exists, just needs the PivotEvent INSERT.

## 2. IntentionSignal Seeding

For 20-30% of `slot_skip` signals, write an IntentionSignal with:
- `intention_type`: weighted random from `not_interested`, `bad_timing`,
  `too_far`, `already_visited`, `weather`, `group_conflict`
- `confidence=1.0`, `source='user_explicit'`, `user_provided=true`

These are the highest-confidence labels the system can produce.
Critical for distinguishing "wrong vibe" from "wrong logistics."

## 3. Discovery Swipe Signals

The offline discovery surface (swipe deck) has zero training data.
For ~30% of users, generate:
- `discover_swipe_right` for high-affinity nodes
- `discover_swipe_left` for low-affinity nodes
- `discover_shortlist` for a subset of swipe_rights

BPR needs to learn the discovery context separately from the itinerary context.

## 4. WeatherContext on Outdoor/Active Signals

All 220K signals have `weatherContext=null`. For outdoor and active category
slots, assign plausible weather:
- Tokyo: seasonal (rainy June, humid Aug, mild Oct-Nov)
- NYC: seasonal (cold Jan-Feb, humid Jul-Aug, mild Sep-Oct)
- CDMX: rainy season Jun-Oct, dry Nov-May

Weight toward the trip's date range. Low effort, high value for the
Item Tower weather feature.

## 5. QualitySignal Source Diversity (Audit First)

Check `QualitySignal` rows per city. If single-source or empty, the
tourist/local divergence calculation is a fiction. Seed synthetic
QualitySignal rows with 2-3 sources per node (en_reddit, foursquare,
tabelog for Tokyo).

## 6. Trip Completion Realism

Currently all trips >8 days old are "completed." Add some abandoned
planning trips (status='planning' from 60+ days ago) and short completed
trips from recent dates for more realistic distribution.
