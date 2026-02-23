/**
 * Route handler tests for GET + PATCH /api/settings/notifications
 * Tests auth guards, validation, defaults fallback, upsert behavior, and IDOR prevention.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    notificationPreference: {
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
  "../../app/api/settings/notifications/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeGetRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/notifications", {
    method: "GET",
  });
}

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/notifications", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/notifications", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

const DEFAULTS = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  citySeeded: true,
  inspirationNudges: false,
  productUpdates: false,
  checkinReminder: false,
  preTripDaysBefore: 3,
};

describe("GET /api/settings/notifications — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

describe("GET /api/settings/notifications — defaults and saved prefs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns defaults when no record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.notificationPreference.findUnique.mockResolvedValueOnce(
      null as never
    );

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(DEFAULTS);
  });

  it("returns saved prefs when record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const savedPrefs = {
      tripReminders: false,
      morningBriefing: true,
      groupActivity: false,
      postTripPrompt: true,
      citySeeded: false,
      inspirationNudges: true,
      productUpdates: true,
      checkinReminder: true,
      preTripDaysBefore: 7,
    };
    mockPrisma.notificationPreference.findUnique.mockResolvedValueOnce(
      savedPrefs as never
    );

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(savedPrefs);
  });
});

describe("PATCH /api/settings/notifications — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ tripReminders: false }));
    expect(res.status).toBe(401);
  });
});

describe("PATCH /api/settings/notifications — validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

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
    const res = await PATCH(makePatchRequest({ tripReminders: "yes" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });
});

describe("PATCH /api/settings/notifications — upsert behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("upserts a single field with userId from session in create block", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = { ...DEFAULTS, tripReminders: false };
    mockPrisma.notificationPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(makePatchRequest({ tripReminders: false }));
    expect(res.status).toBe(200);

    const upsertCall =
      mockPrisma.notificationPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create).toMatchObject({
      userId: "user-abc",
      tripReminders: false,
    });
    expect(upsertCall.update).toEqual({ tripReminders: false });
  });

  it("stores explicit false correctly (not treated as absent)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = { ...DEFAULTS, inspirationNudges: false };
    mockPrisma.notificationPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(makePatchRequest({ inspirationNudges: false }));
    expect(res.status).toBe(200);

    const upsertCall =
      mockPrisma.notificationPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update).toEqual({ inspirationNudges: false });
    expect(upsertCall.create).toMatchObject({ inspirationNudges: false });
  });
});

describe("PATCH /api/settings/notifications — field whitelisting and IDOR", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores extra fields like userId and id in request body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = { ...DEFAULTS, groupActivity: false };
    mockPrisma.notificationPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(
      makePatchRequest({
        groupActivity: false,
        userId: "attacker-id",
        id: "fake-id",
      })
    );
    expect(res.status).toBe(200);

    const upsertCall =
      mockPrisma.notificationPreference.upsert.mock.calls[0][0];
    // userId in Prisma create comes from session, not body
    expect(upsertCall.create.userId).toBe("user-abc");
    // update payload should not contain userId or id
    expect(upsertCall.update).not.toHaveProperty("userId");
    expect(upsertCall.update).not.toHaveProperty("id");
  });

  it("userId in Prisma where clause comes from session, not body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.notificationPreference.upsert.mockResolvedValueOnce(
      DEFAULTS as never
    );

    await PATCH(
      makePatchRequest({ tripReminders: true, userId: "attacker-id" })
    );

    const upsertCall =
      mockPrisma.notificationPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.where.userId).not.toBe("attacker-id");
  });

  it("returns only the 9 notification fields", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.notificationPreference.upsert.mockResolvedValueOnce(
      DEFAULTS as never
    );

    const res = await PATCH(makePatchRequest({ morningBriefing: false }));
    const json = await res.json();

    const expectedKeys = [
      "tripReminders",
      "morningBriefing",
      "groupActivity",
      "postTripPrompt",
      "citySeeded",
      "inspirationNudges",
      "productUpdates",
      "checkinReminder",
      "preTripDaysBefore",
    ];
    expect(Object.keys(json).sort()).toEqual(expectedKeys.sort());
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("userId");
    expect(json).not.toHaveProperty("createdAt");
  });
});
