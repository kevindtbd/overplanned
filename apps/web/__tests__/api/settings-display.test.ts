/**
 * Route handler tests for GET + PATCH /api/settings/display
 * Tests auth guards, validation, defaults fallback, upsert behavior,
 * field whitelisting, and response shape.
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

const DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

// ---------------------------------------------------------------------------
// GET — auth guards
// ---------------------------------------------------------------------------
describe("GET /api/settings/display — auth guards", () => {
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
describe("GET /api/settings/display — data retrieval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns defaults when no record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.findUnique.mockResolvedValueOnce(null);

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(DEFAULTS);
  });

  it("returns saved display prefs when record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const savedPrefs = {
      distanceUnit: "km",
      temperatureUnit: "C",
      dateFormat: "YYYY-MM-DD",
      timeFormat: "24h",
      theme: "dark",
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
describe("PATCH /api/settings/display — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ theme: "dark" }));
    expect(res.status).toBe(401);
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({ user: null } as never);
    const res = await PATCH(makePatchRequest({ theme: "dark" }));
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// PATCH — validation
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/display — validation", () => {
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

  it("returns 400 for invalid enum value (theme: 'blue')", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ theme: "blue" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid distanceUnit", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ distanceUnit: "feet" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });
});

// ---------------------------------------------------------------------------
// PATCH — upsert behavior
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/display — upsert behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("upserts a single field with userId from session", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = { ...DEFAULTS, theme: "dark" };
    mockPrisma.userPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(makePatchRequest({ theme: "dark" }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create).toMatchObject({ userId: "user-abc", theme: "dark" });
    expect(upsertCall.update).toEqual({ theme: "dark" });
    expect(upsertCall.select).toEqual({
      distanceUnit: true,
      temperatureUnit: true,
      dateFormat: true,
      timeFormat: true,
      theme: true,
    });
  });
});

// ---------------------------------------------------------------------------
// PATCH — field whitelisting & response shape
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/display — field whitelisting", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores extra fields like userId and id in body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      ...DEFAULTS,
      theme: "dark",
    } as never);

    await PATCH(
      makePatchRequest({
        theme: "dark",
        userId: "attacker-id",
        id: "fake-id",
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create.userId).toBe("user-abc");
    expect(upsertCall.update).not.toHaveProperty("userId");
    expect(upsertCall.update).not.toHaveProperty("id");
  });

  it("returns only display fields in response (no id/userId/timestamps)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      distanceUnit: "km",
      temperatureUnit: "C",
      dateFormat: "DD/MM/YYYY",
      timeFormat: "24h",
      theme: "light",
    } as never);

    const res = await PATCH(makePatchRequest({ distanceUnit: "km" }));
    const json = await res.json();

    const expectedKeys = [
      "distanceUnit",
      "temperatureUnit",
      "dateFormat",
      "timeFormat",
      "theme",
    ];
    expect(Object.keys(json).sort()).toEqual(expectedKeys.sort());
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("userId");
    expect(json).not.toHaveProperty("createdAt");
    expect(json).not.toHaveProperty("updatedAt");
  });
});
