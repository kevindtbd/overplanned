# Overplanned — Micro-Stops: Backend Architecture

*Created: February 2026*
*Status: Draft — not yet implemented*

---

## What This Is

Micro-stops are user-owned, lightweight location notes that live outside the itinerary spine. They are not recommendations, not scored, not system-generated. They are the "7-Eleven for bug spray", "pop into that ceramic shop", "find an ATM before the temple" moments that real travel involves but no travel app handles well.

The system's job is not to curate these — it's to surface them at the right moment and stay out of the way.

---

## Data Model

### New Table: `micro_stops`

```sql
CREATE TABLE micro_stops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id         UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Content
    name            VARCHAR(255) NOT NULL,           -- "7-Eleven bug spray"
    note            TEXT,                            -- optional freeform note
    category        VARCHAR(40),                     -- 'errand' | 'shop' | 'food' | 'atm' | 'other'
    
    -- Location (optional — can be vague)
    place_id        VARCHAR(255),                    -- Google/Mapbox place ID if resolved
    place_name      VARCHAR(255),                    -- resolved venue name
    lat             DECIMAL(10,8),
    lng             DECIMAL(11,8),
    area_hint       VARCHAR(255),                    -- "near Chatuchak", "Sukhumvit area"
    
    -- Timing (all optional — micro-stops are loose)
    day_number      INTEGER,                         -- which trip day, if known
    before_slot_id  UUID REFERENCES itinerary_slots(id) ON DELETE SET NULL,
    after_slot_id   UUID REFERENCES itinerary_slots(id) ON DELETE SET NULL,
    time_hint       VARCHAR(100),                    -- "before lunch", "afternoon"
    
    -- State
    status          VARCHAR(20) DEFAULT 'pending',   -- 'pending' | 'done' | 'skipped'
    completed_at    TIMESTAMPTZ,
    
    -- Proximity nudge config
    nudge_enabled   BOOLEAN DEFAULT TRUE,
    nudge_radius_m  INTEGER DEFAULT 300,             -- trigger nudge within 300m
    nudge_sent_at   TIMESTAMPTZ,                     -- prevent repeat nudges
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    source          VARCHAR(40) DEFAULT 'user',      -- 'user' | 'voice' | 'pivot_bar'
    
    CONSTRAINT valid_status CHECK (status IN ('pending','done','skipped')),
    CONSTRAINT valid_category CHECK (category IN ('errand','shop','food','atm','photo','other'))
);

-- Indexes
CREATE INDEX idx_micro_stops_trip ON micro_stops(trip_id);
CREATE INDEX idx_micro_stops_user ON micro_stops(user_id);
CREATE INDEX idx_micro_stops_day ON micro_stops(trip_id, day_number);
CREATE INDEX idx_micro_stops_location ON micro_stops USING GIST(
    ST_SetSRID(ST_MakePoint(lng, lat), 4326)
) WHERE lat IS NOT NULL;
CREATE INDEX idx_micro_stops_status ON micro_stops(trip_id, status);
```

### Relationship to Existing Schema

Micro-stops are intentionally **loosely coupled** to the itinerary. They reference slots optionally (`before_slot_id`, `after_slot_id`) but do not live in the `itinerary_slots` table. This separation is critical:

- Itinerary slots are system-managed, scored, sequenced
- Micro-stops are user-managed, unscored, loosely ordered
- Deleting a slot does not delete associated micro-stops (SET NULL, not CASCADE)
- Reordering slots does not reorder micro-stops

---

## API Endpoints

### Create
```
POST /api/v1/trips/:trip_id/micro-stops
Body: {
  name: string,
  note?: string,
  category?: string,
  area_hint?: string,
  day_number?: integer,
  before_slot_id?: uuid,
  nudge_enabled?: boolean
}
→ 201: { micro_stop }
```

### List for a trip day
```
GET /api/v1/trips/:trip_id/micro-stops?day=3
→ 200: { micro_stops: [...], pending_count: 4, done_count: 1 }
```

### Update (mark done, edit, add location)
```
PATCH /api/v1/trips/:trip_id/micro-stops/:stop_id
Body: { status?, note?, lat?, lng?, place_id? }
→ 200: { micro_stop }
```

### Delete
```
DELETE /api/v1/trips/:trip_id/micro-stops/:stop_id
→ 204
```

### Proximity check (called by background worker)
```
POST /api/v1/micro-stops/proximity-check
Body: { user_id, lat, lng, trip_id }
→ 200: { nudges: [{ stop_id, name, distance_m, message }] }
```

---

## Proximity Nudge System

### How It Works

A background worker polls user location (when app is active) or receives a geofence event (when backgrounded). When a user comes within `nudge_radius_m` of a pending micro-stop:

1. Check `nudge_sent_at` — don't re-nudge within 2 hours
2. Check `status` — only nudge `pending` stops
3. Check trip day — only nudge stops relevant to today
4. Fire push notification

### Nudge Message Format

Same tone as the rest of the system — specific, calm, one action:

```
"Bug spray — you're 2 min from the 7-Eleven you flagged."
[Get directions]  [Mark done]

"The ceramic shop is across this street."
[Open maps]  [Dismiss]
```

### Worker Architecture

```python
# Runs every 60s when user location is fresh (< 5 min old)
def check_proximity_nudges(user_id: str, lat: float, lng: float, trip_id: str):
    pending_stops = get_pending_micro_stops(trip_id, day=today())
    
    for stop in pending_stops:
        if stop.lat is None: continue
        if stop.nudge_enabled is False: continue
        if recently_nudged(stop): continue  # nudge_sent_at < 2h ago
        
        distance = haversine(lat, lng, stop.lat, stop.lng)
        
        if distance <= stop.nudge_radius_m:
            send_push_notification(
                user_id=user_id,
                title=stop.name,
                body=f"You're {round(distance)}m away — {stop.note or 'flagged stop'}",
                data={ 'stop_id': stop.id, 'action': 'micro_stop_nudge' }
            )
            update_nudge_sent_at(stop.id)
```

---

## Entry Points (UX)

Three ways a micro-stop gets created:

### 1. Map — "Add a stop here"
Tapping empty space on the map or tapping "Add nearby stop" in the slot popup. Opens a lightweight sheet: name field, optional note, category chip. No location search needed — coordinates captured from tap.

### 2. Day view — "+ Quick stop"
A dashed "+" affordance in the slot spine between any two slots. Lighter than a full slot add — no photo, no scoring, just a name and optional note. Visually distinct from itinerary slots (dashed border, errand icon).

### 3. Pivot bar — Natural language
"Remind me to grab bug spray near Chatuchak" → intent classifier routes to micro-stop creation, LLM extracts `{ name: "bug spray", area_hint: "Chatuchak", category: "errand" }`. No place resolution needed unless user wants it.

---

## Display in Day View

Micro-stops appear in the slot spine as a lighter visual layer:

```
────────────────────────────────
  14:00  [Photo] Kinkaku-ji         ← itinerary slot (solid)
                 "weekday · thins..."
────────────────────────────────
         [- -]  Bug spray — 7-Eleven  ← micro-stop (dashed)
                Near Kinkaku-ji · Errand
────────────────────────────────
  16:00  [Photo] Philosopher's Path  ← itinerary slot (solid)
────────────────────────────────
```

Visual treatment:
- Dashed left border instead of solid
- No photo thumbnail
- Category icon instead of source badge
- Checkbox affordance (tap to mark done)
- Dimmed when done, with strikethrough

---

## What the System Does NOT Do

- Does not score or rank micro-stops
- Does not suggest micro-stops (user-owned entirely)
- Does not reorder them automatically
- Does not block itinerary generation on them
- Does not surface them in the behavioral graph (they're tasks, not preferences)

The one exception: if a user repeatedly creates micro-stops of category `shop` or `errand` in a certain city, that signal *could* feed into the behavioral graph as a lightweight indicator. But this is a v2 concern — not in scope for initial build.

---

## Migration

No changes to existing tables. Net-new table only. Zero risk to existing itinerary data.

```sql
-- Run once
CREATE TABLE micro_stops ( ... );  -- see above
CREATE INDEX ...;

-- Seed categories enum for validation layer
INSERT INTO app_config (key, value) VALUES 
  ('micro_stop_categories', '["errand","shop","food","atm","photo","other"]');
```

---

## Open Questions

1. **Group trips** — do micro-stops belong to one person or the whole group? Probably the individual — they're personal errands. But visibility to group members could be useful ("SL flagged a ceramic shop on this block"). Decision pending.

2. **Offline** — micro-stops must be creatable offline. Queue writes locally, sync when back online. Standard offline-first pattern.

3. **Place resolution** — when a user types "7-Eleven near Chatuchak", do we resolve to a specific place or leave it vague? Suggest: resolve lazily — only if user taps "find it on map". Don't force resolution.

4. **Voice input** — "Hey Overplanned, remind me to grab sunscreen tomorrow morning" is a natural micro-stop creation pattern. Scope for v2 after pivot bar intent classifier is hardened.
