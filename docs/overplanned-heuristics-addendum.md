# Overplanned — Heuristics Addendum

*February 2026 · Internal*
*Extends: bootstrap-deepdive.md, vibe-vocabulary.md, product-ml-features.md*
*Status: Approved — implement alongside scaffold*

These heuristics address gaps in the current architecture across three areas: vibe extraction, behavioral ingestion, and training signal quality. Each is additive — nothing here replaces existing design decisions.

---

## 1. Vibe Extraction Heuristics

### 1.1 Temporal Context Tags (new tag category)

The current 42-tag vocabulary has no temporal or seasonal dimension. Community text is full of it: "only worth it before the crowds hit at 8am," "perfect in October when the leaves turn," "closed in August — whole neighborhood shuts down." This signal goes unextracted.

Add a `temporal_context` tag category to the vibe vocabulary. These are supplementary to the main vibe tags — they do not count toward the 3–8 tag cap per ActivityNode, they live in a separate `temporal_signals` array.

```python
TEMPORAL_SIGNALS = {
    "time_of_day": [
        "best-before-9am",        # "go early", "opens at 7", "pre-crowd"
        "lunch-only",             # "closes at 2", "lunch service only"
        "evening-only",           # "dinner service", "opens at 6"
        "late-night",             # "open past midnight", "after 10pm"
        "all-day",                # no strong timing preference
    ],
    "seasonal": [
        "spring-peak",            # cherry blossom, etc.
        "summer-avoid",           # "unbearably hot", "closed in August"
        "autumn-best",            # foliage, harvest
        "winter-only",            # seasonal operation
        "avoid-holiday-weeks",    # "zoo during Golden Week", etc.
        "year-round",             # no seasonal variation
    ],
    "weekly": [
        "weekday-only",           # "closes weekends", "packed on Sat"
        "weekend-market",         # only operates weekends
        "avoid-weekends",         # "tourist hell on Sat/Sun"
    ],
    "operational": [
        "reservation-required",   # "can't walk in", "book months ahead"
        "queue-expected",         # "always a line but moves fast"
        "cash-only",              # (already gets UI treatment — keep here too)
        "seasonal-menu",          # "menu changes with season"
    ]
}
```

Extraction confidence threshold stays at 0.75. Temporal signals are only applied when the reviewer explicitly states a time condition — not inferred. "Go early" = `best-before-9am`. "Good anytime" = `all-day`. Ambiguous = no temporal tag applied.

**Serving impact:** `temporal_signals` are used by the constraint solver at itinerary generation time, not by the ranking model. A `lunch-only` venue is suppressed from evening slots deterministically. A `spring-peak` venue gets a confidence decay modifier in non-spring months — not suppressed, but ranked lower.

---

### 1.2 Tourist Score Velocity (overrated detector upgrade)

The current `tourist_score` is a scalar computed from source divergence at a point in time. It doesn't capture trajectory. A venue that was a hidden gem 18 months ago and now leads every travel listicle has crossed over — but the static score reflects current state only.

Add `tourist_score_velocity` computed over rolling 6-month windows:

```python
def compute_tourist_score_velocity(activity_node_id: str) -> float:
    """
    Computes rate of change in tourist_score over the last 6 months.
    Positive = becoming more touristy. Negative = locals reclaiming.
    """
    snapshots = query("""
        SELECT tourist_score, computed_at
        FROM activity_node_score_history
        WHERE activity_node_id = %s
          AND computed_at > NOW() - INTERVAL '6 months'
        ORDER BY computed_at ASC
    """, activity_node_id)
    
    if len(snapshots) < 3:
        return 0.0  # insufficient history, no velocity signal
    
    # Linear regression slope over time
    scores = [s.tourist_score for s in snapshots]
    times = [(s.computed_at - snapshots[0].computed_at).days for s in snapshots]
    slope = linregress(times, scores).slope  # score points per day
    
    return slope * 30  # normalize to monthly rate of change

# Thresholds
VELOCITY_WARN = 0.05   # score rising 0.05/month → flag for review
VELOCITY_SUPPRESS = 0.10  # score rising 0.10/month → apply temporary rank penalty
```

Schema addition required:
```sql
ALTER TABLE activity_nodes ADD COLUMN tourist_score_velocity FLOAT DEFAULT 0.0;
ALTER TABLE activity_nodes ADD COLUMN tourist_score_computed_at TIMESTAMPTZ;

CREATE TABLE activity_node_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_node_id UUID REFERENCES activity_nodes(id),
    tourist_score FLOAT NOT NULL,
    quality_score FLOAT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Nightly job appends a row per node. Retained 12 months.
CREATE INDEX idx_score_history_node_time 
    ON activity_node_score_history(activity_node_id, computed_at DESC);
```

The velocity signal is surfaced in the admin tooling source freshness dashboard. A venue with `tourist_score_velocity > 0.10` gets a "trending touristy" flag for human review. The ranking model doesn't consume velocity directly — it's a modifier applied deterministically by the constraint solver.

---

### 1.3 Cross-Reference Independence Weighting

The current cross-reference confidence scorer counts how many sources mention a venue. It doesn't account for source independence — two blog posts from the same editorial network (e.g., Eater NYC and Eater LA both mentioning the same chain) should not count as two independent signals.

Add a `source_cluster_id` to the blog source registry. Sources with shared ownership/editorial are in the same cluster. Cross-reference confidence counts clusters, not raw sources.

```python
SOURCE_CLUSTERS = {
    "vox_media": ["eater", "curbed", "polygon"],          # same editorial parent
    "ny_mag": ["grubstreet", "curbed", "vulture"],        # same editorial parent
    "conde_nast": ["bon_appetit", "gourmet_traveler"],    # same editorial parent
    "timeout_global": ["timeout_tokyo", "timeout_london", "timeout_nyc"],
    # Independent sources have no cluster — each counts as its own cluster
}

def compute_cross_ref_confidence(source_mentions: list[dict]) -> float:
    seen_clusters = set()
    for mention in source_mentions:
        cluster = SOURCE_CLUSTERS.get(mention['source_id'], mention['source_id'])
        seen_clusters.add(cluster)
    
    # Confidence scales with independent source count, not raw mention count
    independent_count = len(seen_clusters)
    return min(1.0, independent_count * 0.20)  # 5 independent sources = 1.0
```

---

### 1.4 Author Type Confidence Decay

The extraction pipeline classifies author type as tourist / local-resident / expat / unknown. This classification degrades over time — a "local-resident" review from 2019 may reflect a neighborhood that has since gentrified significantly. Author type should decay with content age.

```python
def effective_author_weight(author_type: str, content_age_days: int) -> float:
    base_weights = {
        "local-resident": 3.0,   # current: carries 3x signal weight
        "expat": 2.0,
        "tourist": 1.0,
        "unknown": 0.8,
    }
    
    # Decay for content age
    # Local knowledge decays faster in high-velocity neighborhoods
    decay_halflife_days = {
        "local-resident": 730,   # 2-year half-life for local knowledge
        "expat": 548,            # 18 months
        "tourist": 365,          # 1 year (tourist observations decay faster)
        "unknown": 365,
    }
    
    base = base_weights.get(author_type, 0.8)
    halflife = decay_halflife_days.get(author_type, 365)
    decay = 0.5 ** (content_age_days / halflife)
    
    return base * decay
```

This doesn't change the extraction pipeline — it changes how mentions are weighted in the cross-reference aggregation step.

---

## 2. Behavioral Ingestion Heuristics

### 2.1 No-Show Disambiguation

Current gap: when a user doesn't attend a scheduled slot (no GPS presence, no manual check-in, no pivot event recorded), the system has no signal. Treating this as a skip would be wrong — it's most often a scheduling drift, not a rejection.

```python
class SlotCompletionSignal(Enum):
    CONFIRMED_ATTENDED = "confirmed_attended"    # GPS + time confirms presence
    LIKELY_ATTENDED = "likely_attended"          # no GPS but no conflicting signal
    CONFIRMED_SKIPPED = "confirmed_skipped"      # user manually marked skip
    PIVOT_REPLACED = "pivot_replaced"            # pivot event exists for this slot
    NO_SHOW_AMBIGUOUS = "no_show_ambiguous"      # no signal at all

def classify_slot_outcome(slot_id: str, trip_id: str, user_id: str) -> SlotCompletionSignal:
    pivot_event = get_pivot_event_for_slot(slot_id)
    if pivot_event:
        return SlotCompletionSignal.PIVOT_REPLACED
    
    manual_skip = get_manual_skip(slot_id, user_id)
    if manual_skip:
        return SlotCompletionSignal.CONFIRMED_SKIPPED
    
    # No signal = ambiguous. Never treat as negative.
    return SlotCompletionSignal.NO_SHOW_AMBIGUOUS

# Signal weights for ranking model training:
SLOT_OUTCOME_LABEL = {
    SlotCompletionSignal.CONFIRMED_ATTENDED: 1.0,    # strong positive
    SlotCompletionSignal.LIKELY_ATTENDED: 0.6,       # soft positive
    SlotCompletionSignal.CONFIRMED_SKIPPED: -0.5,    # negative
    SlotCompletionSignal.PIVOT_REPLACED: None,        # use pivot signal instead
    SlotCompletionSignal.NO_SHOW_AMBIGUOUS: None,     # excluded from training
}
```

`NO_SHOW_AMBIGUOUS` slots are excluded from ranking model training data entirely. They are not null signals, they are unknown signals — a meaningful distinction.

---

### 2.2 Compromise Satisfaction Signal (Group)

Current gap: the fairness tracker records who compromised, not whether they were satisfied with the compromise. A user who compromised on a slot but rated it highly afterward is a very different signal than one who compromise and then disengaged.

Add a one-time post-activity micro-prompt targeted specifically at compromised slots:

```
CompromiseSatisfactionEvent {
    slot_id: string
    user_id: string
    was_compromise: boolean          // did this user's preference lose the group vote?
    satisfaction: 'glad' | 'neutral' | 'regret' | null   // null = prompt ignored
    prompt_shown_at: timestamp
    responded_at: timestamp | null
    time_to_respond_ms: number | null
}
```

UX rules (same pattern as post-pivot thumbs):
- Shown once, 6 seconds after activity completion
- Auto-dismisses if no response — `null`, not negative
- Never shown twice for the same slot
- Never shown for non-compromise slots (don't interrupt flow)
- Copy: "Glad you went?" (yes / sort of / not really)

This signal feeds the group affinity model specifically, not the individual ranking model. A user who consistently responds "not really" to compromised slots on group trips gets a higher `divergence_score` in the group affinity matrix — the system should surface more group-compatible alternatives upfront.

---

### 2.3 Dwell Time Calibration by Category

Current signal: dwell time relative to scheduled slot duration. The gap: a 45-minute museum visit vs. a 45-minute ramen visit are completely different behavioral patterns. Calibrate dwell time signals by category to make them comparable.

```python
# Expected dwell time ranges by category (in minutes)
# Used to normalize raw dwell time into a -1 to +1 engagement signal
CATEGORY_DWELL_NORMS = {
    "restaurant_sit_down": (45, 90),      # min, max expected
    "ramen_counter": (20, 40),
    "bar": (45, 150),
    "museum_large": (90, 180),
    "museum_small": (30, 75),
    "temple_shrine": (15, 45),
    "market": (30, 90),
    "park": (30, 120),
    "neighborhood_walk": (45, 120),
    "coffee_shop": (20, 60),
    "viewpoint": (10, 30),
}

def compute_dwell_engagement(category: str, actual_minutes: int) -> float:
    """
    Returns engagement signal: 
    -1.0 = left far earlier than expected (disengaged)
     0.0 = within expected range (neutral)
    +1.0 = stayed far longer than expected (engaged)
    """
    if category not in CATEGORY_DWELL_NORMS:
        return 0.0  # unknown category → neutral
    
    min_expected, max_expected = CATEGORY_DWELL_NORMS[category]
    
    if actual_minutes < min_expected * 0.6:
        # Left significantly earlier than expected
        return max(-1.0, (actual_minutes - min_expected) / min_expected)
    elif actual_minutes > max_expected * 1.4:
        # Stayed significantly longer than expected
        return min(1.0, (actual_minutes - max_expected) / max_expected)
    else:
        return 0.0  # within normal range → don't signal either way
```

Zero dwell (no-show) stays as `NO_SHOW_AMBIGUOUS` per 2.1. Dwell engagement is only computed when actual time spent is measurable (GPS presence or manual check-in with time).

---

### 2.4 Sequential Acceptance Decay

If a user accepts the first 3 recommendations in a row without any modification, they are either very satisfied or disengaged. These are very different states. Add a `sequential_acceptance_streak` counter per session and apply a confidence decay to signals from long streaks.

```python
def get_signal_confidence_modifier(signal: BehavioralSignal, session: TripSession) -> float:
    streak = session.sequential_acceptance_streak
    
    if streak <= 3:
        return 1.0   # normal confidence
    elif streak <= 6:
        return 0.7   # mild decay — user may be on autopilot
    elif streak <= 10:
        return 0.4   # significant decay — likely disengaged
    else:
        return 0.2   # very low confidence — passive scrolling, not active preference
    
    # Streak resets on: any modification, any pivot initiation, any explicit skip
```

The raw signal is still logged at full value — this modifier only applies when the training data extraction job computes the label weight for ranking model training. The signal is real, the confidence is qualified.

---

### 2.5 Trip Day Fatigue Prior

Behavioral signals on day 5 of a 7-day trip carry different meaning than day 1 signals. A user accepting a lower-energy activity on day 5 is likely expressing fatigue, not a stable preference shift. The persona updater should apply a `trip_day_context_weight` when incorporating persona dimension changes.

```python
TRIP_DAY_CONTEXT_WEIGHT = {
    1: 0.6,    # day 1: recency bias, excitement inflation
    2: 0.8,    # settling in
    3: 1.0,    # most reliable signal
    4: 1.0,    
    5: 0.7,    # fatigue may be distorting preferences
    6: 0.6,    
    7: 0.5,    # end-of-trip effect
}

def get_persona_update_weight(signal: BehavioralSignal) -> float:
    base_weight = SIGNAL_TYPE_WEIGHTS[signal.signal_type]
    day_weight = TRIP_DAY_CONTEXT_WEIGHT.get(signal.trip_day_number, 0.8)
    return base_weight * day_weight
```

Day 3 signals get the most weight because they're past the initial calibration noise and before the fatigue effect. First-day signals are discounted because users are still calibrating — the first morning coffee shop they accepted was chosen with less information than the fourth.

---

## 3. Training Signal Quality Heuristics

### 3.1 Minimum Session Quality Gate

Before any session's behavioral signals enter the training pipeline, apply a quality gate. Sessions below threshold are excluded entirely — not weighted down, excluded. Noisy training data is worse than no training data.

```python
def session_passes_quality_gate(session: TripSession) -> bool:
    # Minimum signals: at least 5 meaningful interactions
    if session.total_signals < 5:
        return False
    
    # Minimum session duration: at least 30 minutes of active use
    if session.active_duration_minutes < 30:
        return False
    
    # Not a bot/testing account
    if session.user.system_role in ('admin', 'test'):
        return False
    
    # Not flagged for coordinated behavior
    if session.user_id in get_flagged_accounts():
        return False
    
    # Minimum diversity: at least 2 different signal types
    signal_types = set(s.signal_type for s in session.signals)
    if len(signal_types) < 2:
        return False
    
    return True
```

---

### 3.2 Recency Weighting in Training Batches

When the weekly retrain job assembles training examples, apply recency weighting. Behavioral signals from the past 2 weeks should have higher weight than signals from 3 months ago, because user preferences drift and the current persona state is what we're trying to capture.

```python
def compute_training_example_weight(signal_date: date, reference_date: date) -> float:
    age_days = (reference_date - signal_date).days
    
    # Exponential decay with 60-day half-life
    # At 60 days: weight = 0.5
    # At 120 days: weight = 0.25
    # At 180 days: weight = 0.125
    return 0.5 ** (age_days / 60)
```

Use this weight in the loss function during model training, not as a sampling weight. You want the model to see the older examples (they contain signal about less-common preferences) but discount their influence on the final weights.

---

### 3.3 Cold-User Signal Quarantine

Behavioral signals from a user's first trip (fewer than 3 completed trips) should be flagged as `cold_user_signal` and held out of ranking model training. Include them in persona dimension training only.

The reasoning: a cold user's signals reflect their initial calibration, which is heavily influenced by the LLM ranker's suggestions. You're measuring their reaction to the system's first guess, not their stable preference. These signals are useful for learning what the onboarding persona seed gets right and wrong, but shouldn't train the ranking model on circular logic.

```sql
-- Training data extraction: add warm_user flag
SELECT 
    s.*,
    CASE WHEN trip_count.count >= 3 THEN true ELSE false END as is_warm_user
FROM behavioral_signals s
JOIN (
    SELECT user_id, COUNT(DISTINCT id) as count 
    FROM trips 
    WHERE status = 'completed'
    GROUP BY user_id
) trip_count ON trip_count.user_id = s.user_id
```

Ranking model training: `WHERE is_warm_user = true`
Persona dimension training: all users

---

*Overplanned Internal · February 2026*
*These heuristics require schema additions noted inline. Priority for implementation: 2.1 (no-show disambiguation) → 1.2 (velocity) → 2.3 (dwell calibration) → rest.*
