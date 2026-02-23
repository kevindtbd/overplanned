/**
 * Route handler tests for PATCH /api/settings/account
 * Tests auth guard, validation, field whitelisting, and happy path.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      update: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { PATCH } = await import("../../app/api/settings/account/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/account", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/account", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

describe("PATCH /api/settings/account — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ name: "New Name" }));
    expect(res.status).toBe(401);
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({ user: null } as never);
    const res = await PATCH(makePatchRequest({ name: "New Name" }));
    expect(res.status).toBe(401);
  });
});

describe("PATCH /api/settings/account — validation", () => {
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

  it("returns 400 when name is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({}));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when name is empty string", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ name: "" }));
    expect(res.status).toBe(400);
  });

  it("returns 400 when name is whitespace-only", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ name: "   " }));
    expect(res.status).toBe(400);
  });

  it("returns 400 when name exceeds 100 characters", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const longName = "A".repeat(101);
    const res = await PATCH(makePatchRequest({ name: longName }));
    expect(res.status).toBe(400);
  });
});

describe("PATCH /api/settings/account — field whitelisting", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("only updates name field, ignores subscriptionTier in body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Safe Name" } as never);

    const res = await PATCH(
      makePatchRequest({ name: "Safe Name", subscriptionTier: "lifetime" })
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.user.update.mock.calls[0][0];
    expect(updateCall.data).toEqual({ name: "Safe Name" });
    expect(updateCall.data).not.toHaveProperty("subscriptionTier");
  });

  it("only updates name field, ignores systemRole in body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Normal User" } as never);

    const res = await PATCH(
      makePatchRequest({ name: "Normal User", systemRole: "admin" })
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.user.update.mock.calls[0][0];
    expect(updateCall.data).toEqual({ name: "Normal User" });
    expect(updateCall.data).not.toHaveProperty("systemRole");
  });

  it("derives userId from session, not from request body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Test" } as never);

    await PATCH(makePatchRequest({ name: "Test", userId: "attacker-id" }));

    const updateCall = mockPrisma.user.update.mock.calls[0][0];
    expect(updateCall.where).toEqual({ id: "user-abc" });
    expect(updateCall.where.id).not.toBe("attacker-id");
  });
});

describe("PATCH /api/settings/account — happy path", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates name and returns { name } on success", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Kevin" } as never);

    const res = await PATCH(makePatchRequest({ name: "Kevin" }));
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual({ name: "Kevin" });
  });

  it("trims whitespace from name before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Kevin" } as never);

    await PATCH(makePatchRequest({ name: "  Kevin  " }));

    const updateCall = mockPrisma.user.update.mock.calls[0][0];
    expect(updateCall.data.name).toBe("Kevin");
  });

  it("accepts names with special characters", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Jean-Pierre O'Brien" } as never);

    const res = await PATCH(makePatchRequest({ name: "Jean-Pierre O'Brien" }));
    expect(res.status).toBe(200);
  });

  it("accepts 100-character names (boundary)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const maxName = "A".repeat(100);
    mockPrisma.user.update.mockResolvedValueOnce({ name: maxName } as never);

    const res = await PATCH(makePatchRequest({ name: maxName }));
    expect(res.status).toBe(200);
  });

  it("returns only name in response, no sensitive fields", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.update.mockResolvedValueOnce({ name: "Kevin" } as never);

    const res = await PATCH(makePatchRequest({ name: "Kevin" }));
    const json = await res.json();

    expect(Object.keys(json)).toEqual(["name"]);
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("email");
    expect(json).not.toHaveProperty("subscriptionTier");
  });
});
