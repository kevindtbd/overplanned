# Red Team Security Review: PostTrip Phase

**Date:** 2026-02-20
**Reviewer:** soc-core-lite (Red Team Mode)
**Phase:** PostTrip (Phase 5) - Pre-commit review
**Scope:** Photo upload, trip completion, intention signals, disambiguation

---

## Executive Summary

**BLOCK DEPLOYMENT** - Critical authentication and authorization vulnerabilities found.

- **7 CRITICAL** vulnerabilities requiring immediate fix
- **4 HIGH** severity issues causing runtime failures
- **3 MEDIUM** severity issues for hardening

**Primary Risk:** Unauthenticated users can upload files to arbitrary GCS paths, complete anyone's trips, and inject training data into ML signals.

---

## CRITICAL Vulnerabilities

### C-1: Upload Endpoint - Authentication Bypass
**File:** `services/api/routers/upload.py:74`
**Severity:** CRITICAL (CVSS 9.1)

```python
user_id = getattr(request.state, "user_id", "anonymous")
```

**Issue:** Falls back to "anonymous" if no user is authenticated. Anyone can generate signed GCS URLs without authentication.

**Correct Pattern (from pivot.py:36-40):**
```python
def _require_user_id(request: Request) -> str:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return user_id
```

**Impact:**
- Unauthenticated access to upload endpoint
- Storage quota abuse (10MB per upload, unlimited uploads)
- GCS storage cost attack vector

**Fix:** Replace with `_require_user_id(request)` helper (lines 74, 63).

---

### C-2: Upload Endpoint - Authorization Bypass (Trip Ownership)
**File:** `services/api/routers/upload.py:30-31, 84`
**Severity:** CRITICAL (CVSS 8.8)

```python
tripId: str = Field(min_length=1)
slotId: str = Field(min_length=1)
# ...
object_path = f"photos/{body.tripId}/{body.slotId}/{file_id}.{ext}"
```

**Issue:** No verification that authenticated user owns the trip. Users can upload photos to ANY trip by guessing/enumerating trip IDs.

**Missing Check:**
```python
# After getting user_id, verify trip ownership:
trip = await db.trip.find_unique(where={"id": body.tripId})
if not trip or trip.userId != user_id:
    raise HTTPException(status_code=403, detail="Trip not found or access denied")

# Also verify slot belongs to trip:
slot = await db.itineraryslot.find_unique(where={"id": body.slotId})
if not slot or slot.tripId != body.tripId:
    raise HTTPException(status_code=400, detail="Slot does not belong to trip")
```

**Impact:**
- Users can upload photos to other users' trips
- Privacy violation (can see trip structure via enumeration)
- Data poisoning for ML recommendation signals

**Fix:** Add trip ownership + slot membership verification before generating signed URL.

---

### C-3: Upload Endpoint - Path Traversal Risk
**File:** `services/api/routers/upload.py:30-31, 84`
**Severity:** CRITICAL (CVSS 7.5)

```python
tripId: str = Field(min_length=1)  # Not validated as UUID
slotId: str = Field(min_length=1)  # Not validated as UUID
object_path = f"photos/{body.tripId}/{body.slotId}/{file_id}.{ext}"
```

**Issue:** `tripId` and `slotId` only validated for `min_length=1`, not UUID format. Could contain path traversal sequences.

**Attack Vector:**
```json
{
  "tripId": "../../../etc",
  "slotId": "passwd",
  "contentType": "image/jpeg",
  "fileSizeBytes": 1024
}
```

Results in GCS path: `photos/../../../etc/passwd/{uuid}.jpg`

**Fix:** Add UUID validation:
```python
@field_validator("tripId", "slotId")
@classmethod
def validate_uuid(cls, v: str) -> str:
    try:
        uuid.UUID(v)
    except ValueError:
        raise ValueError(f"Must be a valid UUID")
    return v
```

---

### C-4: Completion Endpoint - Authorization Bypass
**File:** `services/api/posttrip/completion.py:43-70`
**Severity:** CRITICAL (CVSS 8.1)

```python
async def mark_trip_completed(
    db: Prisma,
    trip_id: str,
    completed_at: Optional[datetime] = None
) -> Trip:
    trip = await db.trip.update(
        where={"id": trip_id},
        data={"status": "completed", "completedAt": completed_at}
    )
    return trip
```

**Issue:** No verification that caller owns the trip. Any authenticated user (or scheduled job) can complete anyone's trips.

**Missing Check:**
```python
# Before update:
trip = await db.trip.find_unique(where={"id": trip_id})
if not trip:
    raise ValueError(f"Trip '{trip_id}' not found")
# If called from API endpoint (not scheduled job):
if user_id and trip.userId != user_id:
    raise ValueError(f"Trip '{trip_id}' does not belong to user '{user_id}'")
```

**Impact:**
- Users can prematurely complete other users' active trips
- Breaks trip state machine
- Triggers post-trip flow for trips that aren't actually finished

**Fix:** Add optional `user_id` parameter for authorization check when called from API (not scheduled job).

---

### C-5: Intention Signal - Weak Authorization
**File:** `services/api/posttrip/intention_signal.py:72-88`
**Severity:** CRITICAL (CVSS 7.8)

```python
parent_signal = await db.behavioralsignal.find_unique(
    where={"id": behavioral_signal_id}
)
if parent_signal.userId != user_id:
    raise ValueError(...)
```

**Issue:** Only checks behavioral signal ownership, not trip ownership. If attacker can enumerate/guess behavioral signal IDs from other users' trips, they can inject intention signals.

**Additional Check Needed:**
```python
# After verifying signal ownership, also verify trip ownership:
if parent_signal.tripId:
    trip = await db.trip.find_unique(where={"id": parent_signal.tripId})
    if not trip or trip.userId != user_id:
        raise ValueError(
            f"Trip '{parent_signal.tripId}' does not belong to user '{user_id}'"
        )
```

**Impact:**
- Training data poisoning (intentionType with confidence=1.0)
- ML model learns incorrect skip patterns
- Degraded recommendation quality for all users

**Fix:** Add trip ownership verification.

---

### C-6: Disambiguation - Field Name Mismatch (Runtime Error)
**File:** `services/api/posttrip/disambiguation.py:86-122, 203-210`
**Severity:** CRITICAL (Runtime Failure)

**Issue 1 - Context Building (snake_case vs camelCase):**
```python
context: dict[str, Any] = {
    "signal_type": signal.signal_type,    # ❌ signal.signalType
    "user_id": signal.user_id,            # ❌ signal.userId
}
# Later:
if signal.raw_event_id:  # ❌ signal.rawEventId
    raw_event = await db.rawevent.find_unique(where={"id": signal.raw_event_id})
```

Python Prisma client uses camelCase for all fields. Code will fail with `AttributeError`.

**Issue 2 - IntentionSignal Creation (wrong field names):**
```python
await db.intentionsignal.create(
    data={
        "user_id": signal.user_id,                    # ❌ userId
        "behavioral_signal_id": signal.id,            # ❌ behavioralSignalId
        "raw_event_id": signal.raw_event_id,          # ❌ rawEventId
        "trip_id": signal.trip_id,                    # ❌ tripId
        "itinerary_slot_id": signal.itinerary_slot_id,# ❌ itinerarySlotId
        "activity_node_id": signal.activity_node_id,  # ❌ activityNodeId
        "intention_type": "skip_reason",              # ❌ Wrong value (see Issue 3)
        "intention_value": skip_reason,               # ❌ Field doesn't exist
        "created_at": ...,                            # ❌ createdAt (auto-generated anyway)
    }
)
```

**Issue 3 - IntentionSignal Schema:**
Schema only has:
```prisma
intentionType String  // Stores: "not_interested", "weather", etc.
```

No `intentionValue` field. The skip_reason should go directly in `intentionType`.

**Correct Creation:**
```python
await db.intentionsignal.create(
    data={
        "userId": signal.userId,
        "behavioralSignalId": signal.id,
        "rawEventId": signal.rawEventId,
        "intentionType": skip_reason,  # "not_interested", "weather", etc.
        "confidence": confidence,
        "source": "rule_heuristic",
        "metadata": {
            "rule_version": "1.0",
            "inferred_at": signal.createdAt.isoformat(),
        },
    }
)
```

**Impact:**
- Batch job crashes on first signal processed
- Zero intention signals created
- ML training data gap (no rule-based inferences)

**Fix:** Update all field names to camelCase + remove non-existent fields.

---

### C-7: Missing Frontend API Route
**File:** `apps/web/components/posttrip/PhotoStrip.tsx:37`
**Severity:** HIGH (Production Failure)

```typescript
const res = await fetch("/api/upload/signed-url", {
  method: "POST",
  // ...
});
```

**Issue:** No Next.js API route at `apps/web/app/api/upload/signed-url/route.ts`.

**Impact:**
- All photo uploads fail with 404
- PhotoStrip component unusable in production
- User-facing feature completely broken

**Fix:** Create Next.js API route that:
1. Validates session (NextAuth)
2. Proxies request to FastAPI `/upload/signed-url` endpoint
3. Injects `X-User-Id` header from session
4. Returns signed URL to client

---

## HIGH Severity Issues

### H-1: Disambiguation - Source Field Inconsistency
**File:** `services/api/posttrip/intention_signal.py:97`, `disambiguation.py:206`
**Severity:** HIGH

**Issue:** intention_signal.py uses `source="user_explicit"` but disambiguation.py uses `source="rule_heuristic"`. The check at line 167 filters for `source="explicit_feedback"` which doesn't match either.

```python
# intention_signal.py:97
"source": "user_explicit",

# disambiguation.py:167
where={"source": "explicit_feedback"}  # ❌ Never matches

# disambiguation.py:206
"source": "rule_heuristic",
```

**Impact:**
- User-provided signals (confidence=1.0) are overwritten by rule inferences (confidence=0.6-0.8)
- High-quality training data degraded by lower-confidence rules
- ML model learns noise instead of truth

**Fix:** Standardize source values:
```python
# Constants module:
INTENTION_SOURCE_USER = "user_explicit"
INTENTION_SOURCE_RULE = "rule_heuristic"
INTENTION_SOURCE_MODEL = "model_inference"
```

Update line 167 to check for `source=INTENTION_SOURCE_USER`.

---

### H-2: Upload - Weak Content-Type Validation
**File:** `services/api/routers/upload.py:35-42`, `PhotoStrip.tsx:88`
**Severity:** MEDIUM

**Issue:** Validates only Content-Type header, which can be spoofed. Attacker can upload executable files with `Content-Type: image/jpeg`.

**Attack Vector:**
```bash
curl -X POST /api/upload/signed-url \
  -H "Content-Type: application/json" \
  -d '{"tripId":"...","slotId":"...","contentType":"image/jpeg","fileSizeBytes":1024}'
# Returns signed URL

curl -X PUT "<signed-url>" \
  -H "Content-Type: image/jpeg" \
  --data-binary @malware.exe
# Uploads malware.exe to GCS with .jpg extension
```

**Impact:**
- Malware hosting via GCS
- XSS if GCS bucket serves with `Content-Type: text/html`
- Browser exploitation via polyglot files

**Fix:**
1. After client uploads to GCS, trigger Cloud Function to validate file
2. Use libmagic/python-magic to check magic number
3. If not valid image, delete object + revoke slot.imageUrl
4. Log security event

---

### H-3: Disambiguation - Unvalidated Rule Loading
**File:** `services/api/posttrip/disambiguation.py:29-33`
**Severity:** MEDIUM

```python
def load_rules() -> list[dict[str, Any]]:
    with open(RULES_PATH) as f:
        config = json.load(f)
    return config["rules"]
```

**Issue:** Loads rules from JSON without validation. If attacker gains write access to `disambiguation_rules.json`, they can:
- Inject SQL-like conditions (though safe due to dict comparison)
- Set confidence=1.0 for garbage rules
- Add thousands of rules to DoS the batch job

**Fix:**
1. Validate JSON schema on load (pydantic model)
2. Set file permissions to read-only in production (chmod 444)
3. Version-control rules file + require PR review for changes

---

## MEDIUM Severity Issues

### M-1: Upload - Information Disclosure
**File:** `services/api/routers/upload.py:96-99`
**Severity:** LOW

```python
except Exception:
    # Fallback for local dev without GCS credentials
    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name={object_path}"
    public_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{object_path}"
```

**Issue:** Reveals GCS bucket name and path structure even when credentials aren't configured.

**Fix:** Return generic error in production:
```python
except Exception as e:
    logger.error(f"Failed to generate signed URL: {e}")
    raise HTTPException(
        status_code=500,
        detail="Upload service temporarily unavailable"
    )
```

---

### M-2: Upload - Generous Signed URL Expiry
**File:** `services/api/routers/upload.py:23`
**Severity:** LOW

```python
SIGNED_URL_EXPIRY = timedelta(minutes=15)
```

**Issue:** 15 minutes allows time for URL sharing/abuse.

**Fix:** Reduce to 5 minutes (sufficient for 10MB upload on slow connections).

---

### M-3: Completion - No Idempotency Check
**File:** `services/api/posttrip/completion.py:62-67`
**Severity:** LOW

**Issue:** Calling `mark_trip_completed` multiple times updates `completedAt` timestamp. Could be used to fake trip timing.

**Fix:**
```python
trip = await db.trip.find_unique(where={"id": trip_id})
if trip.status == "completed":
    return trip  # Already completed, no-op
```

---

## Summary Statistics

| Severity | Count | Must Fix Before Deploy |
|----------|-------|------------------------|
| CRITICAL | 7     | ✅ YES                 |
| HIGH     | 2     | ✅ YES                 |
| MEDIUM   | 3     | ⚠️ Recommended         |

**Total Issues:** 12
**Blocking Issues:** 9

---

## Recommended Actions

### Before Commit
1. Fix C-1 to C-7 (all critical issues)
2. Fix H-1 (source field standardization)
3. Create missing API route (C-7)

### Before Production Deploy
1. Implement file type validation (H-2)
2. Add rule schema validation (H-3)
3. Reduce signed URL expiry (M-2)
4. Add idempotency checks (M-3)

### Infrastructure
1. Set `disambiguation_rules.json` to read-only (chmod 444)
2. Enable GCS Cloud Armor for DDoS protection
3. Set up Sentry alerts for 401/403 errors (spike = attack)
4. Add rate limiting to `/upload/signed-url` (max 10 requests/minute per user)

---

## Conclusion

**DO NOT MERGE** until C-1 through C-7 are fixed.

The PostTrip implementation has solid architecture (three-layer signals, rule-based ML, timezone-aware completion) but critical security gaps in authentication, authorization, and field naming.

Most issues are straightforward fixes (add ownership checks, fix field names, create API route). Estimated remediation time: 2-4 hours.

Once fixed, this will be a solid foundation for ML training data collection.

---

**Reviewed by:** soc-core-lite
**Next Step:** Fix critical issues → Re-review → Commit
