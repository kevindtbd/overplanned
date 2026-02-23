# Privacy & Data Settings Section — Design

**Date**: 2026-02-22
**Status**: Reviewed (deepener + architect + security), ready for implementation plan

## Context

Settings page has a `PrivacyStub` placeholder. Schema has `DataConsent` model (2 booleans: `modelTraining`, `anonymizedResearch`, both default false/opt-in per GDPR). This section needs: consent toggles, data export, account deletion.

## Decisions

- **GDPR-compliant beta**: consent toggles live, sync data export, account deletion
- **No trip deletion on account delete**: trips are training data. Anonymize userId to "DELETED" in 6 orphan tables (see Anonymization section below).
- **Sync export for beta**: GET endpoint gathers all user data, returns JSON blob. Async email-based export deferred to when data volumes justify it (threshold: ~50 trips per user).
- **Simple rate limit on export**: 1 request per 10 minutes per user (in-memory Map). Single-instance only, upgrade to Redis for multi-instance production.
- **Inline confirmation for delete**: no modal, consistent with calm design philosophy.
- **Email confirmation for delete**: server-side requires `{ confirmEmail }` matching session email. Blocks scripted deletion from stolen sessions.
- **Consent audit logging**: every consent toggle change logged to AuditLog (GDPR Article 7 compliance).
- **Consent copy avoids surveillance language**: "Use my data to improve recommendations" not "Allow us to track your behavior"
- **PII boundary contract**: User row = PII. Signal/event tables contain pseudonymous UUIDs only. Free-text fields (rawAction, payload) must never store identifiable information.

## Anonymization on Delete (Review Finding #1)

6 tables have `userId` as bare String (no FK, no cascade):
- `Trip`, `BehavioralSignal`, `IntentionSignal`, `RawEvent`, `PersonaDimension`, `RankingEvent`

On account deletion, a `$transaction` sets `userId = "DELETED"` on all 6 tables, then deletes the User row. Cascade handles the rest (Session, Account, TripMember, UserPreference, NotificationPreference, DataConsent, BackfillTrip, BackfillSignal, PersonaDelta).

Also anonymize: `AuditLog.actorId`, `SharedTripToken.createdBy`, `InviteToken.createdBy` (bare string refs).

## API Routes

### `GET /api/settings/privacy`
- Auth required
- Returns `{ modelTraining: bool, anonymizedResearch: bool }` from DataConsent
- If no record: `{ modelTraining: false, anonymizedResearch: false }`

### `PATCH /api/settings/privacy`
- Auth -> JSON parse -> `updateConsentSchema.safeParse` (with `.refine` for non-empty)
- Upsert with userId from session (never from body)
- **Audit log**: before upsert, read current values. After upsert, log before/after to AuditLog with `action: "consent_update"`, `targetType: "DataConsent"`.
- Returns `{ modelTraining, anonymizedResearch }`

### `GET /api/settings/export`
- Auth required
- Rate limit: 1 per 10 minutes per user (in-memory Map). 429 if too soon with `{ error: "Please wait before requesting another export." }`.
- Uses `new NextResponse(JSON.stringify(...))` (not `NextResponse.json()`) for Content-Disposition header.
- `$transaction` read gathers ALL user data with explicit `select` clauses:
  - User profile (name, email, createdAt, subscriptionTier)
  - UserPreference (dietary, mobility, languages, travelFrequency)
  - NotificationPreference (7 booleans)
  - DataConsent (2 booleans)
  - Trips (via TripMember where userId, include slots with activityNode name/category)
  - BehavioralSignals (where userId) -- signalType, rawAction, tripPhase, createdAt (NO signalValue -- internal ML weight)
  - IntentionSignals (where userId) -- intentionType, confidence, source, createdAt
  - RawEvents (where userId) -- eventType, intentClass, createdAt (NO payload -- may contain internal data)
  - PersonaDimensions (where userId) -- dimensionName, score, confidence, createdAt
  - RankingEvents (where userId) -- context, selectedId, alternatives count, createdAt
  - BackfillTrips (where userId, include venues) -- NO confidenceTier (internal ML classification)
- Returns with `Content-Disposition: attachment; filename="overplanned-export-YYYY-MM-DD.json"`

### `DELETE /api/settings/account`
- Auth required
- Requires body: `{ confirmEmail: string }` -- must match `session.user.email` (case-insensitive)
- Single `$transaction`:
  1. Anonymize 6 orphan tables: `updateMany({ where: { userId }, data: { userId: "DELETED" } })`
  2. Anonymize AuditLog.actorId, SharedTripToken.createdBy, InviteToken.createdBy
  3. Delete User row (cascade handles Session, Account, TripMember, prefs, consent, backfill)
- Returns `{ deleted: true }`
- Client: `signOut({ callbackUrl: "/" })` gated on `res.ok`
- On failure: reset deleting state, show error message

### Zod for DELETE
```typescript
export const deleteAccountSchema = z.object({
  confirmEmail: z.string().email("Valid email required"),
});
```

## Export JSON Shape

```json
{
  "exportedAt": "ISO timestamp",
  "profile": {
    "name": "string|null",
    "email": "string",
    "createdAt": "ISO timestamp",
    "subscriptionTier": "string"
  },
  "preferences": {
    "dietary": ["string"],
    "mobility": ["string"],
    "languages": ["string"],
    "travelFrequency": "string|null"
  },
  "notifications": {
    "tripReminders": true,
    "morningBriefing": true,
    "groupActivity": true,
    "postTripPrompt": true,
    "citySeeded": true,
    "inspirationNudges": false,
    "productUpdates": false
  },
  "consent": {
    "modelTraining": false,
    "anonymizedResearch": false
  },
  "trips": [{
    "name": "string|null",
    "destination": "string",
    "city": "string",
    "country": "string",
    "startDate": "ISO",
    "endDate": "ISO",
    "status": "string",
    "mode": "string",
    "createdAt": "ISO",
    "slots": [{
      "dayNumber": 1,
      "slotType": "string",
      "status": "string",
      "activityNode": { "name": "string", "category": "string" }
    }]
  }],
  "behavioralSignals": [{
    "signalType": "string",
    "rawAction": "string",
    "tripPhase": "string",
    "createdAt": "ISO"
  }],
  "intentionSignals": [{
    "intentionType": "string",
    "confidence": 0.0,
    "source": "string",
    "createdAt": "ISO"
  }],
  "rawEvents": [{
    "eventType": "string",
    "intentClass": "string",
    "createdAt": "ISO"
  }],
  "personaDimensions": [{
    "dimensionName": "string",
    "score": 0.0,
    "confidence": 0.0,
    "createdAt": "ISO"
  }],
  "rankingEvents": [{
    "context": "string",
    "selectedId": "string|null",
    "alternativesCount": 0,
    "createdAt": "ISO"
  }],
  "backfillTrips": [{
    "city": "string",
    "country": "string",
    "traveledAt": "ISO|null",
    "venues": [{
      "name": "string",
      "category": "string",
      "city": "string"
    }]
  }]
}
```

## Component: `PrivacySection.tsx`

Replaces `PrivacyStub`. Three sub-sections:

### Data Consent (top)
- dm-mono "CONSENT" label
- 2 toggle switches (same pattern as NotificationsSection)
- "Use my data to improve recommendations" (modelTraining)
- "Include my anonymized data in research" (anonymizedResearch)
- Immediate save per toggle, revert on failure

### Your Data (middle)
- dm-mono "YOUR DATA" label
- Description: "Download a copy of all your Overplanned data in JSON format."
- Button: "Download my data" (warm-border style)
- On click: fetch -> check `res.ok` / `res.status === 429` -> blob download
- Blob download pattern: `URL.createObjectURL` -> programmatic `<a>` click -> `setTimeout(() => URL.revokeObjectURL(url), 5000)`
- Loading state on button during download
- 429: show "Please wait before requesting another export."
- Error: show "Failed to download. Please try again."

### Delete Account (bottom)
- dm-mono "DANGER ZONE" label
- Description: "Permanently delete your account and all personal data. Trip data is kept anonymously for service improvement."
- Button: "Delete my account" (red text)
- Inline confirmation (not modal):
  - "Type your email to confirm: [input]"
  - [Cancel] (ghost) + [Yes, delete my account] (red bg, disabled until email matches)
  - Confirm button disabled while `deleting === true`
- On confirm: DELETE /api/settings/account with `{ confirmEmail }` -> if `res.ok` -> `signOut({ callbackUrl: "/" })`
- On failure: reset deleting state, show error

## Zod Schema Updates

Add `.refine` to `updateConsentSchema` + add `deleteAccountSchema`:
```typescript
export const updateConsentSchema = z
  .object({
    modelTraining: z.boolean().optional(),
    anonymizedResearch: z.boolean().optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");

export const deleteAccountSchema = z.object({
  confirmEmail: z.string().email("Valid email required"),
});
```

## Page Wiring

- Import `PrivacySection` instead of `PrivacyStub`
- Delete `PrivacyStub.tsx`
- Pass `email={session.user.email}` prop to PrivacySection (needed for delete confirmation matching)

## Tests

### `settings-privacy.test.ts` (~11 tests)
- GET/PATCH auth guards (401)
- GET defaults when no record
- GET returns saved consent
- PATCH invalid JSON -> 400
- PATCH empty body -> 400
- PATCH validates boolean types
- PATCH upserts, userId from session
- PATCH explicit false stored
- PATCH ignores extra fields
- PATCH creates AuditLog entry with before/after values
- PATCH userId from session, not body (IDOR)

### `settings-export.test.ts` (~6 tests)
- Auth guard (401)
- Returns Content-Disposition header with date-stamped filename
- Response has all sections (profile, trips, signals, intentions, rawEvents, persona, ranking, backfill)
- Empty user returns valid structure with empty arrays
- Rate limit: 429 on second request within 10 min
- Export uses explicit select (no internal fields like signalValue, confidenceTier, payload)

### `settings-delete-account.test.ts` (~8 tests)
- Auth guard (401)
- Missing confirmEmail -> 400
- Wrong confirmEmail -> 403
- Correct email -> anonymizes 6+ tables, deletes user
- Verify $transaction: anonymize updateMany calls + user delete
- userId from session, not body
- Returns { deleted: true }
- Case-insensitive email match

### `PrivacySection.test.tsx` (~10 tests)
- Skeleton then toggles after load
- Toggle triggers PATCH, revert on failure
- Export button triggers blob download
- Export 429 shows rate limit message
- Export error shows error message
- Delete shows inline confirmation with email input
- Cancel hides confirmation
- Confirm disabled until email matches
- Confirm triggers DELETE + signOut
- Delete failure shows error, resets state

### SettingsPage.test.tsx update
- Mock PrivacySection with heading `<h2>Privacy & Data</h2>`

## Execution Order
1. Zod schema update (add refine to consent + add deleteAccountSchema)
2. API routes (privacy, export, delete) -- parallel
3. Component (PrivacySection)
4. Page wiring + delete stub
5. Tests -- parallel
6. Full suite run

## Review Findings Incorporated

| # | Source | Finding | Resolution |
|---|--------|---------|------------|
| 1 | All 3 | 6 tables with userId have no cascade | Anonymize to "DELETED" in $transaction before User delete |
| 2 | Deepener + Security | Export missing 4 signal tables | Added IntentionSignal, RawEvent, PersonaDimension, RankingEvent |
| 3 | Security | No re-auth for account deletion | Added email confirmation (server-side validated) |
| 4 | Security + Architect | No consent audit trail | Added AuditLog create on consent PATCH |
| 5 | Architect + Deepener | Delete needs $transaction | Wrapped all anonymize + delete in single $transaction |
| 6 | Security | Export leaks internal ML data | Stripped signalValue, confidenceTier, payload from export |
| 7 | Architect | No error UI for DELETE failure | Added error state + message to component spec |
| 8 | Architect | Double-click on delete confirm | Disabled button while deleting === true |
| 9 | Deepener | Blob download revokeObjectURL timing | setTimeout 5s before revoke |
| 10 | Deepener | Use new NextResponse() for Content-Disposition | Specified in export route |
| 11 | Deepener | In-memory rate limit doesn't scale | Documented as single-instance, Redis upgrade path noted |
| 12 | Architect | Export needs explicit select clauses | Required in implementation spec |
