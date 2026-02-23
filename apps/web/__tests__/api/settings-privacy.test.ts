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
