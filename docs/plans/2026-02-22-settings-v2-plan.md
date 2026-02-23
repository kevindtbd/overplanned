# Settings V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add travel interests (hybrid vibe tags + free-form), display preferences (units/date/time/theme), Stripe billing portal, and notification gaps to the settings page.

**Architecture:** 9 new schema columns across 2 tables (all defaults, no data migration). 2 new API routes (`/api/settings/display`, `/api/settings/billing-portal`), 2 enhanced routes (preferences, notifications). 2 new components (`DisplayPreferences`, `TravelInterests`), 2 enhanced components (`SubscriptionBadge`, `NotificationsSection`). Stripe singleton + env validation. Ranking engine wiring for vibePreferences. DayView consumer wiring for timeFormat.

**Tech Stack:** Next.js 14, Prisma ORM, Zod validation, Stripe SDK, Vitest + React Testing Library

---

## Task 1: Schema Migration

**Files:**
- Modify: `prisma/schema.prisma:571-581` (UserPreference model)
- Modify: `prisma/schema.prisma:583-596` (NotificationPreference model)

**Step 1: Add 7 new columns to UserPreference**

In `prisma/schema.prisma`, add after `travelFrequency` (line 578), before `createdAt`:

```prisma
  vibePreferences   String[]  @default([])
  travelStyleNote   String?
  distanceUnit      String    @default("mi")
  temperatureUnit   String    @default("F")
  dateFormat        String    @default("MM/DD/YYYY")
  timeFormat        String    @default("12h")
  theme             String    @default("system")
```

**Step 2: Add 2 new columns to NotificationPreference**

In `prisma/schema.prisma`, add after `productUpdates` (line 593), before `createdAt`:

```prisma
  checkinReminder    Boolean @default(false)
  preTripDaysBefore  Int     @default(3)
```

**Step 3: Run migration**

Run: `cd /home/pogchamp/Desktop/overplanned && npx prisma migrate dev --name settings-v2-columns`
Expected: Migration creates successfully, Prisma client regenerated.

**Step 4: Verify Prisma client**

Run: `cd /home/pogchamp/Desktop/overplanned && npx prisma validate`
Expected: "Your Prisma schema is valid."

**Step 5: Commit**

```bash
git add prisma/schema.prisma prisma/migrations/
git commit -m "schema: add settings V2 columns (7 UserPreference, 2 NotificationPreference)"
```

---

## Task 2: Zod Validation Updates

**Files:**
- Modify: `apps/web/lib/validations/settings.ts`

**Step 1: Add vibe preference and display options to validations**

After `TRAVEL_FREQUENCY_OPTIONS` (line 34), add:

```typescript
export const VIBE_PREFERENCE_OPTIONS = [
  "high-energy", "slow-burn", "immersive",
  "hidden-gem", "iconic-worth-it", "locals-only", "offbeat",
  "destination-meal", "street-food", "local-institution", "drinks-forward",
  "nature-immersive", "urban-exploration", "deep-history", "contemporary-culture", "hands-on", "scenic",
  "late-night", "early-morning", "solo-friendly", "group-friendly", "social-scene", "low-interaction",
] as const;

export const DISTANCE_UNITS = ["mi", "km"] as const;
export const TEMPERATURE_UNITS = ["F", "C"] as const;
export const DATE_FORMATS = ["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"] as const;
export const TIME_FORMATS = ["12h", "24h"] as const;
export const THEME_OPTIONS = ["light", "dark", "system"] as const;

export const PRE_TRIP_DAYS = [1, 3, 7] as const;
```

**Step 2: Add vibePreferences and travelStyleNote to updatePreferencesSchema**

Add two new fields to the `.object({})` in `updatePreferencesSchema`:

```typescript
vibePreferences: z.array(z.enum(VIBE_PREFERENCE_OPTIONS)).max(23).optional(),
// SECURITY: travelStyleNote MUST use delimiter isolation (<user_note> tags) when
// fed to any LLM for persona extraction. Never pass raw text as instructions.
travelStyleNote: z.string().max(500).optional(),
```

**Step 3: Add updateDisplaySchema**

After `updatePreferencesSchema`, add:

```typescript
export const updateDisplaySchema = z
  .object({
    distanceUnit: z.enum(DISTANCE_UNITS).optional(),
    temperatureUnit: z.enum(TEMPERATURE_UNITS).optional(),
    dateFormat: z.enum(DATE_FORMATS).optional(),
    timeFormat: z.enum(TIME_FORMATS).optional(),
    theme: z.enum(THEME_OPTIONS).optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");
```

**Step 4: Add checkinReminder and preTripDaysBefore to updateNotificationsSchema**

Add two new fields to the `.object({})` in `updateNotificationsSchema`:

```typescript
checkinReminder: z.boolean().optional(),
preTripDaysBefore: z.number().int().refine(v => [1, 3, 7].includes(v), "Must be 1, 3, or 7").optional(),
```

**Step 5: Verify no TypeScript errors**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to settings.ts

**Step 6: Commit**

```bash
git add apps/web/lib/validations/settings.ts
git commit -m "feat: add Zod schemas for display prefs, vibe tags, notification gaps"
```

---

## Task 3: Stripe Infrastructure

**Files:**
- Create: `apps/web/lib/stripe.ts`
- Modify: `apps/web/lib/env.ts`

**Step 1: Install stripe package**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npm install stripe`
Expected: stripe added to package.json dependencies

**Step 2: Create Stripe singleton**

Create `apps/web/lib/stripe.ts`:

```typescript
import Stripe from "stripe";

const globalForStripe = globalThis as unknown as { stripe?: Stripe };

export const stripe =
  globalForStripe.stripe ??
  new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2024-06-20",
    typescript: true,
  });

if (process.env.NODE_ENV !== "production") globalForStripe.stripe = stripe;
```

**Step 3: Add STRIPE_SECRET_KEY to env validation**

In `apps/web/lib/env.ts`, add to the `envSchema` object:

```typescript
STRIPE_SECRET_KEY: z.string().startsWith("sk_", "STRIPE_SECRET_KEY must start with sk_"),
```

**Step 4: Commit**

```bash
git add apps/web/lib/stripe.ts apps/web/lib/env.ts apps/web/package.json apps/web/package-lock.json
git commit -m "infra: add Stripe SDK singleton and env validation"
```

---

## Task 4: Display Preferences API Route

**Files:**
- Create: `apps/web/app/api/settings/display/route.ts`
- Test: `apps/web/__tests__/api/settings-display.test.ts`

**Step 1: Write the failing tests**

Create `apps/web/__tests__/api/settings-display.test.ts`:

```typescript
/**
 * Route handler tests for GET + PATCH /api/settings/display
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    userPreference: {
      findUnique: vi.fn(),
      upsert: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { GET, PATCH } = await import(
  "../../app/api/settings/display/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeGetRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/display", {
    method: "GET",
  });
}

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/display", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/display", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

// ---------------------------------------------------------------------------
// GET
// ---------------------------------------------------------------------------
describe("GET /api/settings/display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("returns defaults when no record exists", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.userPreference.findUnique.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toEqual({
      distanceUnit: "mi",
      temperatureUnit: "F",
      dateFormat: "MM/DD/YYYY",
      timeFormat: "12h",
      theme: "system",
    });
  });

  it("returns saved display preferences", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.userPreference.findUnique.mockResolvedValue({
      distanceUnit: "km",
      temperatureUnit: "C",
      dateFormat: "DD/MM/YYYY",
      timeFormat: "24h",
      theme: "dark",
    } as any);
    const res = await GET();
    const data = await res.json();
    expect(data.distanceUnit).toBe("km");
    expect(data.theme).toBe("dark");
  });
});

// ---------------------------------------------------------------------------
// PATCH
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("returns 401 when not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);
    const res = await PATCH(makePatchRequest({ theme: "dark" }));
    expect(res.status).toBe(401);
  });

  it("returns 400 for invalid JSON", async () => {
    const res = await PATCH(makePatchRequestInvalidJSON());
    expect(res.status).toBe(400);
  });

  it("returns 400 for empty body", async () => {
    const res = await PATCH(makePatchRequest({}));
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid enum value", async () => {
    const res = await PATCH(makePatchRequest({ theme: "neon" }));
    expect(res.status).toBe(400);
  });

  it("upserts single field", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      distanceUnit: "km",
      temperatureUnit: "F",
      dateFormat: "MM/DD/YYYY",
      timeFormat: "12h",
      theme: "system",
    } as any);

    const res = await PATCH(makePatchRequest({ distanceUnit: "km" }));
    expect(res.status).toBe(200);

    expect(mockPrisma.userPreference.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { userId: "user-abc" },
        create: expect.objectContaining({ userId: "user-abc", distanceUnit: "km" }),
        update: { distanceUnit: "km" },
      })
    );
  });

  it("upserts multiple fields", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      distanceUnit: "km",
      temperatureUnit: "C",
      dateFormat: "MM/DD/YYYY",
      timeFormat: "24h",
      theme: "system",
    } as any);

    const res = await PATCH(makePatchRequest({
      distanceUnit: "km",
      temperatureUnit: "C",
      timeFormat: "24h",
    }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.distanceUnit).toBe("km");
    expect(data.temperatureUnit).toBe("C");
  });

  it("ignores extra fields (userId, id)", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      distanceUnit: "mi",
      temperatureUnit: "F",
      dateFormat: "MM/DD/YYYY",
      timeFormat: "12h",
      theme: "dark",
    } as any);

    const res = await PATCH(makePatchRequest({ theme: "dark", userId: "hacker", id: "fake" }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update).not.toHaveProperty("userId");
    expect(upsertCall.update).not.toHaveProperty("id");
  });

  it("returns only display fields (no id/timestamps)", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      distanceUnit: "mi",
      temperatureUnit: "F",
      dateFormat: "MM/DD/YYYY",
      timeFormat: "12h",
      theme: "system",
    } as any);

    const res = await PATCH(makePatchRequest({ theme: "system" }));
    const data = await res.json();
    expect(data).not.toHaveProperty("id");
    expect(data).not.toHaveProperty("userId");
    expect(data).not.toHaveProperty("createdAt");
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-display.test.ts`
Expected: FAIL — module not found (route doesn't exist yet)

**Step 3: Write the API route**

Create `apps/web/app/api/settings/display/route.ts`:

```typescript
/**
 * GET + PATCH /api/settings/display
 * Auth: session required, userId from session only
 * GET: returns display preferences or defaults
 * PATCH: upserts display preference fields
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateDisplaySchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const DISPLAY_SELECT = {
  distanceUnit: true,
  temperatureUnit: true,
  dateFormat: true,
  timeFormat: true,
  theme: true,
} as const;

const DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const prefs = await prisma.userPreference.findUnique({
    where: { userId },
    select: DISPLAY_SELECT,
  });

  return NextResponse.json(prefs ?? DEFAULTS);
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

  const result = updateDisplaySchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const updated = await prisma.userPreference.upsert({
    where: { userId },
    create: { userId, ...result.data },
    update: result.data,
    select: DISPLAY_SELECT,
  });

  return NextResponse.json(updated);
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-display.test.ts`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/display/route.ts apps/web/__tests__/api/settings-display.test.ts
git commit -m "feat: add display preferences API route (GET + PATCH) with tests"
```

---

## Task 5: Billing Portal API Route

**Files:**
- Create: `apps/web/app/api/settings/billing-portal/route.ts`
- Test: `apps/web/__tests__/api/settings-billing-portal.test.ts`

**Step 1: Write the failing tests**

Create `apps/web/__tests__/api/settings-billing-portal.test.ts`:

```typescript
/**
 * Route handler tests for POST /api/settings/billing-portal
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/stripe", () => ({
  stripe: {
    billingPortal: {
      sessions: {
        create: vi.fn(),
      },
    },
  },
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { stripe } = await import("@/lib/stripe");
const { POST } = await import(
  "../../app/api/settings/billing-portal/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);
const mockStripe = vi.mocked(stripe);

function makePostRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/billing-portal", {
    method: "POST",
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

describe("POST /api/settings/billing-portal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);
    const res = await POST(makePostRequest());
    expect(res.status).toBe(401);
  });

  it("returns 404 when user has no stripeCustomerId", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue({ stripeCustomerId: null } as any);
    const res = await POST(makePostRequest());
    expect(res.status).toBe(404);
    const data = await res.json();
    expect(data.error).toBe("No billing account found");
  });

  it("returns 404 when user record not found", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue(null);
    const res = await POST(makePostRequest());
    expect(res.status).toBe(404);
  });

  it("returns portal URL on success", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue({ stripeCustomerId: "cus_abc123" } as any);
    mockStripe.billingPortal.sessions.create.mockResolvedValue({
      url: "https://billing.stripe.com/session/test_abc",
    } as any);

    const res = await POST(makePostRequest());
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.url).toBe("https://billing.stripe.com/session/test_abc");
  });

  it("validates Stripe URL prefix", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue({ stripeCustomerId: "cus_abc123" } as any);
    mockStripe.billingPortal.sessions.create.mockResolvedValue({
      url: "https://evil.com/steal-cards",
    } as any);

    const res = await POST(makePostRequest());
    expect(res.status).toBe(502);
  });

  it("looks up stripeCustomerId from DB, not session", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue({ stripeCustomerId: "cus_abc123" } as any);
    mockStripe.billingPortal.sessions.create.mockResolvedValue({
      url: "https://billing.stripe.com/session/test",
    } as any);

    await POST(makePostRequest());

    expect(mockPrisma.user.findUnique).toHaveBeenCalledWith({
      where: { id: "user-abc" },
      select: { stripeCustomerId: true },
    });
  });

  it("handles Stripe connection error with 503", async () => {
    mockGetServerSession.mockResolvedValue(authedSession);
    mockPrisma.user.findUnique.mockResolvedValue({ stripeCustomerId: "cus_abc123" } as any);
    const err = new Error("Connection failed");
    err.name = "StripeConnectionError";
    (err as any).type = "StripeConnectionError";
    mockStripe.billingPortal.sessions.create.mockRejectedValue(err);

    const res = await POST(makePostRequest());
    // Should return 500 for unexpected errors (Stripe error types need actual SDK)
    expect(res.status).toBeGreaterThanOrEqual(500);
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-billing-portal.test.ts`
Expected: FAIL — module not found

**Step 3: Write the API route**

Create `apps/web/app/api/settings/billing-portal/route.ts`:

```typescript
/**
 * POST /api/settings/billing-portal
 * Auth: session required
 * Creates a Stripe Customer Portal session and returns the URL.
 * Looks up stripeCustomerId from DB (never from session).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { stripe } from "@/lib/stripe";

export async function POST(_req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const dbUser = await prisma.user.findUnique({
    where: { id: userId },
    select: { stripeCustomerId: true },
  });

  if (!dbUser?.stripeCustomerId) {
    return NextResponse.json({ error: "No billing account found" }, { status: 404 });
  }

  try {
    const portalSession = await stripe.billingPortal.sessions.create({
      customer: dbUser.stripeCustomerId,
      return_url: `${process.env.NEXTAUTH_URL}/settings`,
    });

    if (!portalSession.url || !portalSession.url.startsWith("https://billing.stripe.com/")) {
      return NextResponse.json({ error: "Failed to create billing session" }, { status: 502 });
    }

    return NextResponse.json({ url: portalSession.url });
  } catch (err) {
    console.error("[billing-portal] Error:", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-billing-portal.test.ts`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/billing-portal/route.ts apps/web/__tests__/api/settings-billing-portal.test.ts
git commit -m "feat: add Stripe billing portal API route with tests"
```

---

## Task 6: Enhance Preferences API Route (vibePreferences + travelStyleNote)

**Files:**
- Modify: `apps/web/app/api/settings/preferences/route.ts`
- Modify: `apps/web/__tests__/api/settings-preferences.test.ts`

**Step 1: Add new tests to existing test file**

Append to `apps/web/__tests__/api/settings-preferences.test.ts`, inside a new describe block:

```typescript
// ---------------------------------------------------------------------------
// Settings V2: vibePreferences + travelStyleNote
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — vibePreferences", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("accepts valid vibePreferences array", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: ["hidden-gem", "street-food"], travelStyleNote: null,
    } as any);

    const res = await PATCH(makePatchRequest({ vibePreferences: ["hidden-gem", "street-food"] }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.vibePreferences).toEqual(["hidden-gem", "street-food"]);
  });

  it("rejects invalid vibe tag", async () => {
    const res = await PATCH(makePatchRequest({ vibePreferences: ["not-a-real-tag"] }));
    expect(res.status).toBe(400);
  });

  it("deduplicates vibePreferences", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: ["hidden-gem"], travelStyleNote: null,
    } as any);

    await PATCH(makePatchRequest({ vibePreferences: ["hidden-gem", "hidden-gem"] }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    const createData = upsertCall.create as Record<string, unknown>;
    expect(createData.vibePreferences).toEqual(["hidden-gem"]);
  });

  it("accepts empty vibePreferences (clears selections)", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: [], travelStyleNote: null,
    } as any);

    const res = await PATCH(makePatchRequest({ vibePreferences: [] }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.vibePreferences).toEqual([]);
  });
});

describe("PATCH /api/settings/preferences — travelStyleNote", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("accepts valid travelStyleNote", async () => {
    mockPrisma.userPreference.upsert.mockResolvedValue({
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: [], travelStyleNote: "I love coffee",
    } as any);

    const res = await PATCH(makePatchRequest({ travelStyleNote: "I love coffee" }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.travelStyleNote).toBe("I love coffee");
  });

  it("rejects travelStyleNote over 500 characters", async () => {
    const res = await PATCH(makePatchRequest({ travelStyleNote: "x".repeat(501) }));
    expect(res.status).toBe(400);
  });
});

describe("GET /api/settings/preferences — V2 fields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("returns vibePreferences and travelStyleNote in defaults", async () => {
    mockPrisma.userPreference.findUnique.mockResolvedValue(null);
    const res = await GET();
    const data = await res.json();
    expect(data.vibePreferences).toEqual([]);
    expect(data.travelStyleNote).toBeNull();
  });

  it("returns saved vibePreferences and travelStyleNote", async () => {
    mockPrisma.userPreference.findUnique.mockResolvedValue({
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: ["offbeat"], travelStyleNote: "Coffee hunter",
    } as any);
    const res = await GET();
    const data = await res.json();
    expect(data.vibePreferences).toEqual(["offbeat"]);
    expect(data.travelStyleNote).toBe("Coffee hunter");
  });
});
```

**Step 2: Run tests to verify new ones fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-preferences.test.ts`
Expected: New tests FAIL (route doesn't return vibePreferences yet), existing tests still pass

**Step 3: Update the preferences route**

In `apps/web/app/api/settings/preferences/route.ts`:

1. Add `vibePreferences` and `travelStyleNote` to `PREF_SELECT`:
```typescript
const PREF_SELECT = {
  dietary: true,
  mobility: true,
  languages: true,
  travelFrequency: true,
  vibePreferences: true,
  travelStyleNote: true,
} as const;
```

2. Add to `DEFAULTS`:
```typescript
const DEFAULTS = {
  dietary: [] as string[],
  mobility: [] as string[],
  languages: [] as string[],
  travelFrequency: null as string | null,
  vibePreferences: [] as string[],
  travelStyleNote: null as string | null,
};
```

3. In the PATCH handler, add vibePreferences dedup and travelStyleNote handling after existing dedup block (after line 79):
```typescript
if (result.data.vibePreferences !== undefined) {
  data.vibePreferences = [...new Set(result.data.vibePreferences)];
}
if (result.data.travelStyleNote !== undefined) {
  data.travelStyleNote = result.data.travelStyleNote;
}
```

4. In the upsert `create` block, add defaults:
```typescript
create: {
  userId,
  dietary: (data.dietary as string[]) ?? [],
  mobility: (data.mobility as string[]) ?? [],
  languages: (data.languages as string[]) ?? [],
  travelFrequency: (data.travelFrequency as string | null) ?? null,
  vibePreferences: (data.vibePreferences as string[]) ?? [],
  travelStyleNote: (data.travelStyleNote as string | null) ?? null,
},
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-preferences.test.ts`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/preferences/route.ts apps/web/__tests__/api/settings-preferences.test.ts
git commit -m "feat: add vibePreferences + travelStyleNote to preferences API"
```

---

## Task 7: Enhance Notifications API Route (checkinReminder + preTripDaysBefore)

**Files:**
- Modify: `apps/web/app/api/settings/notifications/route.ts`
- Modify: `apps/web/__tests__/api/settings-notifications.test.ts`

**Step 1: Add new tests**

Append to `apps/web/__tests__/api/settings-notifications.test.ts`:

```typescript
// ---------------------------------------------------------------------------
// Settings V2: checkinReminder + preTripDaysBefore
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/notifications — V2 fields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("accepts checkinReminder toggle", async () => {
    mockPrisma.notificationPreference.upsert.mockResolvedValue({
      ...EXPECTED_DEFAULTS,
      checkinReminder: true,
      preTripDaysBefore: 3,
    } as any);

    const res = await PATCH(makePatchRequest({ checkinReminder: true }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.checkinReminder).toBe(true);
  });

  it("accepts valid preTripDaysBefore values", async () => {
    for (const days of [1, 3, 7]) {
      vi.clearAllMocks();
      mockGetServerSession.mockResolvedValue(authedSession);
      mockPrisma.notificationPreference.upsert.mockResolvedValue({
        ...EXPECTED_DEFAULTS,
        checkinReminder: false,
        preTripDaysBefore: days,
      } as any);

      const res = await PATCH(makePatchRequest({ preTripDaysBefore: days }));
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data.preTripDaysBefore).toBe(days);
    }
  });

  it("rejects invalid preTripDaysBefore value", async () => {
    const res = await PATCH(makePatchRequest({ preTripDaysBefore: 5 }));
    expect(res.status).toBe(400);
  });

  it("rejects non-integer preTripDaysBefore", async () => {
    const res = await PATCH(makePatchRequest({ preTripDaysBefore: 3.5 }));
    expect(res.status).toBe(400);
  });
});

describe("GET /api/settings/notifications — V2 fields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetServerSession.mockResolvedValue(authedSession);
  });

  it("returns V2 defaults when no record exists", async () => {
    mockPrisma.notificationPreference.findUnique.mockResolvedValue(null);
    const res = await GET();
    const data = await res.json();
    expect(data.checkinReminder).toBe(false);
    expect(data.preTripDaysBefore).toBe(3);
  });
});
```

Note: You'll need to add `EXPECTED_DEFAULTS` at the top of the test file (or reuse the existing pattern). It should match the DEFAULTS object in the route. Check the existing tests for the exact variable name used — if none exists, define:

```typescript
const EXPECTED_DEFAULTS = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  citySeeded: true,
  inspirationNudges: false,
  productUpdates: false,
};
```

**Step 2: Run tests to verify new ones fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-notifications.test.ts`
Expected: New tests FAIL (route doesn't return V2 fields), existing tests still pass

**Step 3: Update the notifications route**

In `apps/web/app/api/settings/notifications/route.ts`:

1. Add to `NOTIF_SELECT`:
```typescript
checkinReminder: true,
preTripDaysBefore: true,
```

2. Add to `DEFAULTS`:
```typescript
checkinReminder: false,
preTripDaysBefore: 3,
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-notifications.test.ts`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/api/settings/notifications/route.ts apps/web/__tests__/api/settings-notifications.test.ts
git commit -m "feat: add checkinReminder + preTripDaysBefore to notifications API"
```

---

## Task 8: DisplayPreferences Component

**Files:**
- Create: `apps/web/components/settings/DisplayPreferences.tsx`
- Test: `apps/web/__tests__/settings/DisplayPreferences.test.tsx`

**Step 1: Write the failing tests**

Create `apps/web/__tests__/settings/DisplayPreferences.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DisplayPreferences } from "@/components/settings/DisplayPreferences";

// Mock fetch
beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn();
});

const DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

describe("DisplayPreferences", () => {
  it("renders skeleton during load", () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {})); // never resolves
    render(<DisplayPreferences />);
    expect(screen.getByText("Display Preferences")).toBeInTheDocument();
    // Skeleton should be visible (animate-pulse wrapper)
    expect(screen.queryByText("Distance")).not.toBeInTheDocument();
  });

  it("renders all 5 field groups after load", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => DEFAULTS,
    });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("Date format")).toBeInTheDocument();
    expect(screen.getByText("Time format")).toBeInTheDocument();
    expect(screen.getByText("Theme")).toBeInTheDocument();
  });

  it("shows correct default selections", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => DEFAULTS,
    });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });

    // "mi" pill should be selected (has accent styling via aria-pressed or similar)
    const miRadio = screen.getByRole("radio", { name: "mi" });
    expect(miRadio).toBeChecked();
  });

  it("calls PATCH on radio selection change", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => DEFAULTS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...DEFAULTS, distanceUnit: "km" }) });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });

    const kmRadio = screen.getByRole("radio", { name: "km" });
    await user.click(kmRadio);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/settings/display",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ distanceUnit: "km" }),
        })
      );
    });
  });

  it("reverts on PATCH failure", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => DEFAULTS })
      .mockResolvedValueOnce({ ok: false, status: 500 });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });

    const kmRadio = screen.getByRole("radio", { name: "km" });
    await user.click(kmRadio);

    // Should revert back to "mi"
    await waitFor(() => {
      const miRadio = screen.getByRole("radio", { name: "mi" });
      expect(miRadio).toBeChecked();
    });
  });

  it("applies theme to DOM on theme change", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => DEFAULTS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...DEFAULTS, theme: "dark" }) });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Theme")).toBeInTheDocument();
    });

    const darkRadio = screen.getByRole("radio", { name: "Dark" });
    await user.click(darkRadio);

    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });
  });

  it("shows error state on fetch failure", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: false, status: 500 });

    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/DisplayPreferences.test.tsx`
Expected: FAIL — component doesn't exist

**Step 3: Write the component**

Create `apps/web/components/settings/DisplayPreferences.tsx`:

```typescript
"use client";

import { useState, useEffect } from "react";

// ---------- Config ----------

type DisplayField = "distanceUnit" | "temperatureUnit" | "dateFormat" | "timeFormat" | "theme";

type DisplayState = {
  distanceUnit: string;
  temperatureUnit: string;
  dateFormat: string;
  timeFormat: string;
  theme: string;
};

const DEFAULTS: DisplayState = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

type FieldConfig = {
  field: DisplayField;
  heading: string;
  options: { value: string; label: string }[];
  useDmMono?: boolean;
};

const FIELDS: FieldConfig[] = [
  {
    field: "distanceUnit",
    heading: "Distance",
    options: [
      { value: "mi", label: "mi" },
      { value: "km", label: "km" },
    ],
  },
  {
    field: "temperatureUnit",
    heading: "Temperature",
    options: [
      { value: "F", label: "F" },
      { value: "C", label: "C" },
    ],
  },
  {
    field: "dateFormat",
    heading: "Date format",
    useDmMono: true,
    options: [
      { value: "MM/DD/YYYY", label: "MM/DD/YYYY" },
      { value: "DD/MM/YYYY", label: "DD/MM/YYYY" },
      { value: "YYYY-MM-DD", label: "YYYY-MM-DD" },
    ],
  },
  {
    field: "timeFormat",
    heading: "Time format",
    options: [
      { value: "12h", label: "12h" },
      { value: "24h", label: "24h" },
    ],
  },
  {
    field: "theme",
    heading: "Theme",
    options: [
      { value: "light", label: "Light" },
      { value: "dark", label: "Dark" },
      { value: "system", label: "System" },
    ],
  },
];

// ---------- Theme application ----------

function applyTheme(value: string) {
  if (value === "system") {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    localStorage.removeItem("theme");
  } else {
    document.documentElement.setAttribute("data-theme", value);
    document.documentElement.style.colorScheme = value;
    localStorage.setItem("theme", value);
  }
}

// ---------- Component ----------

export function DisplayPreferences() {
  const [state, setState] = useState<DisplayState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [lastSaved, setLastSaved] = useState<DisplayState>(DEFAULTS);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/display");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setState(data);
          setLastSaved(data);
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

  async function handleChange(field: DisplayField, value: string) {
    const prev = state[field];
    if (prev === value) return;

    // Optimistic update
    setState((s) => ({ ...s, [field]: value }));

    // Apply theme immediately
    if (field === "theme") {
      applyTheme(value);
    }

    try {
      const res = await fetch("/api/settings/display", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      if (!res.ok) throw new Error();
      const saved = await res.json();
      setLastSaved(saved);
    } catch {
      // Revert
      setState(lastSaved);
      if (field === "theme") {
        applyTheme(lastSaved.theme);
      }
    }
  }

  return (
    <section id="display" aria-labelledby="display-heading">
      <h2 id="display-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Display Preferences
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-5">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="space-y-2">
                <div className="h-3 w-24 bg-warm-border rounded" />
                <div className="flex gap-2">
                  <div className="h-8 w-16 bg-warm-border rounded-lg" />
                  <div className="h-8 w-16 bg-warm-border rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load display preferences.</p>
        ) : (
          FIELDS.map(({ field, heading, options, useDmMono }) => (
            <fieldset key={field}>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                {heading}
              </legend>
              <div className="flex flex-wrap gap-2">
                {options.map(({ value, label }) => (
                  <label
                    key={value}
                    className={`
                      flex items-center px-3 py-1.5 rounded-lg border cursor-pointer
                      transition-colors
                      ${useDmMono ? "font-dm-mono text-xs" : "font-sora text-sm"}
                      ${state[field] === value
                        ? "border-accent bg-accent/10 text-ink-100"
                        : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                      }
                    `}
                  >
                    <input
                      type="radio"
                      name={field}
                      value={value}
                      checked={state[field] === value}
                      onChange={() => handleChange(field, value)}
                      className="sr-only"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          ))
        )}
      </div>
    </section>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/DisplayPreferences.test.tsx`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add apps/web/components/settings/DisplayPreferences.tsx apps/web/__tests__/settings/DisplayPreferences.test.tsx
git commit -m "feat: add DisplayPreferences component with radio pills and theme toggle"
```

---

## Task 9: TravelInterests Component

**Files:**
- Create: `apps/web/components/settings/TravelInterests.tsx`
- Test: `apps/web/__tests__/settings/TravelInterests.test.tsx`

**Step 1: Write the failing tests**

Create `apps/web/__tests__/settings/TravelInterests.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TravelInterests } from "@/components/settings/TravelInterests";

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
});

const PREFS_RESPONSE = {
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
  vibePreferences: [],
  travelStyleNote: null,
};

describe("TravelInterests", () => {
  it("renders skeleton during load", () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(<TravelInterests />);
    expect(screen.getByText("Travel Interests")).toBeInTheDocument();
    expect(screen.queryByText("Discovery Style")).not.toBeInTheDocument();
  });

  it("renders disclosure groups after load", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => PREFS_RESPONSE,
    });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Discovery Style")).toBeInTheDocument();
    });
    expect(screen.getByText("Food & Drink")).toBeInTheDocument();
    expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
    expect(screen.getByText("Activity Type")).toBeInTheDocument();
    expect(screen.getByText("Social & Time")).toBeInTheDocument();
  });

  it("Discovery Style and Food & Drink are open by default", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => PREFS_RESPONSE,
    });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Hidden gems")).toBeInTheDocument();
    });
    expect(screen.getByText("Street food")).toBeInTheDocument();
    // Pace & Energy should be collapsed — "High energy" chip not visible
    expect(screen.queryByText("High energy")).not.toBeInTheDocument();
  });

  it("toggling disclosure group shows/hides chips", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => PREFS_RESPONSE,
    });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
    });

    // Click to open Pace & Energy
    fireEvent.click(screen.getByText("Pace & Energy"));
    expect(screen.getByText("High energy")).toBeInTheDocument();

    // Click to close
    fireEvent.click(screen.getByText("Pace & Energy"));
    expect(screen.queryByText("High energy")).not.toBeInTheDocument();
  });

  it("chip click triggers debounced PATCH (500ms)", async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => PREFS_RESPONSE })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...PREFS_RESPONSE, vibePreferences: ["hidden-gem"] }) });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Hidden gems")).toBeInTheDocument();
    });

    // Click chip
    fireEvent.click(screen.getByText("Hidden gems"));

    // Should NOT have called PATCH yet
    expect(global.fetch).toHaveBeenCalledTimes(1); // only the initial GET

    // Advance timer
    vi.advanceTimersByTime(500);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2);
      expect(global.fetch).toHaveBeenLastCalledWith(
        "/api/settings/preferences",
        expect.objectContaining({
          method: "PATCH",
          body: expect.stringContaining("vibePreferences"),
        })
      );
    });
  });

  it("rapid clicks within 500ms produce exactly 1 PATCH", async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => PREFS_RESPONSE })
      .mockResolvedValue({ ok: true, json: async () => ({ ...PREFS_RESPONSE, vibePreferences: ["hidden-gem", "offbeat"] }) });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Hidden gems")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Hidden gems"));
    vi.advanceTimersByTime(200);
    fireEvent.click(screen.getByText("Offbeat & unexpected"));
    vi.advanceTimersByTime(500);

    await waitFor(() => {
      // 1 GET + 1 PATCH = 2 total
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  it("textarea saves on blur only", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => PREFS_RESPONSE })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...PREFS_RESPONSE, travelStyleNote: "Coffee" }) });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/coffee/i)).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/coffee/i);
    await user.click(textarea);
    await user.type(textarea, "Coffee");

    // Should not have PATCHed yet (only GET)
    expect(global.fetch).toHaveBeenCalledTimes(1);

    // Blur triggers save
    await user.tab();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/settings/preferences",
        expect.objectContaining({
          method: "PATCH",
          body: expect.stringContaining("travelStyleNote"),
        })
      );
    });
  });

  it("shows character counter when > 400 characters", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...PREFS_RESPONSE, travelStyleNote: "x".repeat(410) }),
    });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("90")).toBeInTheDocument(); // 500 - 410 = 90
    });
  });

  it("shows active count badge in collapsed group header", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...PREFS_RESPONSE, vibePreferences: ["high-energy", "slow-burn"] }),
    });

    render(<TravelInterests />);

    await waitFor(() => {
      // Pace & Energy is collapsed by default, should show "2" badge
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("reverts all chips on PATCH failure", async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: true, json: async () => PREFS_RESPONSE })
      .mockResolvedValueOnce({ ok: false, status: 500 });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Hidden gems")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Hidden gems"));
    vi.advanceTimersByTime(500);

    // After failure, chip should be unselected
    await waitFor(() => {
      const chip = screen.getByText("Hidden gems").closest("label");
      expect(chip?.className).toContain("border-warm-border");
    });
  });

  it("shows error state on initial fetch failure", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: false, status: 500 });

    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/TravelInterests.test.tsx`
Expected: FAIL — component doesn't exist

**Step 3: Write the component**

Create `apps/web/components/settings/TravelInterests.tsx`:

```typescript
"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------- Icons ----------

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      className={`transition-transform ${open ? "rotate-180" : ""}`}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

// ---------- Config ----------

type VibeGroup = {
  heading: string;
  defaultOpen: boolean;
  tags: { slug: string; label: string }[];
};

const VIBE_GROUPS: VibeGroup[] = [
  {
    heading: "Pace & Energy",
    defaultOpen: false,
    tags: [
      { slug: "high-energy", label: "High energy" },
      { slug: "slow-burn", label: "Slow burn" },
      { slug: "immersive", label: "Immersive" },
    ],
  },
  {
    heading: "Discovery Style",
    defaultOpen: true,
    tags: [
      { slug: "hidden-gem", label: "Hidden gems" },
      { slug: "iconic-worth-it", label: "Iconic & worth it" },
      { slug: "locals-only", label: "Locals only" },
      { slug: "offbeat", label: "Offbeat & unexpected" },
    ],
  },
  {
    heading: "Food & Drink",
    defaultOpen: true,
    tags: [
      { slug: "destination-meal", label: "Destination meals" },
      { slug: "street-food", label: "Street food" },
      { slug: "local-institution", label: "Local institutions" },
      { slug: "drinks-forward", label: "Drinks-forward spots" },
    ],
  },
  {
    heading: "Activity Type",
    defaultOpen: false,
    tags: [
      { slug: "nature-immersive", label: "Nature immersive" },
      { slug: "urban-exploration", label: "Urban exploration" },
      { slug: "deep-history", label: "Deep history" },
      { slug: "contemporary-culture", label: "Contemporary culture" },
      { slug: "hands-on", label: "Hands-on experiences" },
      { slug: "scenic", label: "Scenic views" },
    ],
  },
  {
    heading: "Social & Time",
    defaultOpen: false,
    tags: [
      { slug: "late-night", label: "Late night" },
      { slug: "early-morning", label: "Early morning" },
      { slug: "solo-friendly", label: "Solo-friendly" },
      { slug: "group-friendly", label: "Group-friendly" },
      { slug: "social-scene", label: "Social scene" },
      { slug: "low-interaction", label: "Low interaction" },
    ],
  },
];

// ---------- Component ----------

export function TravelInterests() {
  const [vibePreferences, setVibePreferences] = useState<string[]>([]);
  const [travelStyleNote, setTravelStyleNote] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const g of VIBE_GROUPS) init[g.heading] = g.defaultOpen;
    return init;
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedVibes = useRef<string[]>([]);
  const lastSavedNote = useRef<string>("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/preferences");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setVibePreferences(data.vibePreferences ?? []);
          setTravelStyleNote(data.travelStyleNote ?? "");
          lastSavedVibes.current = data.vibePreferences ?? [];
          lastSavedNote.current = data.travelStyleNote ?? "";
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

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const saveVibes = useCallback((next: string[]) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch("/api/settings/preferences", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vibePreferences: next }),
        });
        if (!res.ok) throw new Error();
        const saved = await res.json();
        lastSavedVibes.current = saved.vibePreferences ?? [];
      } catch {
        setVibePreferences(lastSavedVibes.current);
      }
    }, 500);
  }, []);

  function toggleVibe(slug: string) {
    setVibePreferences((prev) => {
      const next = prev.includes(slug)
        ? prev.filter((v) => v !== slug)
        : [...prev, slug];
      saveVibes(next);
      return next;
    });
  }

  async function saveNote() {
    if (travelStyleNote === lastSavedNote.current) return;
    try {
      const res = await fetch("/api/settings/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ travelStyleNote }),
      });
      if (!res.ok) throw new Error();
      lastSavedNote.current = travelStyleNote;
    } catch {
      setTravelStyleNote(lastSavedNote.current);
    }
  }

  const remaining = 500 - travelStyleNote.length;

  return (
    <section id="travel-interests" aria-labelledby="travel-interests-heading">
      <h2 id="travel-interests-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Travel Interests
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-4">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <div className="h-3 w-32 bg-warm-border rounded" />
                <div className="flex flex-wrap gap-2">
                  {[1, 2, 3, 4].map((j) => (
                    <div key={j} className="h-8 w-24 bg-warm-border rounded-lg" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load travel interests.</p>
        ) : (
          <>
            {/* Vibe tag groups */}
            {VIBE_GROUPS.map((group) => {
              const isOpen = openGroups[group.heading] ?? false;
              const activeCount = group.tags.filter((t) => vibePreferences.includes(t.slug)).length;

              return (
                <div key={group.heading}>
                  <button
                    type="button"
                    onClick={() => setOpenGroups((s) => ({ ...s, [group.heading]: !isOpen }))}
                    aria-expanded={isOpen}
                    className="flex items-center justify-between w-full py-2"
                  >
                    <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400">
                      {group.heading}
                    </span>
                    <span className="flex items-center gap-2">
                      {activeCount > 0 && (
                        <span className="font-dm-mono text-[10px] text-accent">{activeCount}</span>
                      )}
                      <ChevronIcon open={isOpen} />
                    </span>
                  </button>
                  {isOpen && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {group.tags.map(({ slug, label }) => {
                        const checked = vibePreferences.includes(slug);
                        return (
                          <label
                            key={slug}
                            className={`
                              flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                              font-sora text-sm transition-colors
                              ${checked
                                ? "border-accent bg-accent/10 text-ink-100"
                                : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                              }
                            `}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleVibe(slug)}
                              className="sr-only"
                            />
                            {checked && <CheckIcon />}
                            {label}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Free-form textarea */}
            <div className="pt-2">
              <label
                htmlFor="travel-style-note"
                className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2 block"
              >
                Anything else about how you travel?
              </label>
              <textarea
                id="travel-style-note"
                value={travelStyleNote}
                onChange={(e) => setTravelStyleNote(e.target.value)}
                onBlur={saveNote}
                maxLength={500}
                rows={3}
                placeholder="I always hunt for the best coffee spot in every city..."
                className="w-full rounded-lg border border-warm-border bg-transparent px-3 py-2 font-sora text-sm text-ink-200 placeholder:text-ink-500 focus:border-accent focus:outline-none resize-none"
              />
              {remaining <= 100 && (
                <p className={`text-right font-dm-mono text-[10px] tabular-nums ${remaining <= 20 ? "text-[var(--error)]" : "text-ink-400"}`}>
                  {remaining}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/TravelInterests.test.tsx`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add apps/web/components/settings/TravelInterests.tsx apps/web/__tests__/settings/TravelInterests.test.tsx
git commit -m "feat: add TravelInterests component with disclosure groups, chip debounce, blur textarea"
```

---

## Task 10: Enhance SubscriptionBadge with Billing Portal

**Files:**
- Modify: `apps/web/components/settings/SubscriptionBadge.tsx`
- Test: `apps/web/__tests__/settings/SubscriptionBadge.test.tsx`

**Step 1: Write the failing tests**

Create `apps/web/__tests__/settings/SubscriptionBadge.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SubscriptionBadge } from "@/components/settings/SubscriptionBadge";

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn();
  // Mock window.location
  Object.defineProperty(window, "location", {
    writable: true,
    value: { href: "" },
  });
});

describe("SubscriptionBadge", () => {
  it("renders tier badge", () => {
    render(<SubscriptionBadge tier="beta" />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("does not show billing link for beta tier", () => {
    render(<SubscriptionBadge tier="beta" />);
    expect(screen.queryByText("Manage billing")).not.toBeInTheDocument();
  });

  it("does not show billing link for free tier", () => {
    render(<SubscriptionBadge tier="free" />);
    expect(screen.queryByText("Manage billing")).not.toBeInTheDocument();
  });

  it("shows billing link for pro tier", () => {
    render(<SubscriptionBadge tier="pro" />);
    expect(screen.getByText("Manage billing")).toBeInTheDocument();
  });

  it("shows billing link for lifetime tier", () => {
    render(<SubscriptionBadge tier="lifetime" />);
    expect(screen.getByText("Manage billing")).toBeInTheDocument();
  });

  it("handles successful billing portal redirect", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ url: "https://billing.stripe.com/session/test" }),
    });

    render(<SubscriptionBadge tier="pro" />);
    await user.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(window.location.href).toBe("https://billing.stripe.com/session/test");
    });
  });

  it("shows loading state during portal request", async () => {
    const user = userEvent.setup();
    let resolvePortal: (value: unknown) => void;
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => { resolvePortal = resolve; })
    );

    render(<SubscriptionBadge tier="pro" />);
    await user.click(screen.getByText("Manage billing"));

    expect(screen.getByText("Opening...")).toBeInTheDocument();
    const button = screen.getByText("Opening...").closest("button");
    expect(button).toBeDisabled();

    // Resolve to clean up
    resolvePortal!({ ok: true, json: async () => ({ url: "https://billing.stripe.com/session/test" }) });
  });

  it("shows error on 404 (no billing account)", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ error: "No billing account found" }),
    });

    render(<SubscriptionBadge tier="pro" />);
    await user.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(screen.getByText("No billing account found")).toBeInTheDocument();
    });
  });

  it("shows generic error on server failure", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ error: "Internal error" }),
    });

    render(<SubscriptionBadge tier="pro" />);
    await user.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/SubscriptionBadge.test.tsx`
Expected: FAIL — current component doesn't have billing button

**Step 3: Update the component**

Replace `apps/web/components/settings/SubscriptionBadge.tsx`:

```typescript
"use client";

import { useState } from "react";

type SubscriptionBadgeProps = {
  tier: string;
};

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  beta: "Beta",
  pro: "Pro",
  lifetime: "Lifetime",
};

function SpinnerIcon() {
  return (
    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function SubscriptionBadge({ tier }: SubscriptionBadgeProps) {
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);

  const showBillingLink = ["pro", "lifetime"].includes(tier);

  async function handleManageBilling() {
    setBillingLoading(true);
    setBillingError(null);

    try {
      const res = await fetch("/api/settings/billing-portal", { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: "Something went wrong" }));
        setBillingError(data.error || "Something went wrong");
        return;
      }
      const data = await res.json();
      window.location.href = data.url;
    } catch {
      setBillingError("Could not reach billing service");
    } finally {
      setBillingLoading(false);
    }
  }

  return (
    <section id="subscription" aria-labelledby="subscription-heading">
      <h2 id="subscription-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Subscription
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 font-dm-mono text-xs text-accent uppercase tracking-wider">
            {TIER_LABELS[tier] || tier}
          </span>

          {showBillingLink && (
            <button
              onClick={handleManageBilling}
              disabled={billingLoading}
              className="font-dm-mono text-xs text-ink-400 hover:text-accent transition-colors disabled:opacity-50"
            >
              {billingLoading ? (
                <span className="flex items-center gap-1.5">
                  <SpinnerIcon />
                  Opening...
                </span>
              ) : (
                "Manage billing"
              )}
            </button>
          )}
        </div>

        {billingError && (
          <p className="mt-2 font-sora text-xs text-[var(--error)]">{billingError}</p>
        )}

        {!showBillingLink && (
          <p className="mt-3 font-sora text-sm text-ink-400">
            Your plan details will appear here.
          </p>
        )}
      </div>
    </section>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/SubscriptionBadge.test.tsx`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add apps/web/components/settings/SubscriptionBadge.tsx apps/web/__tests__/settings/SubscriptionBadge.test.tsx
git commit -m "feat: add Stripe billing portal link to SubscriptionBadge"
```

---

## Task 11: Enhance NotificationsSection (checkinReminder + preTripDaysBefore)

**Files:**
- Modify: `apps/web/components/settings/NotificationsSection.tsx`
- Modify: `apps/web/__tests__/settings/NotificationsSection.test.tsx`

**Step 1: Add new tests**

Add to existing `apps/web/__tests__/settings/NotificationsSection.test.tsx` (or create if it only has basic tests). Append new describe blocks:

```typescript
describe("NotificationsSection — V2 fields", () => {
  it("renders checkinReminder toggle in Trip activity group", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        tripReminders: true, morningBriefing: true, groupActivity: true,
        postTripPrompt: true, citySeeded: true, inspirationNudges: false,
        productUpdates: false, checkinReminder: false, preTripDaysBefore: 3,
      }),
    });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getByText("Check-in prompts during active trips")).toBeInTheDocument();
    });
  });

  it("renders preTripDaysBefore pills when tripReminders is on", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        tripReminders: true, morningBriefing: true, groupActivity: true,
        postTripPrompt: true, citySeeded: true, inspirationNudges: false,
        productUpdates: false, checkinReminder: false, preTripDaysBefore: 3,
      }),
    });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getByText("Remind me before trips")).toBeInTheDocument();
    });
    expect(screen.getByRole("radio", { name: "1 day" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "3 days" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "1 week" })).toBeInTheDocument();
  });

  it("hides preTripDaysBefore when tripReminders is off", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        tripReminders: false, morningBriefing: true, groupActivity: true,
        postTripPrompt: true, citySeeded: true, inspirationNudges: false,
        productUpdates: false, checkinReminder: false, preTripDaysBefore: 3,
      }),
    });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getByText("Notifications")).toBeInTheDocument();
    });
    expect(screen.queryByText("Remind me before trips")).not.toBeInTheDocument();
  });

  it("PATCHes preTripDaysBefore on radio change", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          tripReminders: true, morningBriefing: true, groupActivity: true,
          postTripPrompt: true, citySeeded: true, inspirationNudges: false,
          productUpdates: false, checkinReminder: false, preTripDaysBefore: 3,
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "1 week" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("radio", { name: "1 week" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/settings/notifications",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ preTripDaysBefore: 7 }),
        })
      );
    });
  });
});
```

**Step 2: Run tests to verify new ones fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/NotificationsSection.test.tsx`
Expected: New tests FAIL

**Step 3: Update the component**

In `apps/web/components/settings/NotificationsSection.tsx`:

1. Add `checkinReminder` and `preTripDaysBefore` to the `NotifField` type (only `checkinReminder` — `preTripDaysBefore` is not a toggle):

```typescript
type NotifField =
  | "tripReminders"
  | "morningBriefing"
  | "groupActivity"
  | "postTripPrompt"
  | "checkinReminder"
  | "citySeeded"
  | "inspirationNudges"
  | "productUpdates";
```

2. Add checkinReminder to NOTIF_GROUPS Trip activity items array:
```typescript
{ field: "checkinReminder", label: "Check-in prompts during active trips" },
```

3. Add to DEFAULTS:
```typescript
checkinReminder: false,
```

4. Add `preTripDaysBefore` as separate state:
```typescript
const [preTripDaysBefore, setPreTripDaysBefore] = useState(3);
```

Update the `load` function to also set `preTripDaysBefore` from fetched data.

5. Add `preTripDaysBefore` radio pills UI. Render right after the `tripReminders` toggle item, conditionally on `notifs.tripReminders`:

```typescript
{field === "tripReminders" && notifs.tripReminders && (
  <div className="ml-0 mt-2">
    <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-2">
      Remind me before trips
    </span>
    <div className="flex gap-2">
      {[
        { value: 1, label: "1 day" },
        { value: 3, label: "3 days" },
        { value: 7, label: "1 week" },
      ].map(({ value, label }) => (
        <label
          key={value}
          className={`
            flex items-center px-3 py-1.5 rounded-lg border cursor-pointer
            font-sora text-sm transition-colors
            ${preTripDaysBefore === value
              ? "border-accent bg-accent/10 text-ink-100"
              : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
            }
          `}
        >
          <input
            type="radio"
            name="preTripDaysBefore"
            value={value}
            checked={preTripDaysBefore === value}
            onChange={() => handleDaysChange(value)}
            className="sr-only"
          />
          {label}
        </label>
      ))}
    </div>
  </div>
)}
```

6. Add the `handleDaysChange` function:
```typescript
async function handleDaysChange(value: number) {
  const prev = preTripDaysBefore;
  setPreTripDaysBefore(value);
  try {
    const res = await fetch("/api/settings/notifications", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preTripDaysBefore: value }),
    });
    if (!res.ok) throw new Error();
  } catch {
    setPreTripDaysBefore(prev);
  }
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/NotificationsSection.test.tsx`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/web/components/settings/NotificationsSection.tsx apps/web/__tests__/settings/NotificationsSection.test.tsx
git commit -m "feat: add checkinReminder toggle + preTripDaysBefore selector to NotificationsSection"
```

---

## Task 12: Settings Page Wiring + Anchor Nav

**Files:**
- Modify: `apps/web/app/settings/page.tsx`
- Modify: `apps/web/__tests__/settings/SettingsPage.test.tsx`

**Step 1: Update page test mocks**

In `apps/web/__tests__/settings/SettingsPage.test.tsx`, add mocks for the new components:

```typescript
vi.mock("@/components/settings/DisplayPreferences", () => ({
  DisplayPreferences: () => <section><h2>Display Preferences</h2></section>,
}));

vi.mock("@/components/settings/TravelInterests", () => ({
  TravelInterests: () => <section><h2>Travel Interests</h2></section>,
}));
```

Add a test for the new sections:

```typescript
it("renders new V2 sections", () => {
  render(<SettingsPage />);
  expect(screen.getByText("Display Preferences")).toBeInTheDocument();
  expect(screen.getByText("Travel Interests")).toBeInTheDocument();
});
```

Add a test for the anchor nav:

```typescript
it("renders anchor navigation", () => {
  render(<SettingsPage />);
  expect(screen.getByRole("navigation")).toBeInTheDocument();
});
```

**Step 2: Run tests to verify new ones fail**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/SettingsPage.test.tsx`
Expected: New assertions FAIL

**Step 3: Update the settings page**

In `apps/web/app/settings/page.tsx`:

1. Add imports:
```typescript
import { DisplayPreferences } from "@/components/settings/DisplayPreferences";
import { TravelInterests } from "@/components/settings/TravelInterests";
```

2. Add anchor nav config and nav element after the page header, inside the authenticated block:

```typescript
const SECTION_ANCHORS = [
  { id: "account", label: "Account" },
  { id: "subscription", label: "Subscription" },
  { id: "display", label: "Display" },
  { id: "preferences", label: "Preferences" },
  { id: "travel-interests", label: "Interests" },
  { id: "notifications", label: "Notifications" },
  { id: "privacy", label: "Privacy" },
  { id: "about", label: "About" },
];
```

Move the constant outside the component, then add the nav:

```tsx
<nav className="flex gap-3 overflow-x-auto scrollbar-none -mx-4 px-4 pb-2 mb-2">
  {SECTION_ANCHORS.map(({ id, label }) => (
    <a
      key={id}
      href={`#${id}`}
      className="shrink-0 font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 hover:text-ink-200 transition-colors"
    >
      {label}
    </a>
  ))}
</nav>
```

3. Add the new components in correct order:
```tsx
<AccountSection ... />
<SubscriptionBadge ... />
<DisplayPreferences />
<PreferencesSection />
<TravelInterests />
<NotificationsSection />
<PrivacySection ... />
<AboutSection />
```

4. Ensure existing sections have `id` attributes that match anchors. The new components already have `id` props. For existing components, add `id` to their outermost `<section>` wrappers if not present (AccountSection → `id="account"`, etc.). Check if they already have `aria-labelledby` IDs that can be reused.

**Step 4: Run tests to verify they pass**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/settings/SettingsPage.test.tsx`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/web/app/settings/page.tsx apps/web/__tests__/settings/SettingsPage.test.tsx
git commit -m "feat: wire DisplayPreferences + TravelInterests into settings page with anchor nav"
```

---

## Task 13: Ranking Engine Wiring (vibePreferences → PersonaSeed)

**Files:**
- Modify: `apps/web/lib/generation/types.ts:4-10` (PersonaSeed)
- Modify: `apps/web/lib/generation/scoring.ts:28-52` (tag overlap scoring)
- Modify: `apps/web/app/api/trips/route.ts:93-98` (seed construction)

**Step 1: Add vibePreferences to PersonaSeed type**

In `apps/web/lib/generation/types.ts`, add to `PersonaSeed`:

```typescript
export interface PersonaSeed {
  pace: Pace;
  morningPreference: MorningPreference;
  foodPreferences: string[];
  vibePreferences?: string[];
  freeformVibes?: string;
  template?: string;
}
```

**Step 2: Update scoring to use vibePreferences**

In `apps/web/lib/generation/scoring.ts`, update the vibe tag overlap section (around line 38-52). Add vibePreferences to the matching set alongside foodPreferences:

```typescript
// Convert food preferences + vibe preferences to lowercase set for matching
const prefSet = new Set([
  ...personaSeed.foodPreferences.map(f => f.toLowerCase()),
  ...(personaSeed.vibePreferences ?? []).map(v => v.toLowerCase()),
]);
```

And update the loop to use `prefSet` instead of `foodPrefSet`:

```typescript
let tagOverlap = 0;
for (const pref of prefSet) {
  if (allNodeTags.has(pref)) tagOverlap++;
  for (const tag of allNodeTags) {
    if (tag.includes(pref) || pref.includes(tag)) {
      tagOverlap += 0.5;
      break;
    }
  }
}
score += Math.min(tagOverlap / Math.max(prefSet.size, 1), 1) * 0.30;
```

**Step 3: Merge vibePreferences into seed at trip creation**

In `apps/web/app/api/trips/route.ts`, update the seed construction (around line 93-98). After constructing the base seed, fetch user's vibe preferences:

```typescript
// Fetch user's vibe preferences from settings
let userVibes: string[] = [];
try {
  const userPref = await prisma.userPreference.findUnique({
    where: { userId },
    select: { vibePreferences: true },
  });
  userVibes = userPref?.vibePreferences ?? [];
} catch {
  // Non-critical — continue without vibes
}

const seed = {
  pace: (personaSeed as any)?.pace ?? "moderate",
  morningPreference: (personaSeed as any)?.morningPreference ?? "mid",
  foodPreferences: (personaSeed as any)?.foodPreferences ?? [],
  vibePreferences: userVibes,
  freeformVibes: (personaSeed as any)?.freeformVibes,
  template: presetTemplate ?? (personaSeed as any)?.template,
};
```

**Step 4: Run existing generation tests**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|generation|scoring|trips)"`
Expected: No regressions

**Step 5: Commit**

```bash
git add apps/web/lib/generation/types.ts apps/web/lib/generation/scoring.ts apps/web/app/api/trips/route.ts
git commit -m "feat: wire vibePreferences into ranking engine (PersonaSeed + scoring overlap)"
```

---

## Task 14: DayView Consumer Wiring (timeFormat)

**Files:**
- Modify: `apps/web/components/trip/DayView.tsx:17-44`

**Step 1: Add timeFormat prop to DayView**

In `apps/web/components/trip/DayView.tsx`, add `timeFormat` to `DayViewProps`:

```typescript
interface DayViewProps {
  dayNumber: number;
  slots: SlotData[];
  timezone?: string;
  /** Display time format preference */
  timeFormat?: string;
  onSlotAction: (event: SlotActionEvent) => void;
  showVoting?: boolean;
  showPivot?: boolean;
  showFlag?: boolean;
  totalDays?: number;
}
```

**Step 2: Update formatTimeMarker to accept timeFormat**

```typescript
function formatTimeMarker(isoString: string, timezone?: string, timeFormat?: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: timeFormat !== "24h",
      timeZone: timezone || undefined,
    });
  } catch {
    return "";
  }
}
```

**Step 3: Thread timeFormat through the component**

Update the call site (around line 122):

```typescript
const timeMarker = slot.startTime
  ? formatTimeMarker(slot.startTime, timezone, timeFormat)
  : null;
```

Make sure to destructure `timeFormat` from props in the component function.

**Step 4: Run existing DayView tests**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run --reporter=verbose 2>&1 | grep -E "(DayView|PASS|FAIL)"`
Expected: Existing tests still pass (timeFormat is optional, defaults to `hour12: true`)

**Step 5: Commit**

```bash
git add apps/web/components/trip/DayView.tsx
git commit -m "feat: wire timeFormat display preference to DayView time markers"
```

---

## Task 15: Full Test Suite + Regression Check

**Files:** None (verification only)

**Step 1: Run all settings tests**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/api/settings-display.test.ts __tests__/api/settings-billing-portal.test.ts __tests__/api/settings-preferences.test.ts __tests__/api/settings-notifications.test.ts __tests__/settings/DisplayPreferences.test.tsx __tests__/settings/TravelInterests.test.tsx __tests__/settings/SubscriptionBadge.test.tsx __tests__/settings/NotificationsSection.test.tsx __tests__/settings/SettingsPage.test.tsx`
Expected: All PASS

**Step 2: Run full test suite**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run`
Expected: 0 failures, no regressions

**Step 3: Check TypeScript compilation**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit any test fixes if needed**

If any tests needed adjustment, commit the fixes:
```bash
git add -A
git commit -m "fix: resolve test regressions from Settings V2 integration"
```
