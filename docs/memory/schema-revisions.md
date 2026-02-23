# Schema Revisions (Post Agent Review)

## Decisions Locked
- **Redis**: YES — docker-compose, ranking cache, rate limiting, session store
- **Embedding model**: nomic-embed-text-v1.5 (768 dim, Apache 2.0, local inference, zero API cost)
- **No-account join**: KILLED — must sign up via Google OAuth to join group trip
- **IntentionSignal**: training feature — feeds ranking model as context features
- **Qdrant vector size**: 768 (updated from 1536 to match nomic-embed-text-v1.5)

## New Models Added to Foundation Schema

### VibeTag (was missing — junction table referenced nonexistent table)
```prisma
model VibeTag {
  id          String   @id @default(uuid())
  slug        String   @unique    // "hole-in-the-wall", "late-night"
  name        String              // "Hole in the Wall", "Late Night"
  category    String              // "dining-character", "atmosphere", "activity-type"
  isActive    Boolean  @default(true)
  sortOrder   Int      @default(0)
  createdAt   DateTime @default(now())

  activityNodeVibeTags ActivityNodeVibeTag[]
}
```
Seeded with 42 locked tags in Foundation M-001.

### SharedTripToken (security critical)
```prisma
model SharedTripToken {
  id          String    @id @default(uuid())
  tripId      String
  trip        Trip      @relation(fields: [tripId], references: [id])
  token       String    @unique   // crypto.randomBytes(32).toString('base64url')
  createdBy   String
  expiresAt   DateTime            // default 90 days
  revokedAt   DateTime?
  viewCount   Int       @default(0)
  importCount Int       @default(0)
  createdAt   DateTime  @default(now())

  @@index([token])
}
```

### InviteToken (security critical — replaces no-account join)
```prisma
model InviteToken {
  id          String    @id @default(uuid())
  tripId      String
  trip        Trip      @relation(fields: [tripId], references: [id])
  token       String    @unique   // crypto.randomBytes(32).toString('base64url')
  createdBy   String              // organizer user ID
  maxUses     Int       @default(1)
  usedCount   Int       @default(0)
  role        TripRole  @default(member) // never organizer via link
  expiresAt   DateTime            // default 7 days, max 30
  revokedAt   DateTime?
  createdAt   DateTime  @default(now())

  @@index([token])
}
```
Organizer role NEVER granted via invite link.

### AuditLog (admin actions)
```prisma
model AuditLog {
  id          String   @id @default(uuid())
  actorId     String
  action      String   // "model_promote" | "user_flag_override" | "node_edit" | "token_revoke" | "user_lookup"
  targetType  String   // "ModelRegistry" | "User" | "ActivityNode" | "SharedTripToken"
  targetId    String
  before      Json?
  after       Json?
  ipAddress   String
  userAgent   String
  createdAt   DateTime @default(now())

  @@index([actorId, createdAt])
  @@index([targetType, targetId])
}
```
Append-only: no UPDATE or DELETE permissions at DB level.

### NextAuth Required Models (session management)
```prisma
model Session {
  id           String   @id @default(uuid())
  sessionToken String   @unique
  userId       String
  user         User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  expires      DateTime // max 30 days, idle timeout 7 days
  createdAt    DateTime @default(now())
}

model Account {
  id                String  @id @default(uuid())
  userId            String
  user              User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  type              String
  provider          String
  providerAccountId String
  refresh_token     String?
  access_token      String?
  expires_at        Int?
  token_type        String?
  scope             String?
  id_token          String?
  session_state     String?

  @@unique([provider, providerAccountId])
}

model VerificationToken {
  identifier String
  token      String   @unique
  expires    DateTime

  @@unique([identifier, token])
}
```
Database-backed sessions (not JWT). Enables revocation, concurrent session limits (max 5), admin termination.

## Field Additions to Existing Models

### Trip — add timezone
```prisma
// ADD to Trip model:
  timezone    String    // IANA timezone e.g. "Asia/Tokyo". Required, populated from destination at creation.
```

### BehavioralSignal — add indexes
```prisma
// ADD indexes to BehavioralSignal:
  @@index([userId, createdAt])
  @@index([userId, tripId, signalType])
  @@index([activityNodeId, signalType])
```

### RawEvent — add clientEventId for idempotency
```prisma
// ADD to RawEvent model:
  clientEventId  String?   // UUID generated on device, dedup key for mobile retries

// ADD constraint:
  @@unique([userId, clientEventId])
```
Batch endpoint uses ON CONFLICT DO NOTHING for silent dedup.

### ModelRegistry — add artifactHash
```prisma
// ADD to ModelRegistry:
  artifactHash    String?   // SHA-256 of model binary, verified at load time
```

### ActivityNodeVibeTag — add relation to VibeTag
```prisma
// CHANGE vibeTagId from String to proper FK:
  vibeTagId       String
  vibeTag         VibeTag  @relation(fields: [vibeTagId], references: [id])
```

## Infrastructure Changes

### docker-compose.yml updates
```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - '127.0.0.1:5432:5432'  # localhost only
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-overplanned}
      POSTGRES_USER: ${POSTGRES_USER:-overplanned}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - '127.0.0.1:6379:6379'
    command: redis-server --requirepass ${REDIS_PASSWORD:?REDIS_PASSWORD is required}
    volumes:
      - redisdata:/data

  qdrant:
    image: qdrant/qdrant
    ports:
      - '127.0.0.1:6333:6333'
      - '127.0.0.1:6334:6334'
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:?QDRANT_API_KEY is required}
    volumes:
      - qdrantdata:/qdrant/storage

  pgbouncer:
    image: edoburu/pgbouncer
    ports:
      - '127.0.0.1:6432:6432'
    environment:
      DATABASE_URL: postgres://${POSTGRES_USER:-overplanned}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-overplanned}
      MAX_CLIENT_CONN: 100
      DEFAULT_POOL_SIZE: 20

volumes:
  pgdata:
  redisdata:
  qdrantdata:
```

### Qdrant collection — updated to 768 dim
```json
{
  "collection": "activity_nodes",
  "vectors": { "size": 768, "distance": "Cosine" },
  "payload_schema": { ... same as before ... }
}
```

### Embedding model
- Model: nomic-embed-text-v1.5 (768 dim)
- License: Apache 2.0
- Inference: local via sentence-transformers (Python) on FastAPI service
- No external API dependency, no per-call cost
- Matryoshka support: can truncate to 512/256 dim if needed for speed
- pip install: `sentence-transformers`, model auto-downloads on first use (~270MB)

## Updated Model Count
Was 16 contracts. Now 22:
1. User
2. Session (NEW - NextAuth)
3. Account (NEW - NextAuth)
4. VerificationToken (NEW - NextAuth)
5. Trip (+ timezone field)
6. TripMember
7. ItinerarySlot
8. ActivityNode
9. ActivityNodeVibeTag (+ VibeTag FK)
10. VibeTag (NEW)
11. ActivityAlias
12. QualitySignal
13. BehavioralSignal (+ indexes)
14. IntentionSignal
15. RawEvent (+ clientEventId)
16. ModelRegistry (+ artifactHash)
17. PivotEvent
18. SharedTripToken (NEW)
19. InviteToken (NEW)
20. AuditLog (NEW)

## Dependency Graph Correction
```
Foundation (1) → Pipeline (2) → Solo (3) core [M-001→M-006]
                                    ↓
                              [Group(4), MidTrip(5)] UI work
                                    ↓
                              PostTrip (6)
                Admin (7) — truly parallel from Foundation
```

Track 4/5 schema migrations (their M-001s) CAN start after Foundation.
Track 4/5 UI migrations need Solo(3) core components (slot card, day view, map).
