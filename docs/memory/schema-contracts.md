# Schema Contracts (All Confirmed)

## Design Rule: No Column Without a Data Source
If nothing writes to a column at launch, it doesn't exist at launch.
Prisma migrations are cheap — add columns when their data source ships.
Each track adds its own columns via its own migration.

## Three-Layer Signal Architecture (CONFIRMED)
- **BehavioralSignal** — structured actions, always true, app reads this
- **IntentionSignal** — inferred WHY behind actions, probabilistic, separate table
- **RawEvent** — append-only firehose, ML pipeline reads this
- **Actions vs intentions are NEVER mixed** — different tables, different write sources, different confidence
- **Promotion pipeline** — batch job (Month 5+) promotes implicit RawEvents → BehavioralSignals + IntentionSignals
- **Frontend contract**: emit every interaction as RawEvent. Over-log, never under-log. Backend decides importance.

## Shadow Training Strategy
Two-Tower (Month 9) needs:
- Positive pairs → BehavioralSignal (confirm, complete, loved)
- Explicit negatives → BehavioralSignal (skip, swipe_left, disliked)
- Implicit negatives → RawEvent impressions (shown but not tapped)
- Candidate sets → RawEvent (full ranked pool during generation)
- Position bias data → RawEvent (position in list when shown)
- Session sequences → RawEvent (sessionId grouping)
- Intent-annotated actions → IntentionSignal (skip + why)

Without implicit negatives + candidate sets, you train a popularity model, not personalization.

## BehavioralSignal (Pure Actions — Always True)
```prisma
model BehavioralSignal {
  id              String     @id @default(uuid())
  userId          String
  tripId          String?
  slotId          String?
  activityNodeId  String?
  signalType      SignalType
  signalValue     Float      // [-1.0, 1.0]
  tripPhase       TripPhase  // pre_trip | active | post_trip
  rawAction       String     // literal action for audit trail
  weatherContext  String?    // clear | rain | snow | extreme_heat | extreme_cold
  modelVersion    String?
  promptVersion   String?
  createdAt       DateTime   @default(now())
}

enum SignalType {
  // Slot interactions
  slot_view, slot_tap, slot_confirm, slot_skip, slot_swap,
  slot_complete, slot_dwell
  // Discovery
  discover_swipe_right, discover_swipe_left,
  discover_shortlist, discover_remove
  // Vibe
  vibe_select, vibe_deselect, vibe_implicit
  // Post-trip
  post_loved, post_skipped, post_missed, post_disliked
  // Pivot
  pivot_accepted, pivot_rejected, pivot_initiated
  // Passive
  dwell_time, scroll_depth, return_visit, share_action
  // Promoted implicit (written by batch pipeline, Month 5+)
  considered_not_chosen, soft_positive, category_preference,
  time_preference, geographic_preference, pace_signal
}
```

## IntentionSignal (Inferred WHY — Probabilistic)
```prisma
model IntentionSignal {
  id                  String   @id @default(uuid())
  behavioralSignalId  String
  rawEventId          String?
  userId              String
  intentionType       String   // "not_interested" | "bad_timing" | "too_far" | "already_visited" | "price_mismatch" | "vibe_mismatch" | "weather_dependent" | "group_conflict"
  confidence          Float    // [0-1]
  source              String   // "rule_heuristic" | "ml_model" | "user_explicit" | "post_trip_feedback"
  userProvided        Boolean  @default(false)
  createdAt           DateTime @default(now())
  @@index([behavioralSignalId])
  @@index([userId, intentionType])
}
```

Three write sources at launch:
1. Rule heuristics — skipped + raining + outdoor → "weather_dependent" (conf 0.7)
2. User explicit — post-trip feedback, flag sheet resolution (conf 1.0)
3. ML model (Month 5+) — promotion pipeline infers from patterns

## RawEvent (Shadow Training Firehose — Over-Log Everything)
```prisma
model RawEvent {
  id              String   @id @default(uuid())
  userId          String
  sessionId       String
  tripId          String?
  activityNodeId  String?  // extracted for queryability, nullable

  eventType       String
  intentClass     String   // "explicit" | "implicit" | "contextual"
  surface         String?  // "discover_feed" | "day_view" | "map_view" | "detail_card" | "search"

  payload         Json
  platform        String?  // "ios" | "android" | "web"
  screenWidth     Int?
  networkType     String?  // "wifi" | "cellular" | "offline"

  createdAt       DateTime @default(now())

  @@index([userId, eventType, createdAt])
  @@index([userId, activityNodeId])
  @@index([sessionId])
  @@index([createdAt])
  @@index([intentClass, eventType])
}
```

Index rule: if ML pipeline will WHERE on it → column. If it's a training feature → stays in payload JSON.
Retention: 90-day rolling Postgres, older → GCS Parquet for batch training.

Frontend must log: every navigation, every scroll, every tap, every viewport change,
every search/filter, every app foreground/background, every detail expand/collapse.

## Entity Resolution (the 7-Eleven Problem)
ActivityNode additions for dedup:
```prisma
// Added to ActivityNode model:
  foursquareId      String?   @unique
  googlePlaceId     String?   @unique
  canonicalName     String    // normalized: lowercase, stripped, canonical spelling
  resolvedToId      String?   // if duplicate, points to canonical node
  isCanonical       Boolean   @default(true)

model ActivityAlias {
  id              String       @id @default(uuid())
  activityNodeId  String
  alias           String
  source          String       // which scraper produced this name
  createdAt       DateTime     @default(now())
  @@index([alias])
  @@index([activityNodeId])
}
```

Resolution chain (strongest → weakest):
1. External place ID match (Foursquare, Google)
2. Geocode proximity (<50m) + same category
3. Normalized name similarity + city (trigram/Levenshtein)
4. Content hash (weakest — same content ≠ same entity)

Query contract: WHERE isCanonical = true. Duplicates invisible to app.
This is launch-day critical — scraping pipeline produces dupes immediately.

## Trip (Lean — group columns deferred to Track 4)
```prisma
model Trip {
  id              String     @id @default(uuid())
  userId          String
  mode            TripMode   // solo | group
  status          TripStatus // draft | planning | active | completed | archived
  destination     String
  city            String
  country         String
  startDate       DateTime
  endDate         DateTime
  groupId         String?
  memberCount     Int?
  planningProgress Float?
  presetTemplate  String?
  personaSeed     Json?      // onboarding answers, cold-start embedding seed
  createdAt       DateTime   @default(now())
  updatedAt       DateTime   @updatedAt
  activatedAt     DateTime?
  completedAt     DateTime?
}
```

Cut: fairnessState, affinityMatrix, logisticsState (all Track 4 group state).

## ItinerarySlot (Lean — pivot/group columns deferred)
```prisma
model ItinerarySlot {
  id              String     @id @default(uuid())
  tripId          String
  activityNodeId  String?
  dayNumber       Int
  sortOrder       Int
  slotType        SlotType   // anchor | flex | meal | break | transit
  status          SlotStatus // proposed | voted | confirmed | active | completed | skipped
  startTime       DateTime?
  endTime         DateTime?
  durationMinutes Int?
  isLocked        Boolean    @default(false)
  createdAt       DateTime   @default(now())
  updatedAt       DateTime   @updatedAt
}
```

Cut: voteState, isContested (Track 4), swappedFromId, pivotEventId, wasSwapped (Track 5),
bookingStatus, bookingRef (no booking integration at launch).

## ActivityNode (with entity resolution fields)
```prisma
model ActivityNode {
  id                String           @id @default(uuid())
  name              String
  slug              String           @unique
  canonicalName     String           // normalized for dedup
  city              String
  country           String
  neighborhood      String?
  latitude          Float
  longitude         Float
  category          ActivityCategory
  subcategory       String?
  priceLevel        Int?             // 1-4
  hours             Json?
  address           String?
  phoneNumber       String?
  websiteUrl        String?
  foursquareId      String?          @unique
  googlePlaceId     String?          @unique
  primaryImageUrl   String?
  imageSource       String?
  imageValidated    Boolean          @default(false)
  sourceCount       Int              @default(0)
  convergenceScore  Float?
  authorityScore    Float?
  descriptionShort  String?
  descriptionLong   String?
  contentHash       String?
  lastScrapedAt     DateTime?
  lastValidatedAt   DateTime?
  status            NodeStatus
  flagReason        String?
  resolvedToId      String?
  isCanonical       Boolean          @default(true)
  createdAt         DateTime         @default(now())
  updatedAt         DateTime         @updatedAt
}

enum ActivityCategory {
  dining, drinks, culture, outdoors, active, entertainment,
  shopping, experience, nightlife, group_activity, wellness
}
```

## ActivityNodeVibeTag (junction — per-source scores)
```prisma
model ActivityNodeVibeTag {
  id              String   @id @default(uuid())
  activityNodeId  String
  vibeTagId       String
  score           Float    // [0-1]
  source          String   // "llm_extraction" | "rule_inference" | "cross_reference"
  createdAt       DateTime @default(now())
  @@unique([activityNodeId, vibeTagId, source])
}
```

## QualitySignal (per-source, NEVER collapsed)
```prisma
model QualitySignal {
  id              String   @id @default(uuid())
  activityNodeId  String
  sourceName      String
  sourceUrl       String?
  sourceAuthority Float    // [0-1]
  signalType      String   // "mention" | "recommendation" | "overrated_flag" | "hidden_gem" | "negative"
  rawExcerpt      String?  // purged after 30 days (compliance)
  extractedAt     DateTime
  createdAt       DateTime @default(now())
  @@index([activityNodeId, sourceName])
}
```

## User + RBAC
```prisma
model User {
  id                String           @id @default(uuid())
  email             String           @unique
  name              String?
  avatarUrl         String?
  googleId          String?          @unique
  emailVerified     DateTime?
  subscriptionTier  SubscriptionTier @default(beta)
  systemRole        SystemRole       @default(user)
  featureFlags      Json?
  accessCohort      String?
  stripeCustomerId  String?          @unique
  stripeSubId       String?
  stripePriceId     String?
  onboardingComplete Boolean         @default(false)
  createdAt         DateTime         @default(now())
  updatedAt         DateTime         @updatedAt
  lastActiveAt      DateTime?
}

enum SubscriptionTier { free, beta, pro, lifetime }
enum SystemRole { user, admin }
```

## TripMember
```prisma
model TripMember {
  id        String       @id @default(uuid())
  tripId    String
  userId    String
  role      TripRole     // organizer | member
  status    MemberStatus // invited | joined | declined
  joinedAt  DateTime?
  createdAt DateTime     @default(now())
  @@unique([tripId, userId])
}
```

## ModelRegistry
```prisma
model ModelRegistry {
  id              String     @id @default(uuid())
  modelName       String     // "vibe_tagger" | "ranking_bpr" | "ranking_two_tower" | "convergence_scorer"
  modelVersion    String     // semver
  stage           ModelStage // staging | ab_test | production | archived
  modelType       String     // "classification" | "ranking" | "extraction" | "scoring"
  description     String?
  artifactPath    String?    // GCS path
  configSnapshot  Json?      // hyperparams frozen at registration
  metrics         Json?      // {"precision": 0.87, "recall": 0.82}
  evaluatedAt     DateTime?
  trainingDataRange Json?    // {"from": "...", "to": "...", "signal_count": N}
  parentVersionId String?
  promotedAt      DateTime?
  promotedBy      String?    // "auto_eval" | "admin_manual" | admin user ID
  createdAt       DateTime   @default(now())
  updatedAt       DateTime   @updatedAt
  @@unique([modelName, modelVersion])
  @@index([modelName, stage])
}

enum ModelStage { staging, ab_test, production, archived }
```

## ActivityAlias (entity resolution)
```prisma
model ActivityAlias {
  id              String   @id @default(uuid())
  activityNodeId  String
  alias           String
  source          String
  createdAt       DateTime @default(now())
  @@index([alias])
  @@index([activityNodeId])
}
```

## PivotEvent (Track 5 schema, defined in Foundation)
```prisma
model PivotEvent {
  id              String       @id @default(uuid())
  tripId          String
  slotId          String
  triggerType     PivotTrigger // weather_change | venue_closed | time_overrun | user_mood | user_request
  triggerPayload  Json?
  originalNodeId  String
  alternativeIds  String[]     // ranked alternatives shown
  selectedNodeId  String?      // null = rejected all
  status          PivotStatus  // proposed | accepted | rejected | expired
  resolvedAt      DateTime?
  responseTimeMs  Int?         // UX metric
  createdAt       DateTime     @default(now())
  @@index([tripId, createdAt])
  @@index([status])
}

enum PivotTrigger { weather_change, venue_closed, time_overrun, user_mood, user_request }
enum PivotStatus { proposed, accepted, rejected, expired }
```

MAX_PIVOT_DEPTH=1 enforced at app layer, not schema.
Table exists at Foundation but empty until Track 5 ships.

## Design Tokens (CSS Custom Properties — LOCKED)
```css
:root {
  --warm-background: #FAF7F4;  --warm-surface: #FFFFFF;  --warm-border: #E8E0D8;
  --accent: #C4694F;  --accent-hover: #B85C3F;
  --text-primary: #2C2C2C;  --text-secondary: #6B6B6B;  --text-muted: #9B9B9B;
  --success: #4A7C59;  --warning: #D4A843;  --error: #C25B4A;
  --font-heading: 'Sora';  --font-body: 'Sora';  --font-mono: 'DM Mono';  --font-serif: 'Lora';
  --space-xs:4px; --space-sm:8px; --space-md:16px; --space-lg:24px; --space-xl:32px; --space-2xl:48px;
  --radius-sm:8px; --radius-md:12px; --radius-lg:16px; --radius-full:9999px;
  --shadow-card: 0 2px 8px rgba(0,0,0,0.06);  --shadow-elevated: 0 4px 16px rgba(0,0,0,0.1);
}
```
Dark mode overrides via @media (prefers-color-scheme: dark).
Tailwind config maps these: bg-warm-background, text-accent, font-heading, etc.
No track introduces new tokens without a Foundation PR.

## API Response Envelope (Convention)
```typescript
// Success: { data: T, meta: { requestId, timestamp, modelVersion? } }
// Error: { error: { code, message, details? }, meta: { requestId, timestamp } }
// Paginated: { data: T[], pagination: { total, limit, offset, hasMore }, meta }
```
- requestId on every response (Sentry correlation)
- modelVersion on any ML/LLM-involved response (ModelRegistry trace)
- Cursor pagination for feeds, offset for admin views
- HTTP status codes only: 200/201/400/401/403/404/429/500
- Same envelope for FastAPI and Next.js API routes

## Qdrant Collection Schema
```json
{
  "collection": "activity_nodes",
  "vectors": { "size": 1536, "distance": "Cosine" },
  "payload_schema": {
    "city": "keyword", "country": "keyword", "neighborhood": "keyword",
    "category": "keyword", "subcategory": "keyword", "price_level": "integer",
    "vibe_tags": "keyword[]", "convergence_score": "float", "authority_score": "float",
    "status": "keyword", "is_canonical": "bool", "latitude": "float", "longitude": "float"
  }
}
```
- Vector from descriptionLong + vibe tags + category embedding
- is_canonical=true filter on every query
- No raw text in Qdrant — descriptions stay in Postgres
- Sync via jsonschema-to-qdrant.ts codegen script
- Collection rebuild on embedding model change (it's a projection)

## ALL 16 CONTRACTS COMPLETE
