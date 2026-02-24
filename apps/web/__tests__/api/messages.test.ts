/**
 * Tests for trip chat message endpoints:
 *   GET    /api/trips/[id]/messages              — List messages (cursor pagination)
 *   POST   /api/trips/[id]/messages              — Send message
 *   DELETE /api/trips/[id]/messages/[messageId]   — Delete own message
 *
 * Uses Vitest with mocked Prisma + next-auth + rate-limit.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// ---- Mocks ----

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: {
      findUnique: vi.fn(),
    },
    message: {
      findMany: vi.fn(),
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
    },
    itinerarySlot: {
      findFirst: vi.fn(),
    },
    behavioralSignal: {
      create: vi.fn(),
    },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/rate-limit", () => ({
  rateLimit: vi.fn().mockReturnValue(null),
  rateLimitPresets: {
    authenticated: { limit: 10, windowMs: 60000 },
  },
}));

vi.mock("@/lib/validations/messages", async () => {
  const actual = await import("../../lib/validations/messages");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { rateLimit } = await import("@/lib/rate-limit");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);
const mockRateLimit = vi.mocked(rateLimit);

// ---- Helpers ----

const USER_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000001";
const OTHER_USER_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000002";
const TRIP_ID = "a1b2c3d4-e5f6-4a7b-8c9d-100000000001";
const MSG_ID_1 = "a1b2c3d4-e5f6-4a7b-8c9d-200000000001";
const MSG_ID_2 = "a1b2c3d4-e5f6-4a7b-8c9d-200000000002";
const SLOT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-300000000001";
const SLOT_ID_OTHER_TRIP = "a1b2c3d4-e5f6-4a7b-8c9d-300000000002";

function authedSession(userId = USER_ID) {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

function mockJoinedMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    status: "joined",
  } as never);
}

function mockInvitedMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    status: "invited",
  } as never);
}

function mockNoMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
}

function makeMessage(overrides: Record<string, unknown> = {}) {
  return {
    id: MSG_ID_1,
    tripId: TRIP_ID,
    userId: USER_ID,
    body: "Hello, world!",
    slotRefId: null,
    slotRef: null,
    createdAt: new Date("2026-02-24T10:00:00Z"),
    user: { id: USER_ID, name: "Test User", avatarUrl: null },
    ...overrides,
  };
}

function makeSlotRef(overrides: Record<string, unknown> = {}) {
  return {
    id: SLOT_ID,
    dayNumber: 1,
    startTime: new Date("2026-06-01T09:00:00Z"),
    wasSwapped: false,
    status: "confirmed",
    activityNode: { name: "Tsukiji Market", category: "dining" },
    ...overrides,
  };
}

// ================================================================
// Auth gate tests (shared behavior across GET/POST/DELETE)
// ================================================================

describe("Auth gates", () => {
  let GET: typeof import("../../app/api/trips/[id]/messages/route").GET;
  let POST: typeof import("../../app/api/trips/[id]/messages/route").POST;
  let DELETE: typeof import("../../app/api/trips/[id]/messages/[messageId]/route").DELETE;

  beforeEach(async () => {
    vi.resetAllMocks();
    mockRateLimit.mockReturnValue(null);
    const msgMod = await import("../../app/api/trips/[id]/messages/route");
    GET = msgMod.GET;
    POST = msgMod.POST;
    const delMod = await import("../../app/api/trips/[id]/messages/[messageId]/route");
    DELETE = delMod.DELETE;
  });

  it("GET returns 401 when not authenticated", async () => {
    noSession();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("GET returns 404 when user has no membership", async () => {
    authedSession();
    mockNoMember();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("GET returns 404 when member status is invited (not joined)", async () => {
    authedSession();
    mockInvitedMember();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("GET proceeds for joined member", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.message.findMany.mockResolvedValueOnce([]);
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
  });
});

// ================================================================
// GET /api/trips/[id]/messages
// ================================================================

describe("GET /api/trips/[id]/messages", () => {
  let GET: typeof import("../../app/api/trips/[id]/messages/route").GET;

  beforeEach(async () => {
    vi.resetAllMocks();
    mockRateLimit.mockReturnValue(null);
    const mod = await import("../../app/api/trips/[id]/messages/route");
    GET = mod.GET;
  });

  it("returns empty messages array and null cursor", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.message.findMany.mockResolvedValueOnce([]);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.messages).toEqual([]);
    expect(json.nextCursor).toBeNull();
  });

  it("returns messages with user info", async () => {
    authedSession();
    mockJoinedMember();
    const msg = makeMessage();
    mockPrisma.message.findMany.mockResolvedValueOnce([msg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.messages).toHaveLength(1);
    expect(json.messages[0].user.id).toBe(USER_ID);
    expect(json.messages[0].user.name).toBe("Test User");
  });

  it("hydrates slot ref with activityNode name and isStale flag", async () => {
    authedSession();
    mockJoinedMember();
    const msg = makeMessage({ slotRefId: SLOT_ID, slotRef: makeSlotRef() });
    mockPrisma.message.findMany.mockResolvedValueOnce([msg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.messages[0].slotRef.activityNode.name).toBe("Tsukiji Market");
    expect(json.messages[0].slotRef.isStale).toBe(false);
  });

  it("marks wasSwapped slot as isStale: true", async () => {
    authedSession();
    mockJoinedMember();
    const msg = makeMessage({
      slotRefId: SLOT_ID,
      slotRef: makeSlotRef({ wasSwapped: true }),
    });
    mockPrisma.message.findMany.mockResolvedValueOnce([msg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.messages[0].slotRef.isStale).toBe(true);
  });

  it("marks skipped status slot as isStale: true", async () => {
    authedSession();
    mockJoinedMember();
    const msg = makeMessage({
      slotRefId: SLOT_ID,
      slotRef: makeSlotRef({ status: "skipped" }),
    });
    mockPrisma.message.findMany.mockResolvedValueOnce([msg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.messages[0].slotRef.isStale).toBe(true);
  });

  it("returns null slotRef when slot was deleted (SetNull)", async () => {
    authedSession();
    mockJoinedMember();
    const msg = makeMessage({ slotRefId: null, slotRef: null });
    mockPrisma.message.findMany.mockResolvedValueOnce([msg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.messages[0].slotRef).toBeNull();
  });

  it("returns nextCursor when page is full (cursor pagination)", async () => {
    authedSession();
    mockJoinedMember();

    // Return exactly `limit` messages (default 50)
    const messages = Array.from({ length: 50 }, (_, i) =>
      makeMessage({
        id: `a1b2c3d4-e5f6-4a7b-8c9d-2000000000${String(i).padStart(2, "0")}`,
        createdAt: new Date(Date.now() - i * 60000),
      })
    );
    mockPrisma.message.findMany.mockResolvedValueOnce(messages as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.nextCursor).toBe(messages[49].id);
  });

  it("returns null nextCursor on last page", async () => {
    authedSession();
    mockJoinedMember();

    // Return fewer than limit
    const messages = [makeMessage()];
    mockPrisma.message.findMany.mockResolvedValueOnce(messages as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`);
    const res = await GET(req, { params: { id: TRIP_ID } });
    const json = await res.json();
    expect(json.nextCursor).toBeNull();
  });

  it("uses cursor for keyset pagination", async () => {
    authedSession();
    mockJoinedMember();

    const cursorDate = new Date("2026-02-24T09:00:00Z");
    mockPrisma.message.findUnique.mockResolvedValueOnce({
      id: MSG_ID_1,
      createdAt: cursorDate,
    } as never);
    mockPrisma.message.findMany.mockResolvedValueOnce([]);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/messages?cursor=${MSG_ID_1}`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);

    // Verify findMany was called with OR condition for keyset pagination
    const findManyCall = mockPrisma.message.findMany.mock.calls[0][0];
    expect(findManyCall?.where?.OR).toBeDefined();
  });

  it("clamps limit to max 50", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.message.findMany.mockResolvedValueOnce([]);

    // limit=100 should be rejected by Zod (max 50)
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/messages?limit=100`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });
});

// ================================================================
// POST /api/trips/[id]/messages
// ================================================================

describe("POST /api/trips/[id]/messages", () => {
  let POST: typeof import("../../app/api/trips/[id]/messages/route").POST;

  beforeEach(async () => {
    vi.resetAllMocks();
    mockRateLimit.mockReturnValue(null);
    const mod = await import("../../app/api/trips/[id]/messages/route");
    POST = mod.POST;
  });

  it("creates a text-only message and returns 201", async () => {
    authedSession();
    mockJoinedMember();

    const createdMsg = makeMessage({ body: "Great spot!" });
    mockPrisma.$transaction.mockResolvedValueOnce([createdMsg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "Great spot!" }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.body).toBe("Great spot!");
  });

  it("creates a message with slotRefId and logs BehavioralSignal", async () => {
    authedSession();
    mockJoinedMember();

    // Slot exists in trip
    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce({ id: SLOT_ID } as never);

    const createdMsg = makeMessage({
      body: "Check this out",
      slotRefId: SLOT_ID,
      slotRef: makeSlotRef(),
    });
    mockPrisma.$transaction.mockResolvedValueOnce([createdMsg, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "Check this out", slotRefId: SLOT_ID }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);

    // Transaction should include 2 operations (message + signal)
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    expect(txArgs).toHaveLength(2);
  });

  it("allows empty body with slotRefId (pure slot share) - 201", async () => {
    authedSession();
    mockJoinedMember();

    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce({ id: SLOT_ID } as never);
    const createdMsg = makeMessage({ body: "", slotRefId: SLOT_ID, slotRef: makeSlotRef() });
    mockPrisma.$transaction.mockResolvedValueOnce([createdMsg, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "", slotRefId: SLOT_ID }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);
  });

  it("rejects empty body without slotRefId - 400", async () => {
    authedSession();
    mockJoinedMember();

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "" }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("rejects whitespace-only body without slotRefId - 400", async () => {
    authedSession();
    mockJoinedMember();

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "   \t\n  " }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("accepts body at exactly 2000 chars - 201", async () => {
    authedSession();
    mockJoinedMember();

    const longBody = "A".repeat(2000);
    const createdMsg = makeMessage({ body: longBody });
    mockPrisma.$transaction.mockResolvedValueOnce([createdMsg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: longBody }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);
  });

  it("rejects body at 2001 chars - 400", async () => {
    authedSession();
    mockJoinedMember();

    const tooLong = "A".repeat(2001);
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: tooLong }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("rejects slotRefId from a different trip - 400", async () => {
    authedSession();
    mockJoinedMember();

    // Slot not found in this trip
    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce(null);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "Look!", slotRefId: SLOT_ID_OTHER_TRIP }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Slot not found in this trip");
  });

  it("rejects non-existent slotRefId - 400", async () => {
    authedSession();
    mockJoinedMember();

    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce(null);

    const fakeSlotId = "a1b2c3d4-e5f6-4a7b-8c9d-999999999999";
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "Look!", slotRefId: fakeSlotId }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("strips HTML tags from body", async () => {
    authedSession();
    mockJoinedMember();

    const createdMsg = makeMessage({ body: "alertHello" });
    mockPrisma.$transaction.mockResolvedValueOnce([createdMsg] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: '<script>alert("xss")</script>Hello' }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);

    // Verify the sanitized body was passed to prisma
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    // The first arg to $transaction is an array of PrismaPromises
    // We check the create call was made with sanitized body
    const createCall = mockPrisma.message.create.mock.calls[0][0];
    expect(createCall?.data?.body).not.toContain("<script>");
    expect(createCall?.data?.body).not.toContain("</script>");
  });

  it("returns 429 when rate limited", async () => {
    authedSession();
    const { NextResponse } = await import("next/server");
    mockRateLimit.mockReturnValueOnce(
      NextResponse.json({ error: "Too many requests" }, { status: 429 })
    );

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: "Hello" }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(429);
  });
});

// ================================================================
// DELETE /api/trips/[id]/messages/[messageId]
// ================================================================

describe("DELETE /api/trips/[id]/messages/[messageId]", () => {
  let DELETE: typeof import("../../app/api/trips/[id]/messages/[messageId]/route").DELETE;

  beforeEach(async () => {
    vi.resetAllMocks();
    mockRateLimit.mockReturnValue(null);
    const mod = await import("../../app/api/trips/[id]/messages/[messageId]/route");
    DELETE = mod.DELETE;
  });

  it("author deletes own message - 200", async () => {
    authedSession();
    mockJoinedMember();

    mockPrisma.message.findFirst.mockResolvedValueOnce(makeMessage() as never);
    mockPrisma.message.delete.mockResolvedValueOnce({} as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/messages/${MSG_ID_1}`,
      { method: "DELETE" }
    );
    const res = await DELETE(req, { params: { id: TRIP_ID, messageId: MSG_ID_1 } });
    expect(res.status).toBe(200);
  });

  it("non-author attempt returns 404", async () => {
    authedSession(OTHER_USER_ID);
    mockJoinedMember();

    // findFirst with userId = OTHER_USER_ID won't find a message authored by USER_ID
    mockPrisma.message.findFirst.mockResolvedValueOnce(null);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/messages/${MSG_ID_1}`,
      { method: "DELETE" }
    );
    const res = await DELETE(req, { params: { id: TRIP_ID, messageId: MSG_ID_1 } });
    expect(res.status).toBe(404);
  });

  it("non-existent message returns 404", async () => {
    authedSession();
    mockJoinedMember();

    mockPrisma.message.findFirst.mockResolvedValueOnce(null);

    const fakeId = "a1b2c3d4-e5f6-4a7b-8c9d-999999999999";
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/messages/${fakeId}`,
      { method: "DELETE" }
    );
    const res = await DELETE(req, { params: { id: TRIP_ID, messageId: fakeId } });
    expect(res.status).toBe(404);
  });
});

// ================================================================
// Zod Schema Unit Tests
// ================================================================

describe("Message validation schemas", () => {
  it("messageCreateSchema requires body when no slotRefId", async () => {
    const { messageCreateSchema } = await import("../../lib/validations/messages");
    expect(messageCreateSchema.safeParse({ body: "" }).success).toBe(false);
    expect(messageCreateSchema.safeParse({}).success).toBe(false);
  });

  it("messageCreateSchema allows empty body with slotRefId", async () => {
    const { messageCreateSchema } = await import("../../lib/validations/messages");
    const result = messageCreateSchema.safeParse({
      body: "",
      slotRefId: "a1b2c3d4-e5f6-4a7b-8c9d-000000000001",
    });
    expect(result.success).toBe(true);
  });

  it("messageCreateSchema rejects body over 2000 chars", async () => {
    const { messageCreateSchema } = await import("../../lib/validations/messages");
    expect(
      messageCreateSchema.safeParse({ body: "A".repeat(2001) }).success
    ).toBe(false);
  });

  it("messageCreateSchema accepts body at exactly 2000 chars", async () => {
    const { messageCreateSchema } = await import("../../lib/validations/messages");
    expect(
      messageCreateSchema.safeParse({ body: "A".repeat(2000) }).success
    ).toBe(true);
  });

  it("messageCreateSchema rejects non-uuid slotRefId", async () => {
    const { messageCreateSchema } = await import("../../lib/validations/messages");
    expect(
      messageCreateSchema.safeParse({ body: "hi", slotRefId: "not-a-uuid" }).success
    ).toBe(false);
  });

  it("messageCursorSchema defaults limit to 50", async () => {
    const { messageCursorSchema } = await import("../../lib/validations/messages");
    const result = messageCursorSchema.safeParse({});
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.limit).toBe(50);
    }
  });

  it("messageCursorSchema rejects limit > 50", async () => {
    const { messageCursorSchema } = await import("../../lib/validations/messages");
    expect(messageCursorSchema.safeParse({ limit: 100 }).success).toBe(false);
  });

  it("messageCursorSchema rejects non-uuid cursor", async () => {
    const { messageCursorSchema } = await import("../../lib/validations/messages");
    expect(messageCursorSchema.safeParse({ cursor: "bad" }).success).toBe(false);
  });
});
