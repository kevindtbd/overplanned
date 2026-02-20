# Overplanned — Data Collection Gaps

*February 2026 · Internal*
*Extends: product-ml-features.md, bootstrap-deepdive.md, architecture-addendum-pivot.md*

**Sourcing note:** Each gap below is marked with its basis:
- **[GROUNDED]** — directly contradicted or absent from existing project docs
- **[INFERRED]** — logically implied gap not addressed anywhere in the docs
- **[PARTIAL]** — the doc references the concept but the schema/collection is incomplete

---

## Gap 1 — Search Query Events [GROUNDED]

**What's missing:** There is no `search_events` table or signal type documented anywhere in the project. The `OnboardingSession` schema captures `destination_intent: string | null` (open-questions-deepdive.md), but that's a one-time onboarding field. Ongoing destination search and in-session free text input are not logged as behavioral signals.

**Why it matters:** Every typed search is an intent signal that precedes any accept/reject. "quiet coffee near temple" vs "best ramen tokyo" vs "something chill tonight" are persona signals dressed as queries. The ranking model and the inspiration mode both benefit from this. You're throwing away the highest-intent moment in the session.

**What to collect:**

```sql
CREATE TABLE search_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    session_id      UUID NOT NULL,
    trip_id         UUID REFERENCES trips(id),       -- null if pre-trip browsing

    query_text      TEXT NOT NULL,
    query_context   VARCHAR(30) NOT NULL,
    -- 'destination_search'  -- top-level destination input
    -- 'slot_modification'   -- user typed into a slot change field
    -- 'inspiration_browse'  -- "Show me something" free text
    -- 'mid_trip_input'      -- typed prompt in pivot bar

    result_count    INT,                             -- how many results surfaced
    result_selected BOOLEAN NOT NULL DEFAULT false,  -- did user tap a result?
    selected_activity_id UUID REFERENCES activity_nodes(id),  -- null if no selection
    time_to_select_ms    INT,                        -- null if no selection

    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_search_events_user ON search_events(user_id, occurred_at DESC);
CREATE INDEX idx_search_events_session ON search_events(session_id);
```

**Training use:** Search queries with subsequent activity selection are implicit preference labels. A user who searches "standing bar local" and accepts an `izakaya` is confirming `locals-only` + `drinks-forward` vibe preference more strongly than a passive scroll-and-accept would. Feed into persona dimension tagger. At scale: intent embedding model trained on query → accepted activity pairs.

**Privacy note:** Query text is user-generated free text. Do not use in cross-user training without anonymization. Session-scope only in per-user persona updates.

---

## Gap 2 — Onboarding Funnel Events [GROUNDED]

**What's missing:** The `OnboardingSession` schema (open-questions-deepdive.md) captures the completed session with `time_to_complete_ms`. It does not capture step-level events. There is no documented mechanism to know where users abandon onboarding or which steps cause friction.

**What to collect:**

```sql
CREATE TABLE onboarding_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,           -- anonymous until account creation
    user_id         UUID REFERENCES users(id), -- null until account created

    event_type      VARCHAR(40) NOT NULL,
    -- 'step_entered'
    -- 'step_completed'
    -- 'step_back'         -- user went back
    -- 'abandoned'         -- session ended without completion
    -- 'resumed'           -- returned to incomplete onboarding

    step_name       VARCHAR(50) NOT NULL,
    -- 'fork'             -- Plan a trip / Show me something
    -- 'group_structure'  -- Who's going?
    -- 'scenario_card'    -- vibe card selection
    -- 'tag_cloud'        -- tag selection
    -- 'destination'      -- destination input
    -- 'dates'            -- date selection

    step_index      INT NOT NULL,            -- position in sequence (0-based)
    time_on_step_ms INT,                     -- null if abandoned mid-step
    tags_selected   TEXT[],                  -- only on tag_cloud step
    preset_selected VARCHAR(50),             -- only on scenario_card step
    
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Training use:** Drop-off by step directly informs onboarding design. `time_on_step_ms` on the tag cloud step: very fast = user engaged and decisive (high signal quality), very slow = uncertain (lower signal confidence for the tags selected). Both are useful meta-signals about the persona seed quality.

**Implementation note:** Session ID is generated client-side before account creation. Sync to backend on account creation — do not require backend call until "save my trip" moment (already established in open-questions-deepdive.md as a design constraint: "onboarding works offline").

---

## Gap 3 — Card View Duration Before Decision [INFERRED]

**What's missing:** The `RankingEvent` schema (bootstrap-deepdive.md §4.5) captures `viewed_ids` (activities viewed but no action taken). It does not capture how long each card was viewed before the decision. The existing behavioral signal types (`card_viewed_then_accepted`, `card_skipped`) treat all views as equivalent.

**Why it matters:** A card dismissed after 300ms is noise — the user wasn't reading it. A card viewed for 7 seconds and then dismissed is a meaningful negative signal — something put them off after consideration. These require different training weights.

**What to collect:** Add `card_view_duration_ms` to the existing `RankingEvent` payload. This is a client-side measurement appended at the moment of decision (accept or skip), not a separate event.

```python
# Extend existing RankingEvent (bootstrap-deepdive.md §4.5)
@dataclass
class RankingEvent:
    # ... existing fields ...
    
    # NEW: per-card view duration at decision time
    view_durations_ms: dict[str, int]  # activity_id → ms viewed before decision
    # Example: {'abc-123': 6800, 'def-456': 280, 'ghi-789': 4200}
    # Populated client-side. Only covers the session's decision window.
```

**Training use:** Introduce a `view_quality` modifier to the training label weight:

```python
def get_view_quality_modifier(view_duration_ms: int) -> float:
    if view_duration_ms < 500:
        return 0.3   # barely glanced — low signal
    elif view_duration_ms < 2000:
        return 0.7   # quick read
    elif view_duration_ms < 6000:
        return 1.0   # engaged read — full confidence
    else:
        return 1.2   # extended consideration — slightly boost signal weight
        # cap at 1.2: very long views may also indicate confusion, not just interest
```

A skipped card with `view_duration_ms > 5000` is a strong negative signal. A skipped card with `view_duration_ms < 400` is nearly noise. Apply the modifier when computing training labels, not to the raw signal stored.

---

## Gap 4 — Itinerary Share and Import Signal Feedback [PARTIAL]

**What exists:** The shared-trips.md doc specifies a full import flow with `POST /s/:token_id/import` and mentions that "import signals from accounts flagged as commercial are quarantined" and "social proof signal from import patterns" should feed `ActivityNode.quality_signals`. The commercial protection model is well-designed.

**What's missing:** The specific signal schema for import events feeding back into ActivityNode quality is described in prose ("lightweight input to ActivityNode.quality_signals from aggregated import events") but has no schema definition. The `behavioral_signals` table doesn't document `itinerary_imported` or `activity_import` as signal types.

**What to add:**

```sql
-- Import event logging (extend behavioral_signals or separate table)
CREATE TABLE itinerary_import_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id        UUID NOT NULL,                   -- SharedTripToken reference
    importer_user_id UUID REFERENCES users(id),      -- null if abandoned pre-auth
    sharer_user_id  UUID NOT NULL,

    import_type     VARCHAR(20) NOT NULL,             -- 'full_list' | 'day' | 'activity'
    activity_ids_imported UUID[] NOT NULL,            -- which activities were imported
    destination_trip_id UUID REFERENCES trips(id),

    -- Quality gate signals (mirrors coordinated pumping detection)
    importer_trip_count INT NOT NULL DEFAULT 0,      -- warm vs cold importer
    importer_account_age_days INT NOT NULL DEFAULT 0,
    is_organic      BOOLEAN NOT NULL DEFAULT true,   -- false if flagged for review

    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Aggregated import signal on ActivityNode (nightly batch job)
-- Updates activity_nodes.quality_signals JSONB field:
-- quality_signals->'import_count'           total organic imports
-- quality_signals->'unique_sharer_count'    distinct sharers (independence signal)
-- quality_signals->'warm_importer_ratio'    % of importers with 3+ trips
```

**Training use:** An activity that appears on many independently-created shared trips (high `unique_sharer_count`) is a quality signal distinct from review volume. Already documented as intent in shared-trips.md — this formalizes the schema.

---

## Gap 5 — Weather Context on Behavioral Signals [INFERRED]

**What exists:** The architecture-addendum-pivot.md specifies weather API integration for pivot triggers (`weather change → outdoor slot detector → fallback cached`). The `EnergyModel` in open-questions-deepdive.md includes `weather_drain_modifier: float`. Weather is being consumed.

**What's missing:** Weather context at time-of-signal is not stored on `behavioral_signals`. The ranking model therefore cannot learn weather-conditional preferences: "this user accepts outdoor activities even when rain is forecast" or "this user's energy drops significantly in heat."

**What to add:** Append `weather_context` to the `RankingEvent` payload at write time. Already being fetched — zero additional API cost.

```python
# Extend existing RankingEvent (bootstrap-deepdive.md §4.5)
@dataclass
class WeatherContext:
    condition: str        # 'clear' | 'cloudy' | 'rain' | 'heavy_rain' | 'snow' | 'extreme_heat'
    temp_celsius: float
    precipitation_pct: int  # 0-100
    humidity_pct: int        # 0-100
    wind_kph: float

@dataclass
class RankingEvent:
    # ... existing fields ...
    weather_context: WeatherContext | None  # null if weather API unavailable
```

**Training use:** Weather becomes a feature in the ranking model training examples. At scale: a user who consistently accepts high-energy outdoor activities regardless of `precipitation_pct` has a high `weather_resilience` coefficient — the model can learn to stop penalizing outdoor suggestions for this user when it's raining.

**Privacy note:** Weather is a city-level signal, not location-level. Do not store GPS coordinates — store the city-level weather from the trip's destination city. No additional privacy surface.

---

## Gap 6 — Pre-Trip Itinerary Modification Events [INFERRED]

**What exists:** The pivot system (architecture-addendum-pivot.md) is fully designed for mid-trip modifications. `PivotEvent` has `trigger_type: 'system' | 'user'` but it's designed for in-trip use.

**What's missing:** Pre-trip modifications — when a user opens a generated itinerary before the trip starts and changes it — are a distinct behavioral class with no documented signal type. These tell you about *initial generation quality*, not real-time adaptability. A user who replaces 40% of slots before their trip starts is a strong signal that the LLM ranker got the initial output wrong for this persona.

**What to collect:**

```sql
-- Extend behavioral_signals signal_type enum with:
-- 'pre_trip_slot_swap'     user replaced a slot before trip started
-- 'pre_trip_slot_removed'  user removed a slot before trip started
-- 'pre_trip_slot_added'    user added a slot before trip started
-- 'pre_trip_reorder'       user reordered slots within a day

-- Payload for pre_trip_slot_swap:
{
  "original_activity_id": "uuid",
  "replacement_activity_id": "uuid",
  "slot_index": 2,
  "day_number": 1,
  "days_before_trip_start": 14,   -- how far in advance
  "replacement_source": "search" | "browse" | "pivot_drawer" | "manual_add"
}
```

**Training use:** Pre-trip modifications as negative labels for the initial generation. A slot that was swapped 2+ days before the trip started = the user didn't want it from the beginning. Aggregate pre-trip swap rate per (user, model_version) is a direct measure of initial generation quality — a metric the current admin tooling has no visibility into.

**Key distinction from mid-trip pivots:** `days_before_trip_start > 0` = pre-trip (generation quality signal). `days_before_trip_start = 0` = day-of (real-time adaptability signal). Do not mix these in the same training set for the ranking model.

---

## Gap 7 — Group Poll Proposer Identity [PARTIAL]

**What exists:** Poll votes are captured (group-social.html shows `votes: ['sl', 'jr', 'mia']` per option). The fairness tracker records who's compromised most. Poll options exist as structured data.

**What's missing:** Who proposed each poll option is not documented as a stored field. The open-decisions.md §9 asks "does the fairness tracker ever *do* anything with that information" about group dynamics, but the underlying data gap — `poll_proposer_user_id` is not on the poll options schema — is not called out.

**What to add:**

```sql
-- Add to poll_options (or equivalent) table:
ALTER TABLE poll_options ADD COLUMN proposed_by_user_id UUID REFERENCES users(id);
ALTER TABLE poll_options ADD COLUMN proposed_at TIMESTAMPTZ DEFAULT NOW();

-- Derived metric (computed nightly, stored on group_affinity_cache):
-- proposer_win_rate per member: proposals accepted / proposals made
-- voice_dominance_score: 1 member wins >60% of polls = flag dominant voice pattern
```

**Training use:** `proposer_win_rate` per member is a group dynamic feature for the group affinity model. A group where one member wins 80% of polls with others rarely proposing has a dominant-voice structure — the system should surface more alternatives that give quieter members agency, rather than optimizing purely for the winning preference vector.

**Privacy consideration:** Poll proposer identity within a group is expected group behavior data. All group members agreed to the group trip. No additional consent needed beyond existing group participation consent.

---

## Gap 8 — Relative ActivityNode Acceptance Rate [GROUNDED]

**What exists:** The `RankingEvent` captures `candidate_ids` (the full candidate set shown to the model) and `accepted_id`. The bootstrap-deepdive.md §4.5 explicitly notes: "Log the full candidate set, not just the accepted item. BPR training needs negative examples (what the user saw but didn't pick). Without the candidate_ids field, you can't construct training pairs." This is correctly designed.

**What's missing:** A derived metric on `ActivityNode` itself — how often it's accepted when surfaced — is not computed or stored. The ranking model uses `tourist_score` and `quality_score` as item features. It doesn't know that a specific venue has a 35% acceptance rate when shown to users with a `slow-burn` persona and a 12% rate when shown to `high-energy` users. That acceptance rate *is* a feature, but it requires aggregating across `RankingEvent` logs.

**What to add (nightly batch job):**

```sql
CREATE TABLE activity_acceptance_stats (
    activity_id         UUID REFERENCES activity_nodes(id),
    persona_archetype   VARCHAR(50),     -- null = all archetypes aggregate
    times_surfaced      INT NOT NULL DEFAULT 0,
    times_accepted      INT NOT NULL DEFAULT 0,
    acceptance_rate     FLOAT GENERATED ALWAYS AS 
                            (CASE WHEN times_surfaced > 0 
                             THEN times_accepted::float / times_surfaced 
                             ELSE NULL END) STORED,
    min_sample_size     INT NOT NULL DEFAULT 50,  -- don't trust rates below this
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (activity_id, COALESCE(persona_archetype, '__all__'))
);
```

**Training use:** `acceptance_rate` per (activity, persona_archetype) is a direct training feature for the ranking model — it's behavioral ground truth about fit, not editorial judgment. An activity that scores well on `quality_score` but has a low `acceptance_rate` for a given persona is being over-recommended for that persona. The ranking model should learn this from data, not rely on `tourist_score` alone as a proxy.

**Bootstrap note:** Don't use acceptance rates below the `min_sample_size` threshold (50 surfacings). With too few samples, the rate is noise. Set feature value to null for sparse activities — the ranking model should treat null as "unknown" not "zero."

---

## Gap 9 — Inter-Trip Latency Signal [INFERRED]

**What exists:** `users.last_active_at` is referenced in the persona decay validation job (product-ml-features.md §5.5). `trips` table has status and completion events.

**What's missing:** Time between trip completion and next trip creation is not computed or stored as a metric anywhere. It's derivable from existing tables but not part of any monitoring dashboard or admin tooling surface.

**What to add:**

```sql
-- Derived column on trips table (or separate metrics table):
ALTER TABLE trips ADD COLUMN days_since_last_trip INT;
-- Set at trip creation: (created_at - previous trip's completed_at) in days
-- NULL for first trip

-- Admin dashboard metric:
-- Median inter-trip latency by cohort (free vs pro, trip count bucket)
-- Trend over time: is latency decreasing as the product improves?
```

**Model use:** `days_since_last_trip` is a feature for the persona update model. A user creating their 8th trip 3 days after completing their 7th is a high-frequency traveler — their persona should update faster (shorter behavioral signal half-life, less decay needed between trips). A user who plans one trip per year has a different update cadence. The persona decay constants (product-ml-features.md §5.5) are currently uniform — this signal allows them to be user-adaptive.

**Retention use:** Median inter-trip latency is a North Star retention metric alongside the LLM→ML bootstrap progress metric already defined in admin-tooling.md. Add to the monthly operational checklist.

---

## Gap 10 — ActivityNode Neighborhood Denormalization on Signals [INFERRED]

**What exists:** `activity_nodes` has `geo_cluster_id` and location data. `RankingEvent` has `city` as a top-level field. The item tower (bootstrap-deepdive.md) includes `geo_cluster embedding` as a 16-dim input feature.

**What's missing:** `geo_cluster_id` and `city_area_type` (urban core vs. residential neighborhood vs. out-of-city) are not denormalized onto the `behavioral_signals` payload at write time. The training pipeline has to join back to `activity_nodes` to get these — and that join is stale if an ActivityNode's neighborhood classification has been updated since the signal was logged.

**What to add:** Append to `RankingEvent` payload at write time:

```python
@dataclass
class RankingEvent:
    # ... existing fields ...
    
    # NEW: denormalized location features (from ActivityNode at signal time)
    geo_cluster_id: str      # neighborhood cluster ID
    city_area_type: str      # 'city-core' | 'out-of-city' (from vibe vocabulary location flags)
    # Both snapshotted at write time — immune to subsequent ActivityNode updates
```

**Training use:** If a user consistently accepts `city-core` activities and skips `out-of-city` ones, `city_area_type` is a persona dimension signal. Currently this would require a join that may return stale data. Denormalizing at write time costs a few bytes per signal and eliminates the stale-join problem entirely.

---

## Priority Implementation Order

| Gap | Priority | Effort | Reason |
|---|---|---|---|
| **3** — Card view duration | High | Low | Client-side only, extends existing RankingEvent, immediate ranking model value |
| **5** — Weather context | High | Low | Already fetching weather, just append to payload, zero API cost |
| **10** — Geo denormalization | High | Low | Append at write time, eliminates stale join problem permanently |
| **1** — Search query events | High | Medium | New table + client instrumentation, high intent signal being lost every session |
| **2** — Onboarding funnel | Medium | Medium | New event type, session-scoped before account creation adds complexity |
| **6** — Pre-trip modifications | Medium | Medium | New signal_type values, distinguish from mid-trip pivots in training |
| **8** — Acceptance rate stats | Medium | Medium | Nightly batch job, new derived table, strong ranking feature at scale |
| **4** — Share/import feedback | Medium | Medium | Schema partially specified in shared-trips.md, formalize and implement |
| **7** — Poll proposer identity | Low | Low | Schema addition only, group affinity model benefit at scale |
| **9** — Inter-trip latency | Low | Low | Derived metric, retention dashboard value, persona decay calibration |

Gaps 3, 5, and 10 should ship with v1 — they require minimal new infrastructure and directly improve ranking model training quality from day one. Gaps 1 and 2 are the highest-value new data surfaces and should be in the first-month post-launch batch.

---

*Overplanned Internal · February 2026*
*All gaps grounded in or inferred from: product-ml-features.md, bootstrap-deepdive.md, architecture-addendum-pivot.md, open-questions-deepdive.md, shared-trips.md, admin-tooling.md*
*Sourcing notation: [GROUNDED] = absent from docs | [PARTIAL] = incomplete in docs | [INFERRED] = logical gap not addressed*
