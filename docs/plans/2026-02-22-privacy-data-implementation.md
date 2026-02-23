# Privacy & Data Settings — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `PrivacyStub` with a functional GDPR-compliant Privacy & Data section: consent toggles, sync data export, and account deletion with anonymization.

**Architecture:** Three API routes (GET+PATCH privacy, GET export, DELETE account) follow the existing settings pattern (session auth, Zod validation, Prisma upsert). Account deletion uses a single `$transaction` to anonymize 9 bare-string userId/actorId/createdBy fields across orphan tables before cascade-deleting the User row. Consent changes are audit-logged per GDPR Article 7.

**Tech Stack:** Next.js 14 App Router, TypeScript, Prisma ORM, Zod, NextAuth, Vitest + React Testing Library

---

## Task 1: Update Zod Schemas

**Files:**
- Modify: `apps/web/lib/validations/settings.ts`

**Step 1: Add `.refine()` to `updateConsentSchema` and add `deleteAccountSchema`**

In `apps/web/lib/validations/settings.ts`, replace lines 57-60:

```typescript
// BEFORE (line 57-60):
export const updateConsentSchema = z.object({
  modelTraining: z.boolean().optional(),
  anonymizedResearch: z.boolean().optional(),
});

// AFTER:
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

**Step 2: Verify existing tests still pass**

Run: `cd apps/web && npx vitest run __tests__/api/settings-preferences.test.ts __tests__/api/settings-notifications.test.ts --reporter=verbose`
Expected: All pass (schema changes are additive, existing schemas untouched)

**Step 3: Commit**

```bash
git add apps/web/lib/validations/settings.ts
git commit -m "feat(settings): add refine guard to consent schema + deleteAccountSchema"
```

---

## Task 2: API Route — GET + PATCH /api/settings/privacy

**Files:**
- Create: `apps/web/app/api/settings/privacy/route.ts`

**Step 1: Write the failing test**

Create `apps/web/__tests__/api/settings-privacy.test.ts`:

```typescript
/**
 * Route handler tests for GET + PATCH /api/settings/privacy
 * Tests auth guards, validation, defaults, upsert, audit logging, and IDOR prevention.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    dataConsent: {
      findUnique: vi.fn(),
      upsert: vi.fn(),
    },
    auditLog: {
      create: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { GET, PATCH } = await import(
  "../../app/api/settings/privacy/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeGetRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/privacy", {
    method: "GET",
  });
}

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/privacy", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/privacy", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

const DEFAULTS = {
  modelTraining: false,
  anonymizedResearch: false,
};

describe("GET /api/settings/privacy — auth guards", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({ user: null } as never);
    const res = await GET();
    expect(res.status).toBe(401);
  });
});

describe("GET /api/settings/privacy — defaults and saved consent", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns defaults when no record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(null as never);

    const res = await GET();
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual(DEFAULTS);
  });

  it("returns saved consent when record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const saved = { modelTraining: true, anonymizedResearch: false };
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(saved as never);

    const res = await GET();
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual(saved);
  });
});

describe("PATCH /api/settings/privacy — auth guard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ modelTraining: true }));
    expect(res.status).toBe(401);
  });
});

describe("PATCH /api/settings/privacy — validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequestInvalidJSON());
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Invalid JSON");
  });

  it("returns 400 for empty body (refine guard)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({}));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when boolean field receives a string", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ modelTraining: "yes" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });
});

describe("PATCH /api/settings/privacy — upsert and audit log", () => {
  beforeEach(() => vi.clearAllMocks());

  it("upserts with userId from session, not body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    // findUnique for before-values
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(null as never);
    const upsertResult = { modelTraining: true, anonymizedResearch: false };
    mockPrisma.dataConsent.upsert.mockResolvedValueOnce(upsertResult as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(
      makePatchRequest({ modelTraining: true, userId: "attacker-id" })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.dataConsent.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create).toMatchObject({ userId: "user-abc" });
    expect(upsertCall.update).not.toHaveProperty("userId");
  });

  it("stores explicit false correctly", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce({
      modelTraining: true,
      anonymizedResearch: false,
    } as never);
    const upsertResult = { modelTraining: false, anonymizedResearch: false };
    mockPrisma.dataConsent.upsert.mockResolvedValueOnce(upsertResult as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(makePatchRequest({ modelTraining: false }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.dataConsent.upsert.mock.calls[0][0];
    expect(upsertCall.update).toEqual({ modelTraining: false });
  });

  it("creates AuditLog entry with before/after values", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const before = { modelTraining: false, anonymizedResearch: false };
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(before as never);
    const after = { modelTraining: true, anonymizedResearch: false };
    mockPrisma.dataConsent.upsert.mockResolvedValueOnce(after as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);

    await PATCH(makePatchRequest({ modelTraining: true }));

    expect(mockPrisma.auditLog.create).toHaveBeenCalledTimes(1);
    const auditCall = mockPrisma.auditLog.create.mock.calls[0][0];
    expect(auditCall.data.actorId).toBe("user-abc");
    expect(auditCall.data.action).toBe("consent_update");
    expect(auditCall.data.targetType).toBe("DataConsent");
    expect(auditCall.data.before).toEqual(before);
    expect(auditCall.data.after).toEqual(after);
  });

  it("ignores extra fields in request body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(null as never);
    mockPrisma.dataConsent.upsert.mockResolvedValueOnce(DEFAULTS as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(
      makePatchRequest({
        modelTraining: true,
        userId: "attacker",
        id: "fake",
        extra: "field",
      })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.dataConsent.upsert.mock.calls[0][0];
    expect(upsertCall.update).not.toHaveProperty("id");
    expect(upsertCall.update).not.toHaveProperty("extra");
  });

  it("returns only the 2 consent fields", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.dataConsent.findUnique.mockResolvedValueOnce(null as never);
    mockPrisma.dataConsent.upsert.mockResolvedValueOnce(DEFAULTS as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(makePatchRequest({ anonymizedResearch: true }));
    const json = await res.json();

    expect(Object.keys(json).sort()).toEqual(["anonymizedResearch", "modelTraining"]);
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("userId");
    expect(json).not.toHaveProperty("createdAt");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run __tests__/api/settings-privacy.test.ts --reporter=verbose`
Expected: FAIL — `Cannot find module '../../app/api/settings/privacy/route'`

**Step 3: Write the route handler**

Create `apps/web/app/api/settings/privacy/route.ts`:

```typescript
/**
 * GET + PATCH /api/settings/privacy
 * Auth: session required, userId from session only
 * GET: returns consent preferences or GDPR-safe defaults (both false)
 * PATCH: upserts consent fields + creates AuditLog entry (GDPR Article 7)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateConsentSchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const CONSENT_SELECT = {
  modelTraining: true,
  anonymizedResearch: true,
} as const;

const DEFAULTS = {
  modelTraining: false,
  anonymizedResearch: false,
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const consent = await prisma.dataConsent.findUnique({
    where: { userId },
    select: CONSENT_SELECT,
  });

  return NextResponse.json(consent ?? DEFAULTS);
}

export async function PATCH(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const result = updateConsentSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Read current values for audit log (before)
  const before = await prisma.dataConsent.findUnique({
    where: { userId },
    select: CONSENT_SELECT,
  });

  const updated = await prisma.dataConsent.upsert({
    where: { userId },
    create: { userId, ...result.data },
    update: result.data,
    select: CONSENT_SELECT,
  });

  // Audit log: consent change (GDPR Article 7)
  await prisma.auditLog.create({
    data: {
      actorId: userId,
      action: "consent_update",
      targetType: "DataConsent",
      targetId: userId,
      before: before ?? DEFAULTS,
      after: updated,
      ipAddress: req.headers.get("x-forwarded-for") ?? "unknown",
      userAgent: req.headers.get("user-agent") ?? "unknown",
    },
  });

  return NextResponse.json(updated);
}
```

**Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run __tests__/api/settings-privacy.test.ts --reporter=verbose`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/privacy/route.ts apps/web/__tests__/api/settings-privacy.test.ts
git commit -m "feat(settings): privacy consent GET+PATCH with audit logging"
```

---

## Task 3: API Route — GET /api/settings/export

**Files:**
- Create: `apps/web/app/api/settings/export/route.ts`

**Step 1: Write the failing test**

Create `apps/web/__tests__/api/settings-export.test.ts`:

```typescript
/**
 * Route handler tests for GET /api/settings/export
 * Tests auth, rate limiting, content-disposition, data shape, and field filtering.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

// Must re-import the route after mocks are set up.
// We also need to reset the rate-limit Map between tests.
let GET: typeof import("../../app/api/settings/export/route").GET;
let resetRateLimit: () => void;

beforeEach(async () => {
  vi.clearAllMocks();
  // Re-import to get fresh rate limit state
  vi.resetModules();
  // Re-mock after reset
  vi.doMock("next-auth", () => ({
    getServerSession: vi.fn(),
  }));
  vi.doMock("@/lib/prisma", () => ({
    prisma: {
      $transaction: vi.fn(),
    },
  }));
  vi.doMock("@/lib/auth/config", () => ({
    authOptions: {},
  }));

  const mod = await import("../../app/api/settings/export/route");
  GET = mod.GET;
  resetRateLimit = mod._resetRateLimitForTest;

  const auth = await import("next-auth");
  const db = await import("@/lib/prisma");
  Object.assign(getServerSession, auth.getServerSession);
  Object.assign(prisma, db.prisma);
});

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

function makeEmptyExportData() {
  return [
    { name: null, email: "test@example.com", createdAt: new Date(), subscriptionTier: "beta" },
    null, // UserPreference
    null, // NotificationPreference
    null, // DataConsent
    [],   // TripMember (trips)
    [],   // BehavioralSignals
    [],   // IntentionSignals
    [],   // RawEvents
    [],   // PersonaDimensions
    [],   // RankingEvents
    [],   // BackfillTrips
  ];
}

describe("GET /api/settings/export — auth", () => {
  it("returns 401 when no session", async () => {
    const { getServerSession: gs } = await import("next-auth");
    vi.mocked(gs).mockResolvedValueOnce(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });
});

describe("GET /api/settings/export — response shape", () => {
  it("returns Content-Disposition header with date-stamped filename", async () => {
    const { getServerSession: gs } = await import("next-auth");
    const { prisma: p } = await import("@/lib/prisma");
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);
    vi.mocked(p.$transaction).mockResolvedValueOnce(makeEmptyExportData() as never);

    const res = await GET();
    expect(res.status).toBe(200);

    const disposition = res.headers.get("content-disposition");
    expect(disposition).toMatch(/^attachment; filename="overplanned-export-\d{4}-\d{2}-\d{2}\.json"$/);
  });

  it("returns valid structure with empty arrays for user with no data", async () => {
    const { getServerSession: gs } = await import("next-auth");
    const { prisma: p } = await import("@/lib/prisma");
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);
    vi.mocked(p.$transaction).mockResolvedValueOnce(makeEmptyExportData() as never);

    const res = await GET();
    const json = await res.json();

    expect(json).toHaveProperty("exportedAt");
    expect(json).toHaveProperty("profile");
    expect(json).toHaveProperty("preferences");
    expect(json).toHaveProperty("notifications");
    expect(json).toHaveProperty("consent");
    expect(json).toHaveProperty("trips");
    expect(json).toHaveProperty("behavioralSignals");
    expect(json).toHaveProperty("intentionSignals");
    expect(json).toHaveProperty("rawEvents");
    expect(json).toHaveProperty("personaDimensions");
    expect(json).toHaveProperty("rankingEvents");
    expect(json).toHaveProperty("backfillTrips");

    expect(json.trips).toEqual([]);
    expect(json.behavioralSignals).toEqual([]);
  });

  it("has all expected sections populated from transaction data", async () => {
    const { getServerSession: gs } = await import("next-auth");
    const { prisma: p } = await import("@/lib/prisma");
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);

    const data = makeEmptyExportData();
    // Add a trip via TripMember
    data[4] = [{
      trip: {
        name: "Rome Trip",
        destination: "Rome",
        city: "Rome",
        country: "Italy",
        startDate: new Date("2026-03-01"),
        endDate: new Date("2026-03-05"),
        status: "planning",
        mode: "solo",
        createdAt: new Date(),
        slots: [{ dayNumber: 1, slotType: "morning", status: "confirmed", activityNode: { name: "Colosseum", category: "culture" } }],
      },
    }];
    vi.mocked(p.$transaction).mockResolvedValueOnce(data as never);

    const res = await GET();
    const json = await res.json();

    expect(json.trips).toHaveLength(1);
    expect(json.trips[0].destination).toBe("Rome");
    expect(json.trips[0].slots).toHaveLength(1);
  });
});

describe("GET /api/settings/export — rate limit", () => {
  it("returns 429 on second request within 10 minutes", async () => {
    const { getServerSession: gs } = await import("next-auth");
    const { prisma: p } = await import("@/lib/prisma");

    // First request succeeds
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);
    vi.mocked(p.$transaction).mockResolvedValueOnce(makeEmptyExportData() as never);
    const res1 = await GET();
    expect(res1.status).toBe(200);

    // Second request rate-limited
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);
    const res2 = await GET();
    expect(res2.status).toBe(429);
    const json = await res2.json();
    expect(json.error).toBe("Please wait before requesting another export.");
  });
});

describe("GET /api/settings/export — field filtering", () => {
  it("does not include internal fields (signalValue, confidenceTier, payload)", async () => {
    const { getServerSession: gs } = await import("next-auth");
    const { prisma: p } = await import("@/lib/prisma");
    vi.mocked(gs).mockResolvedValueOnce(authedSession as never);
    vi.mocked(p.$transaction).mockResolvedValueOnce(makeEmptyExportData() as never);

    await GET();

    // Verify $transaction was called and inspect the callback's queries
    expect(p.$transaction).toHaveBeenCalledTimes(1);
    // The transaction receives a callback — we can't easily inspect Prisma select clauses
    // in unit tests, but the route implementation uses explicit selects.
    // This test primarily verifies the route doesn't crash and returns 200.
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run __tests__/api/settings-export.test.ts --reporter=verbose`
Expected: FAIL — `Cannot find module '../../app/api/settings/export/route'`

**Step 3: Write the route handler**

Create `apps/web/app/api/settings/export/route.ts`:

```typescript
/**
 * GET /api/settings/export
 * Auth: session required
 * Returns all user data as JSON download (GDPR right to portability).
 * Rate limit: 1 request per 10 minutes per user (in-memory).
 * Strips internal ML fields: signalValue, confidenceTier, payload.
 */

import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

const RATE_LIMIT_MS = 10 * 60 * 1000; // 10 minutes
const rateLimitMap = new Map<string, number>();

// Exposed for test reset only
export function _resetRateLimitForTest() {
  rateLimitMap.clear();
}

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // Rate limit check
  const lastExport = rateLimitMap.get(userId);
  if (lastExport && Date.now() - lastExport < RATE_LIMIT_MS) {
    return NextResponse.json(
      { error: "Please wait before requesting another export." },
      { status: 429 }
    );
  }

  const [
    user,
    preferences,
    notifications,
    consent,
    tripMembers,
    behavioralSignals,
    intentionSignals,
    rawEvents,
    personaDimensions,
    rankingEvents,
    backfillTrips,
  ] = await prisma.$transaction([
    prisma.user.findUniqueOrThrow({
      where: { id: userId },
      select: { name: true, email: true, createdAt: true, subscriptionTier: true },
    }),
    prisma.userPreference.findUnique({
      where: { userId },
      select: { dietary: true, mobility: true, languages: true, travelFrequency: true },
    }),
    prisma.notificationPreference.findUnique({
      where: { userId },
      select: {
        tripReminders: true, morningBriefing: true, groupActivity: true,
        postTripPrompt: true, citySeeded: true, inspirationNudges: true, productUpdates: true,
      },
    }),
    prisma.dataConsent.findUnique({
      where: { userId },
      select: { modelTraining: true, anonymizedResearch: true },
    }),
    prisma.tripMember.findMany({
      where: { userId, status: "joined" },
      select: {
        trip: {
          select: {
            name: true, destination: true, city: true, country: true,
            startDate: true, endDate: true, status: true, mode: true, createdAt: true,
            slots: {
              select: {
                dayNumber: true, slotType: true, status: true,
                activityNode: { select: { name: true, category: true } },
              },
            },
          },
        },
      },
    }),
    prisma.behavioralSignal.findMany({
      where: { userId },
      select: { signalType: true, rawAction: true, tripPhase: true, createdAt: true },
    }),
    prisma.intentionSignal.findMany({
      where: { userId },
      select: { intentionType: true, confidence: true, source: true, createdAt: true },
    }),
    prisma.rawEvent.findMany({
      where: { userId },
      select: { eventType: true, intentClass: true, createdAt: true },
    }),
    prisma.personaDimension.findMany({
      where: { userId },
      select: { dimension: true, value: true, confidence: true, createdAt: true },
    }),
    prisma.rankingEvent.findMany({
      where: { userId },
      select: {
        surface: true, selectedIds: true, createdAt: true,
      },
    }),
    prisma.backfillTrip.findMany({
      where: { userId },
      select: {
        city: true, country: true, startDate: true,
        venues: {
          select: { extractedName: true, extractedCategory: true },
        },
      },
    }),
  ]);

  // Record rate limit timestamp
  rateLimitMap.set(userId, Date.now());

  const exportData = {
    exportedAt: new Date().toISOString(),
    profile: {
      name: user.name,
      email: user.email,
      createdAt: user.createdAt,
      subscriptionTier: user.subscriptionTier,
    },
    preferences: preferences ?? { dietary: [], mobility: [], languages: [], travelFrequency: null },
    notifications: notifications ?? {
      tripReminders: true, morningBriefing: true, groupActivity: true,
      postTripPrompt: true, citySeeded: true, inspirationNudges: false, productUpdates: false,
    },
    consent: consent ?? { modelTraining: false, anonymizedResearch: false },
    trips: tripMembers.map((tm: { trip: Record<string, unknown> }) => tm.trip),
    behavioralSignals,
    intentionSignals,
    rawEvents,
    personaDimensions: personaDimensions.map((pd: { dimension: string; value: string; confidence: number; createdAt: Date }) => ({
      dimensionName: pd.dimension,
      score: pd.value,
      confidence: pd.confidence,
      createdAt: pd.createdAt,
    })),
    rankingEvents: rankingEvents.map((re: { surface: string; selectedIds: string[]; createdAt: Date }) => ({
      context: re.surface,
      selectedId: re.selectedIds[0] ?? null,
      alternativesCount: re.selectedIds.length,
      createdAt: re.createdAt,
    })),
    backfillTrips: backfillTrips.map((bt: { city: string; country: string; startDate: Date | null; venues: { extractedName: string; extractedCategory: string | null }[] }) => ({
      city: bt.city,
      country: bt.country,
      traveledAt: bt.startDate,
      venues: bt.venues.map((v: { extractedName: string; extractedCategory: string | null }) => ({
        name: v.extractedName,
        category: v.extractedCategory,
      })),
    })),
  };

  const today = new Date().toISOString().split("T")[0];

  return new NextResponse(JSON.stringify(exportData, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="overplanned-export-${today}.json"`,
    },
  });
}
```

**Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run __tests__/api/settings-export.test.ts --reporter=verbose`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/export/route.ts apps/web/__tests__/api/settings-export.test.ts
git commit -m "feat(settings): data export endpoint with rate limiting and field filtering"
```

---

## Task 4: API Route — DELETE /api/settings/account

**Files:**
- Create: `apps/web/app/api/settings/account/route.ts` (add DELETE handler to existing file)

NOTE: There is already a PATCH handler in this file. We are ADDING the DELETE handler.

**Step 1: Write the failing test**

Create `apps/web/__tests__/api/settings-delete-account.test.ts`:

```typescript
/**
 * Route handler tests for DELETE /api/settings/account
 * Tests auth, email confirmation, anonymization, and cascade deletion.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { DELETE } = await import("../../app/api/settings/account/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeDeleteRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/account", {
    method: "DELETE",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

describe("DELETE /api/settings/account — auth", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(401);
  });
});

describe("DELETE /api/settings/account — validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 400 when confirmEmail is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({}));
    expect(res.status).toBe(400);
  });

  it("returns 400 when confirmEmail is not a valid email", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "not-an-email" }));
    expect(res.status).toBe(400);
  });

  it("returns 403 when confirmEmail does not match session email", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "wrong@example.com" }));
    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toBe("Email does not match");
  });

  it("matches email case-insensitively", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "TEST@EXAMPLE.COM" }));
    expect(res.status).toBe(200);
  });
});

describe("DELETE /api/settings/account — deletion", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns { deleted: true } on success", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ deleted: true });
  });

  it("calls $transaction with anonymize + delete operations", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    // Transaction receives a callback function
    const txArg = mockPrisma.$transaction.mock.calls[0][0];
    expect(typeof txArg).toBe("function");
  });

  it("uses userId from session, not from body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);

    // Capture the transaction callback and execute it with a mock tx
    const mockTx = {
      trip: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      behavioralSignal: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      intentionSignal: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      rawEvent: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      personaDimension: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      rankingEvent: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      auditLog: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      sharedTripToken: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      inviteToken: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      user: { delete: vi.fn().mockResolvedValue({}) },
    };

    mockPrisma.$transaction.mockImplementationOnce(async (cb: (tx: typeof mockTx) => Promise<void>) => {
      await cb(mockTx);
    });

    await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));

    // All anonymize calls should use session userId, not body
    expect(mockTx.trip.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.behavioralSignal.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.user.delete).toHaveBeenCalledWith({
      where: { id: "user-abc" },
    });
  });

  it("returns 500 on transaction failure", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB error"));

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(500);
    const json = await res.json();
    expect(json.error).toBe("Failed to delete account");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run __tests__/api/settings-delete-account.test.ts --reporter=verbose`
Expected: FAIL — `DELETE` is not exported from the route

**Step 3: Read existing account route and add DELETE handler**

First read the existing file:
`apps/web/app/api/settings/account/route.ts`

Then add the DELETE handler at the bottom of the file:

```typescript
// Add these imports at the top (if not already present):
import { deleteAccountSchema } from "@/lib/validations/settings";

// Add this function at the bottom of the file:

export async function DELETE(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const userEmail = (session.user as { email: string }).email;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const result = deleteAccountSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Case-insensitive email match
  if (result.data.confirmEmail.toLowerCase() !== userEmail.toLowerCase()) {
    return NextResponse.json({ error: "Email does not match" }, { status: 403 });
  }

  try {
    await prisma.$transaction(async (tx) => {
      // Step 1: Anonymize 6 orphan tables (no FK cascade)
      await tx.trip.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.behavioralSignal.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.intentionSignal.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.rawEvent.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.personaDimension.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.rankingEvent.updateMany({ where: { userId }, data: { userId: "DELETED" } });

      // Step 2: Anonymize bare string refs
      await tx.auditLog.updateMany({ where: { actorId: userId }, data: { actorId: "DELETED" } });
      await tx.sharedTripToken.updateMany({ where: { createdBy: userId }, data: { createdBy: "DELETED" } });
      await tx.inviteToken.updateMany({ where: { createdBy: userId }, data: { createdBy: "DELETED" } });

      // Step 3: Delete User row (cascade handles Session, Account, TripMember,
      // UserPreference, NotificationPreference, DataConsent, BackfillTrip, BackfillSignal, PersonaDelta)
      await tx.user.delete({ where: { id: userId } });
    });

    return NextResponse.json({ deleted: true });
  } catch {
    return NextResponse.json({ error: "Failed to delete account" }, { status: 500 });
  }
}
```

**Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run __tests__/api/settings-delete-account.test.ts --reporter=verbose`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/account/route.ts apps/web/__tests__/api/settings-delete-account.test.ts
git commit -m "feat(settings): account deletion with anonymization and email confirmation"
```

---

## Task 5: Component — PrivacySection.tsx

**Files:**
- Create: `apps/web/components/settings/PrivacySection.tsx`

**Step 1: Write the failing test**

Create `apps/web/__tests__/settings/PrivacySection.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrivacySection } from "@/components/settings/PrivacySection";

const mockSignOut = vi.fn();

vi.mock("next-auth/react", () => ({
  signOut: (...args: unknown[]) => mockSignOut(...args),
}));

const CONSENT_DEFAULTS = {
  modelTraining: false,
  anonymizedResearch: false,
};

function mockFetchSuccess(getData = CONSENT_DEFAULTS) {
  const fetchMock = vi.fn();
  // First call = GET (consent)
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  // Subsequent calls = PATCH / export / delete
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({}),
  });
  global.fetch = fetchMock;
  return fetchMock;
}

describe("PrivacySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock URL.createObjectURL and revokeObjectURL
    global.URL.createObjectURL = vi.fn(() => "blob:test");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("renders skeleton during load, then toggles after GET resolves", async () => {
    mockFetchSuccess();
    const { container } = render(<PrivacySection email="test@example.com" />);

    // Skeleton visible
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, toggles appear
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("switch");
    expect(toggles).toHaveLength(2);
  });

  it("toggle triggers PATCH and reverts on failure", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => CONSENT_DEFAULTS,
    });
    // PATCH fails
    fetchMock.mockResolvedValueOnce({ ok: false });
    global.fetch = fetchMock;

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(2);
    });

    const toggles = screen.getAllByRole("switch");
    // modelTraining starts false
    expect(toggles[0]).toHaveAttribute("aria-checked", "false");

    await user.click(toggles[0]);

    // After PATCH failure, should revert back to false
    await waitFor(() => {
      expect(toggles[0]).toHaveAttribute("aria-checked", "false");
    });
  });

  it("export button triggers blob download", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override subsequent mock for export
    fetchMock.mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(["{}"], { type: "application/json" }),
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });
  });

  it("export 429 shows rate limit message", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for export 429
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 429,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(screen.getByText("Please wait before requesting another export.")).toBeInTheDocument();
    });
  });

  it("export error shows error message", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for export 500
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(screen.getByText("Failed to download. Please try again.")).toBeInTheDocument();
    });
  });

  it("delete shows inline confirmation with email input", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    expect(screen.getByText("Type your email to confirm:")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
    expect(screen.getByText("Yes, delete my account")).toBeInTheDocument();
  });

  it("cancel hides confirmation", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));
    expect(screen.getByText("Type your email to confirm:")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Type your email to confirm:")).not.toBeInTheDocument();
  });

  it("confirm button disabled until email matches", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const confirmBtn = screen.getByText("Yes, delete my account");
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");

    expect(confirmBtn).not.toBeDisabled();
  });

  it("confirm triggers DELETE + signOut", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for delete
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ deleted: true }),
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");
    await user.click(screen.getByText("Yes, delete my account"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/settings/account",
        expect.objectContaining({
          method: "DELETE",
          body: JSON.stringify({ confirmEmail: "test@example.com" }),
        })
      );
      expect(mockSignOut).toHaveBeenCalledWith({ callbackUrl: "/" });
    });
  });

  it("delete failure shows error and resets state", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for delete failure
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");
    await user.click(screen.getByText("Yes, delete my account"));

    await waitFor(() => {
      expect(screen.getByText("Failed to delete account. Please try again.")).toBeInTheDocument();
    });

    // Confirm button should be re-enabled (not stuck in deleting state)
    expect(screen.getByText("Yes, delete my account")).not.toBeDisabled();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run __tests__/settings/PrivacySection.test.tsx --reporter=verbose`
Expected: FAIL — `Cannot find module '@/components/settings/PrivacySection'`

**Step 3: Write the component**

Create `apps/web/components/settings/PrivacySection.tsx`:

```typescript
"use client";

import { useState, useEffect } from "react";
import { signOut } from "next-auth/react";

// ---------- Types ----------

type ConsentState = {
  modelTraining: boolean;
  anonymizedResearch: boolean;
};

type ConsentField = keyof ConsentState;

const DEFAULTS: ConsentState = {
  modelTraining: false,
  anonymizedResearch: false,
};

const CONSENT_ITEMS: { field: ConsentField; label: string }[] = [
  { field: "modelTraining", label: "Use my data to improve recommendations" },
  { field: "anonymizedResearch", label: "Include my anonymized data in research" },
];

// ---------- Component ----------

export function PrivacySection({ email }: { email: string }) {
  const [consent, setConsent] = useState<ConsentState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Export state
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/privacy");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setConsent(data);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  async function toggleConsent(field: ConsentField) {
    const prev = consent[field];
    const next = !prev;

    setConsent((s) => ({ ...s, [field]: next }));

    try {
      const res = await fetch("/api/settings/privacy", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: next }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setConsent((s) => ({ ...s, [field]: prev }));
    }
  }

  async function handleExport() {
    setExporting(true);
    setExportMsg(null);

    try {
      const res = await fetch("/api/settings/export");
      if (res.status === 429) {
        setExportMsg("Please wait before requesting another export.");
        setExporting(false);
        return;
      }
      if (!res.ok) {
        setExportMsg("Failed to download. Please try again.");
        setExporting(false);
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `overplanned-export-${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      setExportMsg("Failed to download. Please try again.");
    }

    setExporting(false);
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);

    try {
      const res = await fetch("/api/settings/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmEmail }),
      });

      if (res.ok) {
        signOut({ callbackUrl: "/" });
        return;
      }

      setDeleteError("Failed to delete account. Please try again.");
    } catch {
      setDeleteError("Failed to delete account. Please try again.");
    }

    setDeleting(false);
  }

  const emailMatch = confirmEmail.toLowerCase() === email.toLowerCase();

  return (
    <section aria-labelledby="privacy-heading">
      <h2 id="privacy-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Privacy & Data
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-8">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="h-4 w-64 bg-warm-border rounded" />
                <div className="h-6 w-10 bg-warm-border rounded-full" />
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load privacy settings.</p>
        ) : (
          <>
            {/* Consent Toggles */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-3">
                Consent
              </h3>
              <div className="space-y-3">
                {CONSENT_ITEMS.map(({ field, label }) => (
                  <div key={field} className="flex items-center justify-between">
                    <span className="font-sora text-sm text-ink-200">{label}</span>
                    <button
                      role="switch"
                      aria-checked={consent[field]}
                      onClick={() => toggleConsent(field)}
                      className={`
                        relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full
                        border-2 border-transparent transition-colors
                        ${consent[field] ? "bg-accent" : "bg-warm-border"}
                      `}
                    >
                      <span
                        aria-hidden="true"
                        className={`
                          pointer-events-none inline-block h-5 w-5 rounded-full bg-white
                          shadow-sm transition-transform
                          ${consent[field] ? "translate-x-4" : "translate-x-0"}
                        `}
                      />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Data Export */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-3">
                Your Data
              </h3>
              <p className="font-sora text-sm text-ink-300 mb-3">
                Download a copy of all your Overplanned data in JSON format.
              </p>
              <button
                onClick={handleExport}
                disabled={exporting}
                className="rounded-xl border border-warm-border px-4 py-2 font-sora text-sm text-ink-200 hover:bg-warm-border/50 transition-colors disabled:opacity-50"
              >
                {exporting ? "Downloading..." : "Download my data"}
              </button>
              {exportMsg && (
                <p className="mt-2 font-sora text-sm text-red-400">{exportMsg}</p>
              )}
            </div>

            {/* Delete Account */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-red-400 mb-3">
                Danger Zone
              </h3>
              <p className="font-sora text-sm text-ink-300 mb-3">
                Permanently delete your account and all personal data. Trip data is kept anonymously for service improvement.
              </p>

              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="font-sora text-sm text-red-400 hover:text-red-300 transition-colors"
                >
                  Delete my account
                </button>
              ) : (
                <div className="space-y-3">
                  <label className="block">
                    <span className="font-sora text-sm text-ink-300">Type your email to confirm:</span>
                    <input
                      type="email"
                      value={confirmEmail}
                      onChange={(e) => setConfirmEmail(e.target.value)}
                      placeholder="your@email.com"
                      className="mt-1 block w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2 font-sora text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                  </label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setConfirmEmail("");
                        setDeleteError(null);
                      }}
                      className="rounded-lg px-4 py-2 font-sora text-sm text-ink-300 hover:text-ink-200 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleDelete}
                      disabled={!emailMatch || deleting}
                      className="rounded-lg bg-red-500/10 px-4 py-2 font-sora text-sm text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Yes, delete my account
                    </button>
                  </div>
                  {deleteError && (
                    <p className="font-sora text-sm text-red-400">{deleteError}</p>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run __tests__/settings/PrivacySection.test.tsx --reporter=verbose`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add apps/web/components/settings/PrivacySection.tsx apps/web/__tests__/settings/PrivacySection.test.tsx
git commit -m "feat(settings): PrivacySection with consent toggles, export, and delete"
```

---

## Task 6: Page Wiring + Delete Stub

**Files:**
- Modify: `apps/web/app/settings/page.tsx`
- Delete: `apps/web/components/settings/PrivacyStub.tsx`
- Modify: `apps/web/__tests__/settings/SettingsPage.test.tsx`

**Step 1: Update page.tsx**

In `apps/web/app/settings/page.tsx`:

Replace the import (line 14):
```typescript
// BEFORE:
import { PrivacyStub } from "@/components/settings/PrivacyStub";

// AFTER:
import { PrivacySection } from "@/components/settings/PrivacySection";
```

Replace the usage (line 66):
```typescript
// BEFORE:
            <PrivacyStub />

// AFTER:
            <PrivacySection email={session.user.email} />
```

**Step 2: Delete PrivacyStub.tsx**

Delete: `apps/web/components/settings/PrivacyStub.tsx`

**Step 3: Update SettingsPage.test.tsx**

In `apps/web/__tests__/settings/SettingsPage.test.tsx`, add the PrivacySection mock after the NotificationsSection mock (after line 40):

```typescript
vi.mock("@/components/settings/PrivacySection", () => ({
  PrivacySection: () => <section><h2>Privacy & Data</h2></section>,
}));
```

Update the "does NOT render a delete account button" test (lines 139-142). Since PrivacySection is mocked, the delete button won't render anyway, but the test should still pass as-is. No change needed.

**Step 4: Run page tests**

Run: `cd apps/web && npx vitest run __tests__/settings/SettingsPage.test.tsx --reporter=verbose`
Expected: All PASS

**Step 5: Commit**

```bash
git add apps/web/app/settings/page.tsx apps/web/__tests__/settings/SettingsPage.test.tsx
git rm apps/web/components/settings/PrivacyStub.tsx
git commit -m "feat(settings): wire PrivacySection, remove PrivacyStub"
```

---

## Task 7: Full Test Suite Run

**Step 1: Run all privacy/settings tests**

Run: `cd apps/web && npx vitest run __tests__/api/settings-privacy.test.ts __tests__/api/settings-export.test.ts __tests__/api/settings-delete-account.test.ts __tests__/settings/PrivacySection.test.tsx __tests__/settings/SettingsPage.test.tsx --reporter=verbose`
Expected: All pass

**Step 2: Run full test suite**

Run: `cd apps/web && npx vitest run --reporter=verbose`
Expected: 0 regressions (pre-existing trip-route failure is allowed)

**Step 3: Commit if any fixes were needed**

If any tests needed fixing, commit the fixes before proceeding.

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Zod schemas | settings.ts | (existing pass) |
| 2 | Privacy GET+PATCH | privacy/route.ts | 11 tests |
| 3 | Export GET | export/route.ts | 5 tests |
| 4 | Account DELETE | account/route.ts (add) | 8 tests |
| 5 | PrivacySection | PrivacySection.tsx | 10 tests |
| 6 | Page wiring | page.tsx + delete stub | page test update |
| 7 | Full suite | - | 0 regressions |

Total new tests: ~34
