# BPR Training Blockers — Design

Three blockers preventing a BPR training run against the synthetic dataset.

## Current State

- 747 shadow users, 2,744 trips, 85K slots, 220K behavioral signals
- 3 cities: Tokyo (20 nodes), NYC (72 nodes), Mexico City (73 nodes)
- Missing: RankingEvent logs, PersonaDimension table, ModelRegistry entries

---

## Blocker 1: RankingEvent Schema + Seeding

### Why it blocks BPR

BPR needs (user, positive_item, negative_item) training triples. The negative
items come from "what the model offered but the user didn't pick." Without
ranking logs, negatives can only be inferred from skips in the same trip —
a much weaker, noisier signal.

### Schema: New `RankingEvent` model

```prisma
model RankingEvent {
  id                 String   @id @default(uuid())
  userId             String
  tripId             String
  sessionId          String?
  dayNumber          Int
  modelName          String   // llm_ranker, bpr, two_tower
  modelVersion       String   // 0.1.0
  candidateIds       String[] // top 20 items shown to the model
  rankedIds          String[] // model's output ranking (selected items)
  selectedIds        String[] // what user actually confirmed
  surface            String   // itinerary | discovery | pivot
  shadowModelName    String?  // shadow mode: competing model name
  shadowModelVersion String?  // shadow mode: competing model version
  shadowRankedIds    String[] // shadow mode: competing model's ranking
  latencyMs          Int?
  createdAt          DateTime @default(now())

  @@index([userId, createdAt])
  @@index([tripId, dayNumber])
  @@index([modelName, modelVersion])
}
```

### Seeding approach

One RankingEvent per day per trip (~15K events total):
- `candidateIds` = top 20 ActivityNodes by affinity in that trip's city
  (not all nodes — mirrors realistic "model scored and filtered" behavior)
- `rankedIds` = candidateIds reordered by affinity (high first)
- `selectedIds` = the nodes that ended up in that day's ItinerarySlots
- `modelName='llm_ranker'`, `modelVersion='0.1.0'`
- `surface='itinerary'`
- `latencyMs` = random 200-800ms
- `shadowModelName/Version/RankedIds` = null (no shadow model yet)

Affinity source: read PersonaDimension rows (not Trip.personaSeed JSON).
This validates the materialization pipeline end-to-end and maintains a
single source of truth. PersonaDimension must be seeded before RankingEvents.

### Idempotency

DELETE + re-INSERT for shadow data, wrapped in an explicit transaction.
On re-run:
1. BEGIN transaction
2. Delete all RankingEvents where userId is a shadow user
3. Re-insert fresh data
4. COMMIT

This allows tweaking affinity math or adding dimensions without
stale rows mixing with new ones.

### BPR training pair construction

From each RankingEvent:
```
positive_items = selectedIds
negative_items = candidateIds - selectedIds
For each (user, positive, negative): one BPR triple
```

At ~15K events with avg 3-4 selected from 20 candidates = ~15K * 3.5 * 16.5 =
~865K potential training triples. More than enough.

### Known limitation: Tokyo

Tokyo has only 20 nodes. With top-20 candidate selection, every Tokyo user
sees the same candidate set — item embeddings will be heavily correlated.
Exclude Tokyo from BPR training or weight NYC/CDMX examples more heavily
until the Tokyo catalog grows past ~50 nodes.

---

## Blocker 2: PersonaDimension Schema + Materialization

### Why it blocks BPR

The documented training extraction query joins:
```sql
JOIN persona_dimensions p ON p.user_id = s.user_id
  AND p.dimension = 'pace_preference'
```

This table doesn't exist. Persona data is buried in `Trip.personaSeed` JSON.

### Schema: New `PersonaDimension` model

```prisma
model PersonaDimension {
  id         String   @id @default(uuid())
  userId     String
  dimension  String   // pace_preference, budget_sensitivity, etc.
  value      String   // the dimension value
  confidence Float    @default(1.0)
  source     String   @default("onboarding")
  updatedAt  DateTime @updatedAt
  createdAt  DateTime @default(now())

  @@unique([userId, dimension])
  @@index([userId])
  @@index([dimension, value])
}
```

### Materialization approach

For each of 747 shadow users, extract from their first Trip's personaSeed JSON:

| dimension | source field | example value |
|---|---|---|
| pace_preference | persona_seed.pace | leisurely |
| budget_sensitivity | persona_seed.budget_tier | low |
| cuisine_openness | persona_seed.cuisine_openness | 0.85 |
| social_mode | persona_seed.social_mode | solo |
| time_orientation | persona_seed.time_orientation | night_owl |
| primary_interest | persona_seed.primary_interest | food |
| trip_count | derived: COUNT(trips) | returning |
| category_affinities | persona_seed.category_affinities | JSON blob |

8 dimensions x 747 users = 5,976 rows.
All with confidence=1.0, source='onboarding'.

`exploration_radius` was dropped — it's deterministically derived from `pace`
(slow=neighborhood, moderate=district, packed=city_wide). Zero independent
information for BPR.

Replaced with:
- `trip_count`: first_trip (1 trip) / returning (2-3) / frequent (4+).
  Gives BPR a cold-start vs warm user differentiation hook.
- `category_affinities`: the jittered affinity vector as a JSON string.
  Eliminates the reconstruction error between signal generation (jittered)
  and RankingEvent ranking (would otherwise be un-jittered). The seeder
  reads this directly instead of recomputing from dimension labels.

### Idempotency

DELETE + re-INSERT for shadow data, wrapped in an explicit transaction.
On re-run:
1. BEGIN transaction
2. Delete all PersonaDimensions where userId is a shadow user
3. Re-insert fresh data from Trip.personaSeed JSON
4. COMMIT

---

## Blocker 3: ModelRegistry Entries + Backfill

### Why it blocks BPR

Shadow mode needs a production model anchor. BehavioralSignal.modelVersion
is null on all 220K signals — signals can't be attributed to a model version.

### Seed entries

Two rows in ModelRegistry:

1. LLM Ranker (production baseline):
   - modelName: 'llm_ranker'
   - modelVersion: '0.1.0'
   - stage: 'production'
   - modelType: 'llm_ranking'
   - description: 'Claude Sonnet-based ranking, bootstrap phase'

2. BPR (staging placeholder):
   - modelName: 'bpr'
   - modelVersion: '0.0.0'
   - stage: 'staging'
   - modelType: 'collaborative_filtering'
   - description: 'BPR placeholder, awaiting first training run'

### Backfill

```sql
UPDATE "BehavioralSignal"
SET "modelVersion" = 'llm_ranker:0.1.0'
WHERE "userId" IN (
  SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%'
)
AND "modelVersion" IS NULL;
```

~220K rows updated. Single UPDATE, no loop needed. The WHERE clause
properly scopes to shadow users via email prefix. The IS NULL guard
makes this safe to re-run (idempotent).

---

## Schema Changes (non-blocker)

### Add missing index to ItinerarySlot

```prisma
@@index([tripId, dayNumber])
```

Needed for the RankingEvent seeder's per-trip slot queries and the
validation query's 3-way join. Currently missing.

---

## Implementation Order

1. Schema: Add RankingEvent + ItinerarySlot index to schema.prisma
2. Migration: prisma db push
3. Seed ModelRegistry (2 rows) + backfill modelVersion (1 UPDATE)
4. Materialize PersonaDimension (5,976 rows)
5. Seed RankingEvents (~15K rows)

Steps 3-5 go in a single seeder script: `services/api/pipeline/training_data_seeder.py`
Every DELETE + re-INSERT block wrapped in explicit transactions.

---

## Validation

After all 3 blockers are fixed, this query should return rows:

```sql
SELECT
  bs."signalType",
  bs."modelVersion",
  pd_pace.value as pace,
  pd_budget.value as budget,
  re."modelName" as ranking_model,
  array_length(re."candidateIds", 1) as candidates_shown
FROM "BehavioralSignal" bs
JOIN "ItinerarySlot" isl
  ON isl.id = bs."slotId"
JOIN "PersonaDimension" pd_pace
  ON pd_pace."userId" = bs."userId" AND pd_pace.dimension = 'pace_preference'
JOIN "PersonaDimension" pd_budget
  ON pd_budget."userId" = bs."userId" AND pd_budget.dimension = 'budget_sensitivity'
LEFT JOIN "RankingEvent" re
  ON re."tripId" = bs."tripId"
  AND re."userId" = bs."userId"
  AND re."dayNumber" = isl."dayNumber"
WHERE bs."userId" IN (SELECT "id" FROM "User" WHERE "email" LIKE 'shadow-%')
AND bs."slotId" IS NOT NULL
LIMIT 10;
```

The 3-way join through ItinerarySlot on dayNumber prevents fan-out
(one RankingEvent per day, many BehavioralSignals per day).

---

## Out of Scope (Noted for Later)

- Admin endpoint auth dependency (pre-existing gap across all /admin/* routes)
- `is_synthetic` boolean on User table (email pattern works for now)
- Tokyo catalog expansion (need >50 nodes before Tokyo BPR data is useful)
