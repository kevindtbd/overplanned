# Overplanned â€” Product Features & ML Gaps Deep Dive
*Offline Mode Â· Notifications Â· Packing Â· Calendar Â· ML Versioning Â· Training Pipeline Â· Eval*

---

# 1. Offline Mode & Smart Prefetch

## The Problem Restated

"I have no service and I want something new. Let me swipe through some cached ideas that sound like my vibe or something fun in the area."

The constraint: don't over-fetch. In populated tourist areas you'd burn through LLM budget fast if you pre-generate narratives for everything within 2km. The system needs to be surgically precise about what it fetches before signal drops.

The insight: **the LLM is expensive. The ActivityNode structured data is cheap. Keep them separate.**

---

## What Costs Money vs. What Doesn't

```
Expensive (LLM-generated, per-activity):
  - Narrative slot text ("locals-only counter Â· gets loud after 9")
  - Persona-fitted "why this" explanation
  - Divergence notes ("this is slower-paced than your usual picks")

Free (pre-computed, deterministic):
  - activity name, category, geo, tourist_score
  - source attribution string ("via Tabelog, 847 local reviews")
  - vibe_embedding vector (already stored in ActivityNode)
  - photo URL (Unsplash CDN, not our cost)
  - crowd_model (time of day + day of week lookup)
  - cost_estimate, typical_duration_min
  - requires_booking boolean
```

**The offline swipe deck is built entirely from the free tier.** No LLM calls at prefetch time. The narrative generates only when the user acts on something â€” imports to their trip, saves it, or asks "why this?" Online LLM call at that moment is fine because it's user-initiated and valuable.

---

## The Prefetch Budget

### When to prefetch

Prefetch happens at a specific trigger: **the moment a trip becomes active** (trip status flips to `active`, date_start = today). The user is about to go offline-capable. This happens while they're likely still on hotel WiFi.

Not at trip creation â€” that's days or weeks earlier and the data will be stale. Not continuously in the background â€” that's battery and data drain. Exactly once per trip activation, plus a lightweight nightly refresh for the current day.

### What to prefetch

**Always prefetch (free data, minimal storage):**
- Full structured `ActivityNode` records for everything already in the itinerary
- Pre-cached fallback graph (2 adjacent alts + 1 polar opposite + 1 indoor per slot) â€” already computed at trip generation, just needs to be synced to device
- Photos for all itinerary slots + fallbacks (lazy-load via CDN, cache on device)

**Conditionally prefetch (the expensive/heavy part):**

This is where the cost control lives. Don't fetch everything in a radius. Instead:

```
prefetch_budget = {
  activity_nodes: 40,        // max ActivityNode records to prefetch
  llm_narratives: 0,         // zero at prefetch time â€” generate on demand
  photos: 40,                // matches activity_nodes count
  geo_radius_km: 1.5,        // tight radius â€” walkable distance only
}
```

The 40-activity limit and 1.5km radius are deliberate. In a dense city like Tokyo or Bangkok, 1.5km still gives you dozens of options. In a rural area, you might only get 8 â€” which is fine, that's the honest reality of where you are. Don't fake abundance.

**Selection criteria for the 40 prefetch slots:**

Not the 40 closest. Not the 40 highest-rated. Ranked by:

```python
def prefetch_score(activity, user_profile, current_time):
    persona_match  = dot_product(activity.vibe_embedding, user_profile.preference_vector)
    proximity      = 1.0 / (1.0 + distance_km(activity.geo, user_location))
    time_fit       = crowd_model_score(activity, current_time)  # not crowded right now
    novelty        = 1.0 - recently_seen_penalty(activity, user_profile)
    
    return (
        persona_match * 0.45 +   # heaviest weight â€” fit matters most
        proximity     * 0.25 +   # walkable
        time_fit      * 0.20 +   # open and not slammed right now
        novelty       * 0.10     # haven't already seen this in their itinerary
    )
```

This scoring runs **entirely server-side against the vector DB and ActivityNode store** â€” no LLM involved. Fast, cheap, deterministic. Returns 40 ranked records. Client stores them in SQLite.

**One exception â€” narratives for itinerary slots only:**

Pre-generate LLM narratives for the activities already in the user's confirmed itinerary (not the fallbacks, not the prefetch pool). At ~150 tokens per slot, 10 slots per day, 7 days = ~10,500 tokens total. At Claude Haiku pricing that's under $0.01 per trip activation. Worth it for the confirmed itinerary.

Everything else â€” fallbacks, the swipe deck, alternatives â€” is structured data only until the user interacts.

---

## The Offline Swipe Deck â€” UX

This is a distinct surface, not a modified version of the itinerary view.

**Entry point:** A persistent button in the bottom of the active trip view: "Explore nearby â†’" It's always there, always accessible, and works identically online and offline. Online: fetches fresh. Offline: serves from cache. The experience is identical either way â€” the user never sees a "you're offline" state for this feature.

**The card:**

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ [full-bleed photo]                   â”‚
â”‚                                      â”‚
â”‚ Nishiki Market                       â”‚
â”‚ Market Â· 12 min walk                 â”‚
â”‚                                      â”‚
â”‚ â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘â–‘  â”‚ â† local/tourist bar (no label)
â”‚                                      â”‚
â”‚ via Tabelog Â· 847 local reviews      â”‚
â”‚ Usually busy now Â· closes at 6pm     â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

No LLM narrative on this card. The source attribution line + crowd model + category + walk time is enough to make a decision. The "why this fits you" language only appears if they tap in for more detail â€” which triggers an online LLM call if available, or shows a "we'll load the full details when you're back online" state if not.

**Swipe gestures:**
- Swipe right â†’ "interested" (queued to proposal pile, syncs when online)
- Swipe left â†’ "not for me" (negative signal, syncs when online)
- Tap â†’ detail view (online: full narrative; offline: structured data only)
- Long press â†’ "add to today" (slot import, syncs when online)

Both left and right swipes are behavioral signals that feed Pipeline A when connectivity returns. The swipe deck is a signal harvester, not just a browsing surface.

**Deck ordering offline:**

The 40 prefetched records are already ranked by `prefetch_score`. On the device, they're re-sorted by:
- `time_fit` refreshed against the current clock (crowd model is a lookup table, no network needed)
- Filter: `requires_booking = false` floated to top when offline (can't book anyway)
- Already-seen cards in this session moved to back

---

## Local Storage Architecture

```
SQLite tables on device (via Expo SQLite or react-native-sqlite-storage):

prefetched_activities (
  activity_id       TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  category_tags     TEXT,          -- JSON array
  geo_lat           REAL,
  geo_lng           REAL,
  photo_url         TEXT,
  tourist_score     REAL,
  source_attribution TEXT,
  crowd_model       TEXT,          -- JSON: { hour: score } lookup
  typical_duration_min INTEGER,
  cost_estimate_usd REAL,
  requires_booking  INTEGER,       -- boolean
  prefetch_score    REAL,
  prefetched_at     TEXT           -- ISO timestamp
)

offline_actions (
  id                TEXT PRIMARY KEY,  -- client-generated UUID
  action_type       TEXT NOT NULL,     -- swipe_right | swipe_left | add_to_trip
  activity_id       TEXT NOT NULL,
  occurred_at       TEXT NOT NULL,
  synced            INTEGER DEFAULT 0  -- boolean
)

cached_narratives (
  activity_id       TEXT PRIMARY KEY,
  narrative_text    TEXT NOT NULL,
  generated_at      TEXT,
  model_version     TEXT
)
-- Only itinerary slots have narratives cached. Prefetch pool does not.
```

**Storage budget per trip activation:**
- 40 `ActivityNode` records as JSON: ~40KB
- 40 photos (cached by CDN/image library): ~4MB on device if pre-fetched, otherwise on-demand
- Itinerary slot narratives (confirmed slots only): ~20KB
- Fallback graph (pre-cached alts): ~15KB
- Total structured data: ~75KB â€” negligible

Photos are the only meaningful storage cost. Don't pre-download photos for the swipe deck. Cache them as the user swipes. A 1.5km radius swipe session will naturally load photos sequentially; most won't be seen.

---

## Sync When Online Returns

When connectivity restores:

```python
def sync_offline_actions(user_id, device_id):
    unsyced = get_unsynced_offline_actions(device_id)
    
    for action in unsynced:
        if action.type == 'swipe_right':
            add_to_proposal_pile(user_id, action.activity_id, source='offline_swipe')
            log_behavioral_signal(user_id, 'card_interest', action.activity_id, 
                                  occurred_at=action.occurred_at)
        
        elif action.type == 'swipe_left':
            log_behavioral_signal(user_id, 'card_dismissed', action.activity_id,
                                  occurred_at=action.occurred_at)
        
        elif action.type == 'add_to_trip':
            # Import the activity into their itinerary â€” triggers re-hydration
            process_import(user_id, action.activity_id, action.trip_id)
    
    mark_synced(unsynced)
    
    # Refresh the prefetch pool if > 4 hours since last prefetch
    if should_refresh_prefetch(user_id):
        trigger_prefetch_job(user_id)
```

All offline actions carry their original `occurred_at` timestamp. The behavioral signal store preserves temporal ordering even for synced events â€” this matters for training data integrity.

---

## Nightly Refresh (Lightweight)

Each night at ~2am local time (when the user is presumably asleep), a background task runs:

```
Nightly prefetch refresh:
  1. Re-score the existing 40 prefetched activities against current crowd_model
     â†’ bump activities that will be less crowded tomorrow to top
     â†’ no new network calls if crowd_model is a local lookup table
  
  2. If device has WiFi:
     â†’ Check for newly added ActivityNodes in the city (Pipeline C may have added some)
     â†’ Fetch top-5 new additions that score well against persona
     â†’ Replace bottom-5 from current pool
     â†’ Total new data: ~5KB
  
  3. Update photo cache: preload photos for top-10 in ranked pool
```

This keeps the deck fresh without burning battery or data. WiFi-only for new data fetches. The crowd_model re-scoring is entirely local.

---

## Cost Model for Offline Feature

```
Per trip activation:
  Vector DB query (prefetch scoring)    : ~$0.001
  LLM narratives for confirmed slots    : ~$0.008  (Haiku, 10 slots)
  Photo CDN bandwidth                   : ~$0.002
  Total per trip activation             : ~$0.011

Per swipe deck session (online, on-demand narrative):
  LLM call only if user taps for detail : ~$0.0008 per tap
  Expected taps per session             : 2-3
  Total per online session              : ~$0.002

Per nightly refresh:
  5 new ActivityNode fetches            : negligible
  No LLM calls                         : $0
  Total                                 : ~$0.001

LLM cost per active trip per day       : ~$0.003
LLM cost per active trip total         : ~$0.020

At 500 users, assuming 30% have an active trip on any given day:
  150 active trips Ã— $0.003/day        = $0.45/day = ~$14/mo in LLM for offline
```

Extremely manageable. The zero-LLM prefetch design is what makes this cheap.

---

---

# 2. Notifications System

## What Needs to Exist

Four notification surfaces: push (mobile), in-app (notification center), email, and ambient (UI state, no notification).

### Pre-Trip Notifications

**3 days before trip starts:**
Push: "Kyoto in 3 days â€” your itinerary is ready. Any last adjustments?"
â†’ Opens itinerary day view

**Day before:**
Push: "Tomorrow's the day. Check the weather and make sure everything's confirmed."
â†’ Opens trip overview with weather snapshot updated

**Morning of each trip day:**
Push: "[Day 3 in Kyoto] â€” Fushimi Inari first, before the crowds hit. Starts at 8am."
â†’ Opens that day's slot view
â†’ This is the highest-value daily notification â€” it's the "alarm that helps you travel better"

### Mid-Trip Notifications

**System-initiated pivot** (when user is NOT in app):
Push: "Heads up â€” Nishiki Market closes early today. We swapped in an alternative."
â†’ Opens the pivot drawer for that slot

**Poll waiting** (group trip):
Push: "Alex and Jordan voted on tonight's dinner. Your turn."
â†’ Opens the poll

**Check-in reminder** (optional, user-controlled):
Push: "At Ichiran Ramen? Check in to log it."
â†’ Triggers check-in flow
â†’ Default: OFF. Opt-in only â€” this can feel invasive.

### Post-Trip Notifications

**24 hours after trip ends:**
Push: "You're back. How was it? Tell us the one thing that surprised you."
â†’ Opens post-trip rating flow (not a star rating â€” a single open-ended prompt)

**7 days after trip ends:**
Email: "Your Kyoto trip, saved. Here's the full itinerary you can share or revisit."
â†’ Links to the shared trip view (auto-created, private by default)

### Notification Data Model

```sql
CREATE TABLE notification_preferences (
    user_id             UUID PRIMARY KEY REFERENCES users(id),
    push_enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Pre-trip
    pre_trip_reminder   BOOLEAN NOT NULL DEFAULT TRUE,
    pre_trip_days_before INT NOT NULL DEFAULT 3,
    morning_briefing    BOOLEAN NOT NULL DEFAULT TRUE,  -- daily trip morning push
    
    -- Mid-trip
    pivot_alerts        BOOLEAN NOT NULL DEFAULT TRUE,
    group_poll_nudge    BOOLEAN NOT NULL DEFAULT TRUE,
    checkin_reminder    BOOLEAN NOT NULL DEFAULT FALSE, -- opt-in only
    
    -- Post-trip
    post_trip_rating    BOOLEAN NOT NULL DEFAULT TRUE,
    post_trip_summary_email BOOLEAN NOT NULL DEFAULT TRUE,
    
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE push_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       VARCHAR(512) NOT NULL UNIQUE,
    platform    VARCHAR(10) NOT NULL CHECK (platform IN ('ios', 'android')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_push_tokens_user ON push_tokens(user_id) WHERE is_active = TRUE;
```

### Notification Queue

```sql
CREATE TABLE notification_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    channel         VARCHAR(10) NOT NULL CHECK (channel IN ('push', 'email', 'in_app')),
    notification_type VARCHAR(40) NOT NULL,
    payload         JSONB NOT NULL,        -- channel-specific content
    scheduled_at    TIMESTAMPTZ NOT NULL,  -- when to send
    sent_at         TIMESTAMPTZ,
    failed_at       TIMESTAMPTZ,
    retry_count     INT NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    -- pending | sent | failed | cancelled
);

CREATE INDEX idx_notif_queue_pending ON notification_queue(scheduled_at)
    WHERE status = 'pending';
```

A background job polls `notification_queue` for `scheduled_at <= NOW() AND status = 'pending'`, processes in batches of 50, marks sent or failed.

### Stack Recommendation

- **Push**: Expo Push Notifications (if React Native Expo) â€” handles both FCM and APNs via a single API. Free. If bare React Native: direct FCM + APNs integration.
- **Email**: Resend. Modern API, excellent deliverability, React Email for templates. $0 for first 3,000/month.
- **In-app notification center**: a `notifications` table + unread count badge. Not a separate service.

### The Morning Briefing â€” Design

This is the highest-value notification in the product. It deserves specific design:

```
Push notification:
  Title: "Day 4 in Kyoto"
  Body:  "Arashiyama Bamboo Grove at 7am â€” you beat the crowds. 
          Weather's clear. Light day, you'll have energy for tonight."

Tap â†’ opens today's slot view, already expanded to first slot
```

The body copy is LLM-generated nightly for each active trip day, using:
- Next day's slot list
- Weather forecast
- Crowd model for first slot (time of day)
- Energy curve for that day of trip
- User's persona (tone calibration)

Cost: ~200 tokens per user per active trip day. At Haiku pricing: ~$0.0002 per notification. For 150 active trips: $0.03/day. Completely negligible.

Generate nightly at 11pm local user time. Cache the generated copy in `notification_queue.payload`. Send at 7am local time (or user-configured hour).

---

---

# 3. Packing List

## The Feature

`TripNode.packing_list` exists in the schema but nothing generates it or displays it.

This is genuinely useful and almost free to build on top of the existing pipeline. The LLM already has everything it needs at trip generation time: destination, dates, activity slot types, weather forecast, trip length.

## Generation Prompt Architecture

```python
def generate_packing_list(trip_id):
    trip = get_trip(trip_id)
    weather = get_weather_forecast(trip.destination, trip.date_start, trip.date_end)
    activity_categories = extract_categories_from_slots(trip.itinerary_slots)
    
    prompt = f"""
    Generate a packing list for this trip. Output JSON only.
    
    Destination: {trip.destination}
    Duration: {trip.trip_length_days} days
    Dates: {trip.date_start} to {trip.date_end}
    Weather: {weather.summary}  // "warm, humid, chance of afternoon rain"
    Activities: {activity_categories}  // ["hiking", "fine_dining", "beach", "temple_visits"]
    Group size: {trip.group_size}
    Mode: {trip.mode}  // solo | couple | group
    
    Return a JSON object with these categories:
    - documents (passport, visa, travel insurance)
    - clothing (specific to weather + activities)
    - footwear
    - electronics
    - toiletries (essentials only, no generic list)
    - activity_specific (gear for the specific activities in this trip)
    - medications (generic â€” no prescription recommendations)
    
    Rules:
    - Be specific. "Rain jacket" not "jacket". "Reef-safe sunscreen" not "sunscreen".
    - Activity-specific items only appear if those activities are in the itinerary.
    - Don't include items everyone already knows to pack (underwear, toothbrush).
    - Flag items as "essential" or "optional".
    """
    
    # One LLM call per trip, at generation time
    # Cost: ~400 tokens. Negligible.
    return llm_call(prompt, output_format='json')
```

## Data Model Addition

```sql
-- Add to trips table
ALTER TABLE trips ADD COLUMN packing_list JSONB DEFAULT NULL;

-- Separate table for per-item check state (checked off during packing)
CREATE TABLE packing_list_items (
    trip_id     UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    category    VARCHAR(40) NOT NULL,
    item        VARCHAR(255) NOT NULL,
    essential   BOOLEAN NOT NULL DEFAULT TRUE,
    checked     BOOLEAN NOT NULL DEFAULT FALSE,
    checked_at  TIMESTAMPTZ,
    PRIMARY KEY (trip_id, category, item)
);
```

## UX

A separate tab in the pre-trip view. Not buried in settings. Not in the itinerary. Its own place in the navigation hierarchy because users interact with it at a different time (packing the night before, not while planning slots).

- Grouped by category, collapsible
- Each item has a checkbox â€” check state persists
- "Add item" inline per category â€” free text, no LLM needed
- Delete any item â€” nothing is sacred
- Regenerate button (if itinerary changes significantly â€” adds a hiking day, removes beach)

**Regeneration cost control**: Packing list regenerates on explicit user request only, not automatically on every slot change. One LLM call per trip is the budget.

---

---

# 4. Calendar Integration

## What to Build

Two directions: export and import. Export is trivial and high value. Import is harder but eliminates a significant friction point.

### Export â€” `.ics` File

Generate a standard iCalendar file from the itinerary. Every calendar app on every platform reads `.ics`. No API keys, no OAuth, no partner integration required.

```python
def generate_ics(trip_id):
    trip = get_trip(trip_id)
    
    cal = Calendar()
    cal.add('prodid', '-//Overplanned//Travel Itinerary//EN')
    cal.add('version', '2.0')
    
    for slot in trip.itinerary_slots:
        event = Event()
        event.add('summary', slot.activity.name)
        event.add('dtstart', datetime(trip.date_start + slot.time_window.start))
        event.add('dtend', datetime(trip.date_start + slot.time_window.end))
        event.add('location', slot.activity.address)
        event.add('description', slot.overplanned_narrative or slot.activity.name)
        event.add('uid', f"{slot.id}@overplanned.app")
        cal.add_component(event)
    
    return cal.to_ical()

# API endpoint
GET /api/v1/trips/:trip_id/export.ics
â†’ Returns text/calendar
â†’ Browser downloads and opens in default calendar app
```

This is an afternoon of work. Ships in v1.

**Two export modes:**
- Full trip â†’ one `.ics` with all slots across all days
- Single day â†’ one `.ics` for today's slots (useful mid-trip, send to phone)

### Import â€” Reading Existing Calendar

The high-value case: user has flight info, hotel reservations, and existing commitments in their calendar. They're doing trip constraints data entry that Overplanned could read automatically.

**What to read:**
- Flights (detect by airline keywords + airport codes in event titles)
- Hotel check-in/check-out
- Existing hard commitments ("work call", "conference") that create blocked slots

**Approach â€” don't build this from scratch:**
- iOS: EventKit API (React Native has a package for this â€” `react-native-calendar-events`)
- Android: Calendar Provider
- Request read-only calendar permission â€” no write access at import time

**What to do with imported events:**

```python
def process_calendar_import(calendar_events, trip_id):
    for event in calendar_events:
        classification = classify_calendar_event(event)
        
        if classification == 'flight':
            constraint = extract_flight_constraint(event)
            # Add to trip.constraints: departure terminal, arrival time
            add_hard_constraint(trip_id, constraint)
        
        elif classification == 'hotel':
            constraint = extract_hotel_constraint(event)
            # Add check-in/check-out times as hard constraints
            add_hard_constraint(trip_id, constraint)
        
        elif classification == 'blocked':
            # Create a locked 'break' slot covering the event time
            add_locked_slot(trip_id, event.start, event.end, type='blocked',
                           notes=event.title)
```

`classify_calendar_event` is a lightweight classifier â€” keyword matching + time patterns, not a full LLM call. "Flight to NRT" + airport code regex = flight. "Check-in at APA Hotel" = hotel. "Q3 earnings call" = blocked.

Only run the LLM if the classifier is uncertain (low confidence score). The LLM call for calendar event classification is a fallback, not the default path.

---

---

# 5. ML Gaps

## 5.1 â€” Model Registry & Versioning

Every recommendation event needs to log which model version produced it. Currently nothing does this.

```sql
CREATE TABLE model_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      VARCHAR(50) NOT NULL,
    -- ranking_model | persona_dimension_tagger | vibe_embedding |
    -- pivot_acceptance_model | source_authority_scorer | mood_classifier
    
    version         VARCHAR(20) NOT NULL,  -- semver: "1.0.0", "1.1.0"
    artifact_path   TEXT NOT NULL,         -- S3: s3://overplanned-models/ranking/v1.0.0/
    training_date   DATE NOT NULL,
    training_data_window VARCHAR(40),      -- "2026-01-01 to 2026-02-01"
    
    metrics         JSONB NOT NULL DEFAULT '{}',
    -- ranking_model:        { "ndcg@10": 0.72, "mrr": 0.68, "coverage": 0.91 }
    -- pivot_acceptance:     { "auc": 0.81, "precision@3": 0.74 }
    -- persona_tagger:       { "label_accuracy": 0.87, "dimension_mae": 0.09 }
    
    status          VARCHAR(20) NOT NULL DEFAULT 'staging',
    -- staging | a_b_test | production | archived
    
    promoted_at     TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,
    promoted_by     UUID REFERENCES users(id),  -- internal admin user
    
    notes           TEXT  -- human-readable deployment notes
);

CREATE UNIQUE INDEX idx_model_registry_prod ON model_registry(model_name)
    WHERE status = 'production';
-- Enforces: exactly one production model per model_name at any time
```

Every recommendation response includes `X-Model-Version: ranking/v1.2.0` in the response header. Logged in the behavioral signal for that recommendation. Allows per-version performance attribution.

---

## 5.2 â€” Training Data Pipeline

Signals accumulate in `behavioral_signals` but no extraction pipeline moves them to training-ready format. This is the gap between "we have data" and "we can train."

### Extraction Job Structure

Runs nightly as a background job. Reads `behavioral_signals` for the previous day, transforms into typed training examples, writes to S3 as Parquet.

```python
def extract_training_data(date: date):
    """
    Nightly job. Runs at 3am UTC. Takes ~5-10 min at Tier 1 scale.
    """
    
    # --- Ranking Model Training Examples ---
    # Positive: recommendation that was accepted (slot_accepted, card_interest)
    # Negative: same session, same user, same trip â€” activities that were skipped
    
    ranking_examples = query("""
        SELECT 
            s.user_id,
            s.payload->>'activity_id' as activity_id,
            s.payload->>'model_version' as model_version,
            CASE WHEN s.signal_type = 'card_viewed_then_accepted' THEN 1
                 WHEN s.signal_type = 'card_skipped' THEN 0
                 ELSE NULL END as label,
            p.value as persona_pace,
            p2.value as persona_budget,
            -- ... other persona dimensions
            a.tourist_score,
            a.quality_score,
            -- ... other activity features
            s.occurred_at
        FROM behavioral_signals s
        JOIN persona_dimensions p ON p.user_id = s.user_id AND p.dimension = 'pace_preference'
        JOIN persona_dimensions p2 ON p2.user_id = s.user_id AND p2.dimension = 'budget_sensitivity'
        JOIN activity_nodes a ON a.id = (s.payload->>'activity_id')::uuid
        WHERE s.occurred_at >= %(date_start)s
          AND s.occurred_at < %(date_end)s
          AND s.signal_type IN ('card_viewed_then_accepted', 'card_skipped',
                                 'pivot_accepted', 'pivot_dismissed')
          AND s.user_id NOT IN (SELECT user_id FROM flagged_accounts)  -- exclude commercial
    """, date_start=date, date_end=date + timedelta(days=1))
    
    write_parquet(ranking_examples, f"s3://overplanned-training/ranking/{date}/examples.parquet")
    
    # --- Persona Dimension Training Examples ---
    # Each behavioral signal = one training example for the dimension update model
    
    persona_examples = query("""
        SELECT
            s.user_id,
            s.signal_type as action_type,
            s.payload->>'activity_category' as category,
            s.payload->>'energy_delta' as energy_delta,
            s.payload->>'time_of_day' as time_of_day,
            s.payload->>'day_number' as trip_day,
            s.payload->>'group_context' as group_context,
            -- Target: actual dimension delta that occurred after this signal
            pd_after.value - pd_before.value as actual_delta,
            pd_before.dimension as dimension
        FROM behavioral_signals s
        ...
    """)
    
    write_parquet(persona_examples, f"s3://overplanned-training/persona/{date}/examples.parquet")
    
    # --- Pivot Acceptance Training Examples ---
    pivot_examples = query("""
        SELECT * FROM behavioral_signals
        WHERE signal_type IN ('pivot_accepted', 'pivot_dismissed', 'pivot_ignored')
          AND occurred_at >= %(date_start)s
    """, ...)
    
    write_parquet(pivot_examples, f"s3://overplanned-training/pivot/{date}/examples.parquet")
```

### S3 Training Data Layout

```
s3://overplanned-training/
  ranking/
    2026-02-01/examples.parquet
    2026-02-02/examples.parquet
    ...
    manifest.json      â† which dates are available, row counts
  persona/
    2026-02-01/examples.parquet
    ...
  pivot/
    2026-02-01/examples.parquet
    ...
  embeddings/
    user_vectors/      â† periodic snapshot of preference_vectors table
    activity_vectors/  â† periodic snapshot from Qdrant
```

### Retrain Cadence

| Model | Retrain | Minimum data | Trigger |
|---|---|---|---|
| Persona dimension tagger | Weekly | 500 new signals | Cron |
| Ranking model | Weekly | 200 new positive examples | Cron |
| Pivot acceptance model | Weekly | 100 new pivot events | Cron |
| Vibe embedding / two-tower | Monthly | 1,000 new positive pairs | Manual + cron |
| Source authority scorer | Monthly | Significant new Pipeline C data | Manual |

At Tier 1 scale (< 500 users), you may not hit minimum data thresholds weekly. The job should check row count before attempting retrain and skip with a log message if below threshold. Better to skip than to overfit on tiny data.

---

## 5.3 â€” Offline Evaluation Framework

Before any model goes to production, it runs through eval. No human judgment required â€” automated metrics gate promotion.

```python
def evaluate_model(model_name: str, version: str, holdout_date_range: tuple) -> dict:
    """
    Runs before promoting a model from 'staging' to 'production'.
    Uses held-out behavioral signals (10% of data never used in training).
    """
    
    holdout_examples = load_parquet(
        f"s3://overplanned-training/{model_name}/holdout/{holdout_date_range}/examples.parquet"
    )
    
    model = load_model(model_name, version)
    
    if model_name == 'ranking_model':
        predictions = model.predict(holdout_examples.features)
        return {
            'ndcg@10': compute_ndcg(predictions, holdout_examples.labels, k=10),
            'mrr': compute_mrr(predictions, holdout_examples.labels),
            'coverage': compute_coverage(predictions),  # % of catalog reachable
            'vs_baseline': compare_to_baseline(predictions, holdout_examples)
        }
    
    elif model_name == 'pivot_acceptance_model':
        return {
            'auc': compute_auc(predictions, holdout_examples.labels),
            'precision@3': compute_precision_at_k(predictions, holdout_examples.labels, k=3),
            'vs_baseline': compare_to_most_popular_pivot(holdout_examples)
        }

PROMOTION_THRESHOLDS = {
    'ranking_model': {
        'ndcg@10': 0.65,       # must beat this to promote
        'vs_baseline': 0.05    # must be at least 5% better than "most popular in city"
    },
    'pivot_acceptance_model': {
        'auc': 0.75,
        'vs_baseline': 0.08
    }
}

def should_promote(model_name, metrics) -> bool:
    thresholds = PROMOTION_THRESHOLDS[model_name]
    return all(metrics[k] >= v for k, v in thresholds.items())
```

If `should_promote` returns False, model stays in `staging`. Human reviews the metrics and decides whether to investigate the training data, adjust the model, or accept lower performance. Nothing auto-promotes past human review at Tier 1 â€” the stakes are low enough that a weekly 5-minute review is fine.

---

## 5.4 â€” A/B Testing Framework (Lightweight)

Not a full feature experimentation platform â€” that's overkill for Tier 1. A simple model A/B test: route X% of users to model version A, Y% to version B, compare downstream behavioral outcomes.

```sql
CREATE TABLE ab_experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    model_name      VARCHAR(50) NOT NULL,
    control_version VARCHAR(20) NOT NULL,    -- typically current production
    treatment_version VARCHAR(20) NOT NULL,
    traffic_split   FLOAT NOT NULL DEFAULT 0.10,  -- 10% to treatment
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    winner          VARCHAR(20)   -- 'control' | 'treatment' | null (inconclusive)
);

CREATE TABLE ab_assignments (
    user_id         UUID NOT NULL REFERENCES users(id),
    experiment_id   UUID NOT NULL REFERENCES ab_experiments(id),
    variant         VARCHAR(20) NOT NULL,  -- 'control' | 'treatment'
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, experiment_id)
);
```

Assignment is sticky â€” same user always gets the same variant. Assigned on first exposure, stored in `ab_assignments`. Never re-assigned mid-experiment.

---

## 5.5 â€” The Gap Nobody Talks About: Persona Decay Validation

The architecture defines a decay function for persona dimensions but never validates that it actually works. A dimension that never decays loses meaning over time ("I hiked once 3 years ago, am I still hiking boy?"). A dimension that decays too fast requires more signals than real users generate.

**What needs to exist:**

A validation job that runs monthly:
1. Sample users who haven't had a trip in 60+ days
2. Check: have their persona dimension confidence scores decayed appropriately?
3. When those users create a new trip, do their fresh behavioral signals diverge significantly from their decayed scores? If yes, decay was too slow.
4. Log divergence metrics per dimension

This isn't training data â€” it's a health check on the deterministic state machine. If pace_preference decays too slowly for long-inactive users, adjust the decay constant. No ML involved â€” just parameter tuning.

```python
def validate_decay_health():
    """Monthly job. 30 min runtime. No ML inference."""
    
    stale_users = query("""
        SELECT user_id FROM users 
        WHERE last_active_at < NOW() - INTERVAL '60 days'
          AND last_active_at > NOW() - INTERVAL '180 days'
    """)
    
    for user_id in stale_users:
        dims = get_persona_dimensions(user_id)
        avg_confidence = mean([d.confidence for d in dims])
        
        # Flag if high confidence despite 60+ days of inactivity
        if avg_confidence > 0.6:
            log_decay_health_issue(user_id, avg_confidence, days_inactive=...)
    
    # Report: what % of stale users still have high-confidence dimensions?
    # If > 20%, decay constants are too conservative
```

---

# Summary â€” Priority Order for This Doc

### Ship with v1
- Offline swipe deck (structured data only, no LLM at prefetch time)
- SQLite local cache + offline action queue + sync-on-reconnect
- Morning briefing push notification (LLM-generated nightly, negligible cost)
- Pre-trip reminder + post-trip rating push
- Push token table + notification preferences table
- Packing list generation (one LLM call per trip at generation time)
- `.ics` calendar export

### First month post-launch
- Nightly prefetch refresh (crowd model re-sort, WiFi-only new fetches)
- Notification queue table + background sender job
- Model registry table
- Training data extraction job â†’ S3 Parquet
- Offline evaluation framework (metrics, promotion gates)
- Post-trip email summary (Resend + React Email template)

### Tier 2 (500+ users)
- Calendar import (EventKit / Calendar Provider)
- A/B experiment framework
- Persona decay validation job
- Retraining automation (currently: manual trigger after eval passes)
- Pivot acceptance model (needs sufficient pivot event volume first)

---

*Last updated: February 2026*
*Cost-constrained offline design: zero LLM at prefetch time, ~$0.011 per trip activation*
*Depends on: ActivityNode schema (build list Â§1.3), behavioral_signals table (gaps doc Â§1.5)*
