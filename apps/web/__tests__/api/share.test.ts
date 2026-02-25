/**
 * Tests for share endpoints:
 *   POST /api/trips/[id]/share
 *   GET  /api/shared/[token]
 *   POST /api/shared/[token]/import
 *
 * Uses Vitest with mocked Prisma + next-auth.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { Prisma } from "@prisma/client";
import { NextRequest } from "next/server";

// ---- Mocks ----

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    sharedTripToken: {
      findUnique: vi.fn(),
      create: vi.fn(),
      update: vi.fn().mockResolvedValue({}),
    },
    tripMember: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
    },
    tripLeg: {
      create: vi.fn(),
    },
    itinerarySlot: {
      create: vi.fn(),
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
    public: { limit: 30, windowMs: 60000 },
    authenticated: { limit: 10, windowMs: 60000 },
  },
}));

vi.mock("@/lib/validations/share", async () => {
  const actual = await import("../../lib/validations/share");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

// ---- Helpers ----

function authedSession(userId = "user-123") {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

const TRIP_ID = "trip-001";
const VALID_TOKEN = "abcdefghij1234567890abcdefghij12";

function makeSharedTokenRecord(overrides: Record<string, unknown> = {}) {
  return {
    id: "st-001",
    tripId: TRIP_ID,
    token: VALID_TOKEN,
    createdBy: "user-org",
    expiresAt: new Date(Date.now() + 30 * 86400000),
    revokedAt: null,
    viewCount: 0,
    importCount: 0,
    createdAt: new Date(),
    ...overrides,
  };
}

function makeTripData(overrides: Record<string, unknown> = {}) {
  return {
    id: TRIP_ID,
    userId: "user-org",
    name: "Tokyo Adventure",
    mode: "group",
    status: "active",
    startDate: new Date("2026-04-01"),
    endDate: new Date("2026-04-05"),
    presetTemplate: "culture_explorer",
    personaSeed: { adventurousness: 0.8 },
    logisticsState: null,
    legs: [
      {
        id: "leg-001",
        tripId: TRIP_ID,
        position: 0,
        city: "Tokyo",
        country: "Japan",
        timezone: "Asia/Tokyo",
        destination: "Tokyo, Japan",
        startDate: new Date("2026-04-01"),
        endDate: new Date("2026-04-05"),
        arrivalTime: "morning",
        departureTime: "evening",
        transitMode: null,
        transitDurationMin: null,
        transitCostHint: null,
        transitConfirmed: false,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
    ],
    slots: [
      {
        id: "slot-001",
        tripId: TRIP_ID,
        tripLegId: "leg-001",
        activityNodeId: "node-001",
        dayNumber: 1,
        sortOrder: 0,
        slotType: "anchor",
        status: "confirmed",
        startTime: new Date("2026-04-01T09:00:00Z"),
        endTime: new Date("2026-04-01T11:00:00Z"),
        durationMinutes: 120,
        isLocked: false,
        voteState: { state: "confirmed", votes: { "user-org": "yes" } },
        isContested: false,
        swappedFromId: null,
        pivotEventId: null,
        wasSwapped: false,
        createdAt: new Date(),
        updatedAt: new Date(),
        activityNode: {
          id: "node-001",
          name: "Senso-ji Temple",
          canonicalName: "Senso-ji",
          category: "culture",
          subcategory: null,
          neighborhood: "Asakusa",
          priceLevel: 0,
          primaryImageUrl: "https://images.unsplash.com/photo-sensoji",
          descriptionShort: "Historic Buddhist temple",
          latitude: 35.7148,
          longitude: 139.7967,
        },
      },
    ],
    ...overrides,
  };
}

// ====================================================================
// POST /api/trips/[id]/share — Create share token
// ====================================================================

describe("POST /api/trips/[id]/share", () => {
  let handler: typeof import("../../app/api/trips/[id]/share/route").POST;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/trips/[id]/share/route");
    handler = mod.POST;
  });

  it("returns 401 without auth", async () => {
    noSession();
    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 404 for non-member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 403 for non-organizer", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(403);
  });

  it("creates share token with default 30-day expiry", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);

    const now = Date.now();
    mockPrisma.sharedTripToken.create.mockResolvedValueOnce({
      id: "st-new",
      token: "generated-token",
      expiresAt: new Date(now + 30 * 86400000),
      createdAt: new Date(),
    } as never);

    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);

    const json = await res.json();
    expect(json.token).toBeDefined();
    expect(json.shareUrl).toContain("/s/");
    expect(json.expiresAt).toBeDefined();

    // Verify token was created with 256-bit random token
    const createCall = mockPrisma.sharedTripToken.create.mock.calls[0][0] as {
      data: { token: string };
    };
    // base64url of 32 bytes = 43 chars
    expect(createCall.data.token.length).toBeGreaterThanOrEqual(43);
  });

  it("creates share token with custom expiry", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);

    mockPrisma.sharedTripToken.create.mockResolvedValueOnce({
      id: "st-new",
      token: "generated-token",
      expiresAt: new Date(Date.now() + 7 * 86400000),
      createdAt: new Date(),
    } as never);

    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
      body: JSON.stringify({ expiresInDays: 7 }),
      headers: { "Content-Type": "application/json" },
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(201);
  });

  it("logs trip_shared behavioral signal", async () => {
    authedSession("user-org");
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "joined",
    } as never);

    mockPrisma.sharedTripToken.create.mockResolvedValueOnce({
      id: "st-new",
      token: "tok",
      expiresAt: new Date(),
      createdAt: new Date(),
    } as never);

    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    await handler(req, { params: { id: TRIP_ID } });

    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        userId: "user-org",
        tripId: TRIP_ID,
        signalType: "share_action",
        rawAction: "trip_shared",
      }),
    });
  });

  it("returns 404 for invited-but-not-joined member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "invited",
    } as never);

    const req = new NextRequest("http://localhost/api/trips/trip-001/share", {
      method: "POST",
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });
});

// ====================================================================
// GET /api/shared/[token] — Public shared trip view
// ====================================================================

describe("GET /api/shared/[token]", () => {
  let handler: typeof import("../../app/api/shared/[token]/route").GET;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/shared/[token]/route");
    handler = mod.GET;
  });

  it("returns 400 for invalid token format", async () => {
    const req = new NextRequest("http://localhost/api/shared/short", {
      method: "GET",
    });
    const res = await handler(req, { params: { token: "short" } });
    expect(res.status).toBe(400);
  });

  it("returns 404 for unknown token", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce(null as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(404);
  });

  it("returns 410 for expired token", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord({
        expiresAt: new Date(Date.now() - 86400000), // expired yesterday
      }),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
  });

  it("returns 410 for revoked token", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord({ revokedAt: new Date() }),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
  });

  it("returns trip preview with slots grouped by day", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.trip.destination).toBe("Tokyo, Japan");
    expect(json.trip.city).toBe("Tokyo");
    expect(json.trip.country).toBe("Japan");
    expect(json.slotsByDay["1"]).toHaveLength(1);
    expect(json.slotsByDay["1"][0].activity.name).toBe("Senso-ji Temple");
    expect(json.sharedAt).toBeDefined();
  });

  it("strips voteState and member PII from response", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    const json = await res.json();

    // No voteState, no members in response
    const slot = json.slotsByDay["1"][0];
    expect(slot.voteState).toBeUndefined();
    expect(json.trip.members).toBeUndefined();
    expect(json.trip.userId).toBeUndefined();
  });

  it("increments viewCount", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    await handler(req, { params: { token: VALID_TOKEN } });

    expect(mockPrisma.sharedTripToken.update).toHaveBeenCalledWith({
      where: { id: "st-001" },
      data: { viewCount: { increment: 1 } },
    });
  });

  it("includes legs in response", async () => {
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(`http://localhost/api/shared/${VALID_TOKEN}`, {
      method: "GET",
    });
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    const json = await res.json();

    expect(json.legs).toHaveLength(1);
    expect(json.legs[0].city).toBe("Tokyo");
  });
});

// ====================================================================
// POST /api/shared/[token]/import — Import shared trip
// ====================================================================

describe("POST /api/shared/[token]/import", () => {
  let handler: typeof import("../../app/api/shared/[token]/import/route").POST;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/shared/[token]/import/route");
    handler = mod.POST;
  });

  it("returns 401 without auth", async () => {
    noSession();
    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(401);
  });

  it("returns 400 for invalid token", async () => {
    authedSession();
    const req = new NextRequest("http://localhost/api/shared/bad/import", {
      method: "POST",
    });
    const res = await handler(req, { params: { token: "bad" } });
    expect(res.status).toBe(400);
  });

  it("returns 404 for unknown token", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce(null as never);

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(404);
  });

  it("returns 410 for expired token", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord({ expiresAt: new Date(Date.now() - 86400000) }),
      trip: makeTripData(),
    } as never);

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(410);
  });

  it("returns 409 if user already imported this trip (V9)", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    // User already imported
    mockPrisma.trip.findFirst.mockResolvedValueOnce({
      id: "existing-import",
    } as never);

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(409);

    const json = await res.json();
    expect(json.tripId).toBe("existing-import");
  });

  it("creates cloned trip with solo mode and planning status", async () => {
    authedSession("user-importer");
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    // No existing import
    mockPrisma.trip.findFirst.mockResolvedValueOnce(null as never);

    // Transaction mock
    const createdTrip = { id: "new-trip-id" };
    mockPrisma.$transaction.mockImplementationOnce(async (fn: Function) => {
      // Create a mock tx that records calls
      const tx = {
        trip: { create: vi.fn().mockResolvedValue(createdTrip) },
        tripMember: { create: vi.fn().mockResolvedValue({}) },
        tripLeg: { create: vi.fn().mockResolvedValue({}) },
        itinerarySlot: { create: vi.fn().mockResolvedValue({}) },
        behavioralSignal: { create: vi.fn().mockResolvedValue({}) },
      };
      const result = await fn(tx);

      // Verify trip created with correct fields
      const tripCreateData = tx.trip.create.mock.calls[0][0].data;
      expect(tripCreateData.mode).toBe("solo");
      expect(tripCreateData.status).toBe("planning");
      expect(tripCreateData.userId).toBe("user-importer");
      expect(tripCreateData.name).toBe("Tokyo Adventure (imported)");
      expect(tripCreateData.logisticsState).toEqual({
        sourceSharedTokenId: "st-001",
      });
      // Must NOT copy: groupId, fairnessState, affinityMatrix
      expect(tripCreateData.groupId).toBeUndefined();
      expect(tripCreateData.fairnessState).toBeUndefined();
      expect(tripCreateData.affinityMatrix).toBeUndefined();

      // Verify organizer membership created
      expect(tx.tripMember.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            userId: "user-importer",
            role: "organizer",
            status: "joined",
          }),
        })
      );

      // Verify legs cloned
      expect(tx.tripLeg.create).toHaveBeenCalledTimes(1);

      // Verify slots cloned with reset status
      expect(tx.itinerarySlot.create).toHaveBeenCalledTimes(1);
      const slotData = tx.itinerarySlot.create.mock.calls[0][0].data;
      expect(slotData.status).toBe("proposed"); // Reset
      expect(slotData.voteState).toBe(Prisma.JsonNull); // Cleared
      expect(slotData.isLocked).toBe(false);
      expect(slotData.wasSwapped).toBe(false);
      expect(slotData.isContested).toBe(false);

      // Verify signal logged
      expect(tx.behavioralSignal.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            userId: "user-importer",
            signalType: "share_action",
            rawAction: "trip_imported",
          }),
        })
      );

      return result;
    });

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    const res = await handler(req, { params: { token: VALID_TOKEN } });
    expect(res.status).toBe(201);

    const json = await res.json();
    expect(json.tripId).toBe("new-trip-id");
  });

  it("generates new UUIDs for all cloned entities", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    mockPrisma.trip.findFirst.mockResolvedValueOnce(null as never);

    const entityIds: string[] = [];
    mockPrisma.$transaction.mockImplementationOnce(async (fn: Function) => {
      const tx = {
        trip: {
          create: vi.fn().mockImplementation((args: { data: { id: string } }) => {
            entityIds.push(args.data.id);
            return { id: args.data.id };
          }),
        },
        tripMember: { create: vi.fn().mockResolvedValue({}) },
        tripLeg: {
          create: vi.fn().mockImplementation((args: { data: { id: string } }) => {
            entityIds.push(args.data.id);
            return {};
          }),
        },
        itinerarySlot: {
          create: vi.fn().mockImplementation((args: { data: { id: string } }) => {
            entityIds.push(args.data.id);
            return {};
          }),
        },
        behavioralSignal: { create: vi.fn().mockResolvedValue({}) },
      };
      return fn(tx);
    });

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    await handler(req, { params: { token: VALID_TOKEN } });

    // All entity IDs must be unique
    const unique = new Set(entityIds);
    expect(unique.size).toBe(entityIds.length);

    // None should match source IDs
    expect(entityIds).not.toContain(TRIP_ID);
    expect(entityIds).not.toContain("leg-001");
    expect(entityIds).not.toContain("slot-001");
  });

  it("increments importCount on token", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData(),
    } as never);

    mockPrisma.trip.findFirst.mockResolvedValueOnce(null as never);
    mockPrisma.$transaction.mockImplementationOnce(async (fn: Function) => {
      const tx = {
        trip: { create: vi.fn().mockResolvedValue({ id: "new-id" }) },
        tripMember: { create: vi.fn().mockResolvedValue({}) },
        tripLeg: { create: vi.fn().mockResolvedValue({}) },
        itinerarySlot: { create: vi.fn().mockResolvedValue({}) },
        behavioralSignal: { create: vi.fn().mockResolvedValue({}) },
      };
      return fn(tx);
    });

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    await handler(req, { params: { token: VALID_TOKEN } });

    // Wait for fire-and-forget
    await new Promise((r) => setTimeout(r, 10));

    expect(mockPrisma.sharedTripToken.update).toHaveBeenCalledWith({
      where: { id: "st-001" },
      data: { importCount: { increment: 1 } },
    });
  });

  it("preserves personaSeed and presetTemplate in clone", async () => {
    authedSession();
    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce({
      ...makeSharedTokenRecord(),
      trip: makeTripData({
        personaSeed: { adventurousness: 0.9, foodie: 0.7 },
        presetTemplate: "foodie_paradise",
      }),
    } as never);

    mockPrisma.trip.findFirst.mockResolvedValueOnce(null as never);

    let capturedTripData: Record<string, unknown> | null = null;
    mockPrisma.$transaction.mockImplementationOnce(async (fn: Function) => {
      const tx = {
        trip: {
          create: vi.fn().mockImplementation((args: { data: Record<string, unknown> }) => {
            capturedTripData = args.data;
            return { id: "new-id" };
          }),
        },
        tripMember: { create: vi.fn().mockResolvedValue({}) },
        tripLeg: { create: vi.fn().mockResolvedValue({}) },
        itinerarySlot: { create: vi.fn().mockResolvedValue({}) },
        behavioralSignal: { create: vi.fn().mockResolvedValue({}) },
      };
      return fn(tx);
    });

    const req = new NextRequest(
      `http://localhost/api/shared/${VALID_TOKEN}/import`,
      { method: "POST" }
    );
    await handler(req, { params: { token: VALID_TOKEN } });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const captured = capturedTripData as any;
    expect(captured?.personaSeed).toEqual({
      adventurousness: 0.9,
      foodie: 0.7,
    });
    expect(captured?.presetTemplate).toBe("foodie_paradise");
  });
});

// ====================================================================
// Zod schema validation
// ====================================================================

describe("share validation schemas", () => {
  it("shareCreateSchema defaults expiresInDays to 30", async () => {
    const { shareCreateSchema } = await import(
      "../../lib/validations/share"
    );
    const result = shareCreateSchema.parse({});
    expect(result.expiresInDays).toBe(30);
  });

  it("shareCreateSchema rejects expiresInDays > 90", async () => {
    const { shareCreateSchema } = await import(
      "../../lib/validations/share"
    );
    const result = shareCreateSchema.safeParse({ expiresInDays: 91 });
    expect(result.success).toBe(false);
  });

  it("shareCreateSchema rejects expiresInDays < 1", async () => {
    const { shareCreateSchema } = await import(
      "../../lib/validations/share"
    );
    const result = shareCreateSchema.safeParse({ expiresInDays: 0 });
    expect(result.success).toBe(false);
  });

  it("shareCreateSchema rejects non-integer", async () => {
    const { shareCreateSchema } = await import(
      "../../lib/validations/share"
    );
    const result = shareCreateSchema.safeParse({ expiresInDays: 7.5 });
    expect(result.success).toBe(false);
  });

  it("sanitizeToken strips invalid characters", async () => {
    const { sanitizeToken } = await import(
      "../../lib/validations/share"
    );
    expect(sanitizeToken("valid-token_123456789012345")).toBeDefined();
    expect(sanitizeToken("ab")).toBeNull(); // too short
    expect(sanitizeToken("")).toBeNull();
  });

  it("sanitizeToken truncates to 64 chars", async () => {
    const { sanitizeToken } = await import(
      "../../lib/validations/share"
    );
    const long = "a".repeat(100);
    const result = sanitizeToken(long);
    expect(result?.length).toBe(64);
  });
});
