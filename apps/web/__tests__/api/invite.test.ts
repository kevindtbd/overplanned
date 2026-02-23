/**
 * Tests for invite endpoints:
 *   GET  /api/invites/preview/[token]
 *   POST /api/trips/[id]/join?token=xxx
 *   POST /api/trips/[id]/invite
 *
 * Uses Vitest with mocked Prisma + next-auth.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// ---- Mocks ----

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    inviteToken: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
    tripMember: {
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
    },
    behavioralSignal: {
      create: vi.fn(),
    },
    $queryRaw: vi.fn(),
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/validations/invite", async () => {
  const actual = await import("../../lib/validations/invite");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---- Helpers ----

function authedSession(userId = "user-123") {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

const VALID_TOKEN = "abcdefghij1234567890abcdefghij12";
const TRIP_ID = "trip-001";

function makeInviteRecord(overrides: Record<string, unknown> = {}) {
  return {
    id: "inv-001",
    tripId: TRIP_ID,
    token: VALID_TOKEN,
    createdBy: "user-org",
    maxUses: 10,
    usedCount: 0,
    role: "member",
    expiresAt: new Date(Date.now() + 7 * 86400000),
    revokedAt: null,
    createdAt: new Date(),
    trip: {
      id: TRIP_ID,
      name: "Tokyo Adventure",
      startDate: new Date("2026-06-01"),
      endDate: new Date("2026-06-07"),
      status: "planning",
      members: [{ id: "m-1" }, { id: "m-2" }],
      legs: [
        { destination: "Tokyo, Japan", city: "Tokyo", country: "Japan" },
      ],
    },
    ...overrides,
  };
}

// ================================================================
// GET /api/invites/preview/[token]
// ================================================================

describe("GET /api/invites/preview/[token]", () => {
  let GET: typeof import("../../app/api/invites/preview/[token]/route").GET;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/invites/preview/[token]/route");
    GET = mod.GET;
  });

  it("returns 400 for invalid token format", async () => {
    const req = new NextRequest("http://localhost:3000/api/invites/preview/bad!");
    const res = await GET(req, { params: { token: "bad!" } });
    expect(res.status).toBe(400);
  });

  it("returns 400 for short token", async () => {
    const req = new NextRequest("http://localhost:3000/api/invites/preview/abc");
    const res = await GET(req, { params: { token: "abc" } });
    expect(res.status).toBe(400);
  });

  it("returns 404 when invite not found", async () => {
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(null);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.valid).toBe(false);
  });

  it("returns 410 when invite is expired", async () => {
    const expired = makeInviteRecord({
      expiresAt: new Date(Date.now() - 86400000),
    });
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(expired as never);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
    const json = await res.json();
    expect(json.valid).toBe(false);
  });

  it("returns 410 when invite is revoked", async () => {
    const revoked = makeInviteRecord({ revokedAt: new Date() });
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(revoked as never);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
  });

  it("returns 410 when invite is fully used", async () => {
    const used = makeInviteRecord({ usedCount: 10, maxUses: 10 });
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(used as never);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
  });

  it("returns valid preview with trip data", async () => {
    const invite = makeInviteRecord();
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(invite as never);
    mockPrisma.tripMember.findFirst.mockResolvedValueOnce({
      user: { name: "Jane Doe" },
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.valid).toBe(true);
    expect(json.tripId).toBe(TRIP_ID);
    expect(json.destination).toBe("Tokyo, Japan");
    expect(json.city).toBe("Tokyo");
    expect(json.country).toBe("Japan");
    expect(json.memberCount).toBe(2);
    expect(json.organizerName).toBe("Jane");
  });

  it("truncates organizer name to first name only (V13)", async () => {
    const invite = makeInviteRecord();
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(invite as never);
    mockPrisma.tripMember.findFirst.mockResolvedValueOnce({
      user: { name: "Alexander Hamilton III" },
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    const json = await res.json();
    expect(json.organizerName).toBe("Alexander");
  });

  it("falls back to 'Someone' when organizer has no name", async () => {
    const invite = makeInviteRecord();
    mockPrisma.inviteToken.findUnique.mockResolvedValueOnce(invite as never);
    mockPrisma.tripMember.findFirst.mockResolvedValueOnce(null);

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    const json = await res.json();
    expect(json.organizerName).toBe("Someone");
  });

  it("returns 500 on unexpected DB error", async () => {
    mockPrisma.inviteToken.findUnique.mockRejectedValueOnce(new Error("DB down"));

    const req = new NextRequest(`http://localhost:3000/api/invites/preview/${VALID_TOKEN}`);
    const res = await GET(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(500);
  });
});

// ================================================================
// POST /api/trips/[id]/join?token=xxx
// ================================================================

describe("POST /api/trips/[id]/join", () => {
  let POST: typeof import("../../app/api/trips/[id]/join/route").POST;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/trips/[id]/join/route");
    POST = mod.POST;
  });

  it("returns 401 if not authenticated", async () => {
    noSession();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 400 if token is missing", async () => {
    authedSession();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 400 if token has invalid characters", async () => {
    authedSession();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=invalid%3Cscript%3E`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 409 if user is already a joined member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toBe("Already a member");
  });

  it("returns 409 when atomic SQL returns 0 rows (expired/revoked/exhausted)", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    mockPrisma.$queryRaw.mockResolvedValueOnce([] as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(409);
  });

  it("creates new membership on successful join", async () => {
    authedSession("user-new");
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    mockPrisma.$queryRaw.mockResolvedValueOnce([{ id: "inv-1", role: "member" }] as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.tripId).toBe(TRIP_ID);

    // Verify transaction was called with create (not update)
    expect(mockPrisma.$transaction).toHaveBeenCalledOnce();
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    expect(txArgs).toHaveLength(2); // membership create + signal create
  });

  it("updates existing declined membership on rejoin", async () => {
    authedSession("user-declined");
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "declined",
    } as never);
    mockPrisma.$queryRaw.mockResolvedValueOnce([{ id: "inv-1", role: "member" }] as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
  });

  it("returns 500 on unexpected error", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockRejectedValueOnce(new Error("DB down"));

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/join?token=${VALID_TOKEN}`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(500);
  });
});

// ================================================================
// POST /api/trips/[id]/invite
// ================================================================

describe("POST /api/trips/[id]/invite", () => {
  let POST: typeof import("../../app/api/trips/[id]/invite/route").POST;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/trips/[id]/invite/route");
    POST = mod.POST;
  });

  it("returns 401 if not authenticated", async () => {
    noSession();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 404 if user is not a joined member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 403 if user is not organizer", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(403);
  });

  it("returns 409 if trip is not group mode", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      mode: "solo",
      status: "planning",
    } as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toContain("group");
  });

  it("creates invite with defaults (maxUses=10, 7 days)", async () => {
    authedSession("user-org");
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      mode: "group",
      status: "planning",
    } as never);

    const mockInvite = {
      id: "inv-new",
      token: "generated-token-abc",
      expiresAt: new Date("2026-03-01"),
    };
    mockPrisma.inviteToken.create.mockResolvedValueOnce(mockInvite as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);

    const json = await res.json();
    expect(json.token).toBe("generated-token-abc");
    expect(json.inviteUrl).toContain("/invite/generated-token-abc");
    expect(json.expiresAt).toBeDefined();

    // Verify create was called with correct maxUses default
    const createCall = mockPrisma.inviteToken.create.mock.calls[0][0];
    expect(createCall.data.maxUses).toBe(10);
  });

  it("accepts custom maxUses and expiresInDays", async () => {
    authedSession("user-org");
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      mode: "group",
      status: "planning",
    } as never);
    mockPrisma.inviteToken.create.mockResolvedValueOnce({
      id: "inv-new",
      token: "custom-token",
      expiresAt: new Date("2026-03-15"),
    } as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      {
        method: "POST",
        body: JSON.stringify({ maxUses: 5, expiresInDays: 14 }),
        headers: { "Content-Type": "application/json" },
      }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);

    const createCall = mockPrisma.inviteToken.create.mock.calls[0][0];
    expect(createCall.data.maxUses).toBe(5);
  });

  it("returns 400 for invalid maxUses", async () => {
    authedSession();

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      {
        method: "POST",
        body: JSON.stringify({ maxUses: 0 }),
        headers: { "Content-Type": "application/json" },
      }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 400 for expiresInDays > 30", async () => {
    authedSession();

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      {
        method: "POST",
        body: JSON.stringify({ expiresInDays: 31 }),
        headers: { "Content-Type": "application/json" },
      }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 500 on unexpected DB error", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockRejectedValueOnce(new Error("DB down"));

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/invite`,
      { method: "POST" }
    );
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(500);
  });
});

// ================================================================
// Zod schema unit tests
// ================================================================

describe("invite validation schemas", () => {
  let inviteCreateSchema: typeof import("../../lib/validations/invite").inviteCreateSchema;
  let joinQuerySchema: typeof import("../../lib/validations/invite").joinQuerySchema;

  beforeEach(async () => {
    const mod = await import("../../lib/validations/invite");
    inviteCreateSchema = mod.inviteCreateSchema;
    joinQuerySchema = mod.joinQuerySchema;
  });

  describe("inviteCreateSchema", () => {
    it("applies defaults when empty object", () => {
      const result = inviteCreateSchema.parse({});
      expect(result.maxUses).toBe(10);
      expect(result.expiresInDays).toBe(7);
    });

    it("accepts valid values", () => {
      const result = inviteCreateSchema.parse({ maxUses: 50, expiresInDays: 14 });
      expect(result.maxUses).toBe(50);
      expect(result.expiresInDays).toBe(14);
    });

    it("rejects maxUses < 1", () => {
      expect(() => inviteCreateSchema.parse({ maxUses: 0 })).toThrow();
    });

    it("rejects maxUses > 100", () => {
      expect(() => inviteCreateSchema.parse({ maxUses: 101 })).toThrow();
    });

    it("rejects non-integer maxUses", () => {
      expect(() => inviteCreateSchema.parse({ maxUses: 5.5 })).toThrow();
    });

    it("rejects expiresInDays < 1", () => {
      expect(() => inviteCreateSchema.parse({ expiresInDays: 0 })).toThrow();
    });

    it("rejects expiresInDays > 30", () => {
      expect(() => inviteCreateSchema.parse({ expiresInDays: 31 })).toThrow();
    });
  });

  describe("joinQuerySchema", () => {
    it("accepts valid base64url token", () => {
      const result = joinQuerySchema.parse({ token: VALID_TOKEN });
      expect(result.token).toBe(VALID_TOKEN);
    });

    it("rejects token shorter than 10 chars", () => {
      expect(() => joinQuerySchema.parse({ token: "short" })).toThrow();
    });

    it("rejects token longer than 64 chars", () => {
      expect(() =>
        joinQuerySchema.parse({ token: "a".repeat(65) })
      ).toThrow();
    });

    it("rejects token with special characters", () => {
      expect(() =>
        joinQuerySchema.parse({ token: "abc<script>alert(1)</script>" })
      ).toThrow();
    });

    it("accepts token with hyphens and underscores", () => {
      const token = "abc-def_ghi-123456";
      const result = joinQuerySchema.parse({ token });
      expect(result.token).toBe(token);
    });

    it("rejects null token", () => {
      expect(() => joinQuerySchema.parse({ token: null })).toThrow();
    });
  });
});
