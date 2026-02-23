/**
 * Route handler tests for GET + PATCH /api/settings/preferences
 * Tests auth guards, validation, array deduplication, upsert behavior,
 * and field whitelisting (userId from session only).
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
  "../../app/api/settings/preferences/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeGetRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "GET",
  });
}

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

// ---------------------------------------------------------------------------
// GET — auth guards
// ---------------------------------------------------------------------------
describe("GET /api/settings/preferences — auth guards", () => {
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

// ---------------------------------------------------------------------------
// GET — data retrieval
// ---------------------------------------------------------------------------
describe("GET /api/settings/preferences — data retrieval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns defaults when no record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.findUnique.mockResolvedValueOnce(null);

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual({
      dietary: [],
      mobility: [],
      languages: [],
      travelFrequency: null,
    });
  });

  it("returns saved preferences when record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const savedPrefs = {
      dietary: ["vegan", "halal"],
      mobility: ["wheelchair"],
      languages: ["non-english-menus"],
      travelFrequency: "monthly",
    };
    mockPrisma.userPreference.findUnique.mockResolvedValueOnce(
      savedPrefs as never
    );

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(savedPrefs);
  });
});

// ---------------------------------------------------------------------------
// PATCH — auth guards
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ dietary: ["vegan"] }));
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// PATCH — validation
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — validation", () => {
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

  it("returns 400 for invalid dietary array items", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ dietary: ["pizza"] }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid travelFrequency value", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(
      makePatchRequest({ travelFrequency: "every-decade" })
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });
});

// ---------------------------------------------------------------------------
// PATCH — upsert behavior
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — upsert behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("upserts on first write with userId from session and empty defaults", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = {
      dietary: ["vegan"],
      mobility: [],
      languages: [],
      travelFrequency: null,
    };
    mockPrisma.userPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(makePatchRequest({ dietary: ["vegan"] }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create.userId).toBe("user-abc");
    expect(upsertCall.create.dietary).toEqual(["vegan"]);
    expect(upsertCall.create.mobility).toEqual([]);
    expect(upsertCall.create.languages).toEqual([]);
    expect(upsertCall.create.travelFrequency).toBeNull();
    expect(upsertCall.select).toEqual({
      dietary: true,
      mobility: true,
      languages: true,
      travelFrequency: true,
    });
  });

  it("deduplicates arrays before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["vegan"],
      mobility: [],
      languages: [],
      travelFrequency: null,
    } as never);

    await PATCH(makePatchRequest({ dietary: ["vegan", "vegan"] }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.dietary).toEqual(["vegan"]);
    expect(upsertCall.create.dietary).toEqual(["vegan"]);
  });

  it("stores empty array when clearing selections", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: [],
      mobility: [],
      languages: [],
      travelFrequency: null,
    } as never);

    await PATCH(makePatchRequest({ dietary: [] }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.dietary).toEqual([]);
    expect(upsertCall.create.dietary).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// PATCH — field whitelisting & response shape
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — field whitelisting", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores extra fields like userId and id in body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["halal"],
      mobility: [],
      languages: [],
      travelFrequency: null,
    } as never);

    await PATCH(
      makePatchRequest({
        dietary: ["halal"],
        userId: "attacker-id",
        id: "fake-id",
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    // userId in where/create comes from session, not body
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create.userId).toBe("user-abc");
    // update block should not contain userId or id
    expect(upsertCall.update).not.toHaveProperty("userId");
    expect(upsertCall.update).not.toHaveProperty("id");
  });

  it("returns only data fields in response (no id/userId/timestamps)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["kosher"],
      mobility: [],
      languages: [],
      travelFrequency: "monthly",
    } as never);

    const res = await PATCH(
      makePatchRequest({ dietary: ["kosher"], travelFrequency: "monthly" })
    );
    const json = await res.json();

    // Verify the upsert uses PREF_SELECT to limit returned fields
    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.select).toEqual({
      dietary: true,
      mobility: true,
      languages: true,
      travelFrequency: true,
    });

    // Response should only contain data fields
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("userId");
    expect(json).not.toHaveProperty("createdAt");
    expect(json).not.toHaveProperty("updatedAt");
  });
});
