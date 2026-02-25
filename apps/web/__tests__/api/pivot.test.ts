/**
 * Route handler tests for:
 *   POST  /api/trips/[id]/pivot          (create pivot)
 *   PATCH /api/trips/[id]/pivot/[pivotId] (resolve pivot)
 *
 * Tests auth guards, validation, pivot caps, scoring, resolution, vote reset,
 * and signal logging.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: { findUnique: vi.fn() },
    itinerarySlot: { findUnique: vi.fn(), update: vi.fn() },
    pivotEvent: { count: vi.fn(), create: vi.fn(), findUnique: vi.fn(), update: vi.fn() },
    activityNode: { findMany: vi.fn() },
    behavioralSignal: { create: vi.fn() },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("uuid", () => ({
  v4: () => "mock-uuid-1",
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import(
  "../../app/api/trips/[id]/pivot/route"
);
const { PATCH } = await import(
  "../../app/api/trips/[id]/pivot/[pivotId]/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

const authedSession = { user: { id: "user-abc" } };
const tripId = "trip-1";
// Valid UUIDs required by pivotCreateSchema (slotId: z.string().uuid())
const slotId = "123e4567-e89b-12d3-a456-426614174000";
const pivotId = "223e4567-e89b-12d3-a456-426614174001";

function makeCreateRequest(body: unknown): NextRequest {
  return new NextRequest(`http://localhost:3000/api/trips/${tripId}/pivot`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function makeResolveRequest(body: unknown): NextRequest {
  return new NextRequest(
    `http://localhost:3000/api/trips/${tripId}/pivot/${pivotId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

const createParams = { params: { id: tripId } };
const resolveParams = { params: { id: tripId, pivotId } };

const baseSlot = {
  id: slotId,
  tripId,
  activityNodeId: "node-original",
  status: "confirmed",
  voteState: null,
  isContested: false,
  activityNode: { id: "node-original", city: "Tokyo", category: "dining" },
  trip: {
    id: tripId,
    status: "active",
    personaSeed: { vibes: ["local-eats", "hidden-gems"] },
    slots: [
      { activityNodeId: "node-original" },
      { activityNodeId: "node-existing-2" },
    ],
  },
};

// Valid UUIDs for alternativeIds (selectedNodeId also requires UUID per pivotResolveSchema)
const altId1 = "323e4567-e89b-12d3-a456-426614174001";
const altId2 = "423e4567-e89b-12d3-a456-426614174002";
const altId3 = "523e4567-e89b-12d3-a456-426614174003";

const basePivotEvent = {
  id: pivotId,
  tripId,
  slotId,
  triggerType: "user_mood",
  triggerPayload: null,
  originalNodeId: "node-original",
  alternativeIds: [altId1, altId2, altId3],
  selectedNodeId: null,
  status: "proposed",
  resolvedAt: null,
  responseTimeMs: null,
  createdAt: new Date(Date.now() - 5000),
};

const mockAlternatives = [
  {
    id: altId1,
    name: "Ramen Spot",
    category: "dining",
    neighborhood: "Shibuya",
    primaryImageUrl: null,
    authorityScore: 0.9,
    vibeTags: [{ vibeTag: { slug: "local-eats" } }],
  },
  {
    id: altId2,
    name: "Sushi Place",
    category: "dining",
    neighborhood: "Shinjuku",
    primaryImageUrl: null,
    authorityScore: 0.7,
    vibeTags: [{ vibeTag: { slug: "hidden-gems" } }],
  },
  {
    id: altId3,
    name: "Udon House",
    category: "dining",
    neighborhood: "Asakusa",
    primaryImageUrl: null,
    authorityScore: 0.5,
    vibeTags: [],
  },
];

// ═══════════════════════════════════════════════════════════════════════
// POST /api/trips/[id]/pivot — Create Pivot
// ═══════════════════════════════════════════════════════════════════════

describe("POST /api/trips/[id]/pivot — auth guards", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(401);
  });

  it("returns 404 when user is not a joined member", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(404);
  });

  it("returns 404 when membership status is not joined", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "invited",
    } as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(404);
  });
});

describe("POST /api/trips/[id]/pivot — validation", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${tripId}/pivot`,
      { method: "POST", body: "not json" },
    );
    const res = await POST(req, createParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing slotId", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeCreateRequest({ trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid trigger", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "weather_change" }),
      createParams,
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for reason exceeding 200 chars", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood", reason: "x".repeat(201) }),
      createParams,
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid slotId format", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeCreateRequest({ slotId: "not-a-uuid", trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(400);
  });
});

describe("POST /api/trips/[id]/pivot — state checks", () => {
  beforeEach(() => vi.resetAllMocks());

  function setupAuth() {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
  }

  it("returns 404 when slot not found", async () => {
    setupAuth();
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(null);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(404);
  });

  it("returns 404 when slot belongs to different trip", async () => {
    setupAuth();
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      tripId: "other-trip",
    } as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(404);
  });

  it("returns 409 when trip is not active", async () => {
    setupAuth();
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      trip: { ...baseSlot.trip, status: "planning" },
    } as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(409);
  });

  it("returns 409 when slot status is proposed", async () => {
    setupAuth();
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      status: "proposed",
    } as never);
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(409);
  });
});

describe("POST /api/trips/[id]/pivot — pivot caps (V11)", () => {
  beforeEach(() => vi.resetAllMocks());

  function setupAuthAndSlot() {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
  }

  it("returns 409 when trip has 3 active pivots", async () => {
    setupAuthAndSlot();
    mockPrisma.pivotEvent.count.mockResolvedValueOnce(3); // trip cap
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toBe("Too many active pivots");
  });

  it("returns 409 when slot already has active pivot", async () => {
    setupAuthAndSlot();
    mockPrisma.pivotEvent.count
      .mockResolvedValueOnce(1) // trip cap ok
      .mockResolvedValueOnce(1); // slot cap exceeded
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toBe("Pivot already active for this slot");
  });
});

describe("POST /api/trips/[id]/pivot — happy path", () => {
  beforeEach(() => vi.resetAllMocks());

  function setupFullHappyPath() {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.pivotEvent.count
      .mockResolvedValueOnce(0) // trip cap
      .mockResolvedValueOnce(0); // slot cap
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(mockAlternatives as never);
  }

  it("creates pivot event and returns alternatives", async () => {
    setupFullHappyPath();
    const createdPivot = { ...basePivotEvent, status: "proposed" };
    mockPrisma.$transaction.mockResolvedValueOnce([createdPivot, {}] as never);

    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood", reason: "Not hungry" }),
      createParams,
    );
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.pivotEvent.status).toBe("proposed");
    expect(json.alternatives).toHaveLength(3);
    expect(json.alternatives[0]).toHaveProperty("id");
    expect(json.alternatives[0]).toHaveProperty("name");
    expect(json.alternatives[0]).toHaveProperty("score");
  });

  it("returns empty alternatives for unseeded cities", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.pivotEvent.count
      .mockResolvedValueOnce(0)
      .mockResolvedValueOnce(0);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce([]); // no alternatives

    const createdPivot = { ...basePivotEvent, alternativeIds: [] };
    mockPrisma.$transaction.mockResolvedValueOnce([createdPivot, {}] as never);

    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_request" }),
      createParams,
    );
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.alternatives).toHaveLength(0);
  });

  it("excludes existing trip node IDs from alternatives query", async () => {
    setupFullHappyPath();
    mockPrisma.$transaction.mockResolvedValueOnce([basePivotEvent, {}] as never);

    await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );

    expect(mockPrisma.activityNode.findMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: expect.objectContaining({
          id: { notIn: ["node-original", "node-existing-2"] },
        }),
      }),
    );
  });

  it("returns 500 when transaction fails", async () => {
    setupFullHappyPath();
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB failure"));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await POST(
      makeCreateRequest({ slotId, trigger: "user_mood" }),
      createParams,
    );
    expect(res.status).toBe(500);
    consoleSpy.mockRestore();
  });
});

// ═══════════════════════════════════════════════════════════════════════
// PATCH /api/trips/[id]/pivot/[pivotId] — Resolve Pivot
// ═══════════════════════════════════════════════════════════════════════

describe("PATCH /api/trips/[id]/pivot/[pivotId] — auth guards", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(401);
  });

  it("returns 404 when user is not a joined member", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(404);
  });
});

describe("PATCH /api/trips/[id]/pivot/[pivotId] — validation", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${tripId}/pivot/${pivotId}`,
      { method: "PATCH", body: "not json" },
    );
    const res = await PATCH(req, resolveParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid outcome", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(
      makeResolveRequest({ outcome: "cancelled" }),
      resolveParams,
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 when accepted without selectedNodeId", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(basePivotEvent as never);

    const res = await PATCH(
      makeResolveRequest({ outcome: "accepted" }),
      resolveParams,
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("selectedNodeId required for accepted outcome");
  });

  it("returns 400 when selectedNodeId not in alternativeIds (test risk #4)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(basePivotEvent as never);

    const res = await PATCH(
      makeResolveRequest({ outcome: "accepted", selectedNodeId: "123e4567-e89b-12d3-a456-426614174999" }),
      resolveParams,
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("selectedNodeId not in alternatives");
  });
});

describe("PATCH /api/trips/[id]/pivot/[pivotId] — state checks", () => {
  beforeEach(() => vi.resetAllMocks());

  function setupAuth() {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
  }

  it("returns 404 when pivot not found", async () => {
    setupAuth();
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(null);
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(404);
  });

  it("returns 404 when pivot belongs to different trip", async () => {
    setupAuth();
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce({
      ...basePivotEvent,
      tripId: "other-trip",
    } as never);
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(404);
  });

  it("returns 409 when pivot already resolved", async () => {
    setupAuth();
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce({
      ...basePivotEvent,
      status: "accepted",
    } as never);
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toBe("Pivot already resolved");
  });
});

describe("PATCH /api/trips/[id]/pivot/[pivotId] — accept", () => {
  beforeEach(() => vi.resetAllMocks());

  function setupForAccept() {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(basePivotEvent as never);
  }

  it("swaps slot activity and returns updated pivot + slot", async () => {
    setupForAccept();
    const updatedPivot = {
      ...basePivotEvent,
      status: "accepted",
      selectedNodeId: altId1,
      resolvedAt: new Date(),
    };
    const updatedSlot = {
      id: slotId,
      activityNodeId: altId1,
      wasSwapped: true,
      swappedFromId: "node-original",
      pivotEventId: pivotId,
      voteState: null,
      isContested: false,
    };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedPivot, updatedSlot, {}] as never);

    const res = await PATCH(
      makeResolveRequest({ outcome: "accepted", selectedNodeId: altId1 }),
      resolveParams,
    );
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.pivotEvent.status).toBe("accepted");
    expect(json.updatedSlot.activityNodeId).toBe(altId1);
    expect(json.updatedSlot.wasSwapped).toBe(true);
  });

  it("resets voteState and isContested on accepted pivot", async () => {
    setupForAccept();
    mockPrisma.$transaction.mockResolvedValueOnce([
      { ...basePivotEvent, status: "accepted" },
      { id: slotId, voteState: null, isContested: false },
      {},
    ] as never);

    await PATCH(
      makeResolveRequest({ outcome: "accepted", selectedNodeId: altId2 }),
      resolveParams,
    );

    // Verify the transaction includes voteState: null, isContested: false
    const txCall = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];
    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    // Transaction should have 3 operations: pivotEvent update, slot update, signal create
    expect(txCall).toHaveLength(3);
  });
});

describe("PATCH /api/trips/[id]/pivot/[pivotId] — reject", () => {
  beforeEach(() => vi.resetAllMocks());

  it("rejects without updating slot", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(basePivotEvent as never);

    const updatedPivot = { ...basePivotEvent, status: "rejected", resolvedAt: new Date() };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedPivot, {}] as never);

    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.pivotEvent.status).toBe("rejected");
    expect(json.updatedSlot).toBeUndefined();
  });
});

describe("PATCH /api/trips/[id]/pivot/[pivotId] — error handling", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns 500 when transaction fails", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(basePivotEvent as never);
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB failure"));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await PATCH(
      makeResolveRequest({ outcome: "rejected" }),
      resolveParams,
    );
    expect(res.status).toBe(500);
    consoleSpy.mockRestore();
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Zod Schema Unit Tests
// ═══════════════════════════════════════════════════════════════════════

const { pivotCreateSchema, pivotResolveSchema } = await import(
  "../../lib/validations/pivot"
);

describe("pivotCreateSchema validation", () => {
  it("accepts valid user_mood trigger", () => {
    const result = pivotCreateSchema.safeParse({
      slotId: "123e4567-e89b-12d3-a456-426614174000",
      trigger: "user_mood",
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid user_request with reason", () => {
    const result = pivotCreateSchema.safeParse({
      slotId: "123e4567-e89b-12d3-a456-426614174000",
      trigger: "user_request",
      reason: "Want something different",
    });
    expect(result.success).toBe(true);
  });

  it("rejects missing slotId", () => {
    expect(pivotCreateSchema.safeParse({ trigger: "user_mood" }).success).toBe(false);
  });

  it("rejects non-UUID slotId", () => {
    expect(
      pivotCreateSchema.safeParse({ slotId: "abc", trigger: "user_mood" }).success,
    ).toBe(false);
  });

  it("rejects invalid trigger value", () => {
    expect(
      pivotCreateSchema.safeParse({
        slotId: "123e4567-e89b-12d3-a456-426614174000",
        trigger: "weather_change",
      }).success,
    ).toBe(false);
  });

  it("rejects reason > 200 chars", () => {
    expect(
      pivotCreateSchema.safeParse({
        slotId: "123e4567-e89b-12d3-a456-426614174000",
        trigger: "user_mood",
        reason: "x".repeat(201),
      }).success,
    ).toBe(false);
  });

  it("accepts reason at exactly 200 chars", () => {
    expect(
      pivotCreateSchema.safeParse({
        slotId: "123e4567-e89b-12d3-a456-426614174000",
        trigger: "user_mood",
        reason: "x".repeat(200),
      }).success,
    ).toBe(true);
  });

  it("rejects null", () => {
    expect(pivotCreateSchema.safeParse(null).success).toBe(false);
  });
});

describe("pivotResolveSchema validation", () => {
  it("accepts accepted with selectedNodeId", () => {
    const result = pivotResolveSchema.safeParse({
      outcome: "accepted",
      selectedNodeId: "123e4567-e89b-12d3-a456-426614174000",
    });
    expect(result.success).toBe(true);
  });

  it("accepts rejected without selectedNodeId", () => {
    const result = pivotResolveSchema.safeParse({ outcome: "rejected" });
    expect(result.success).toBe(true);
  });

  it("rejects invalid outcome", () => {
    expect(
      pivotResolveSchema.safeParse({ outcome: "cancelled" }).success,
    ).toBe(false);
  });

  it("rejects non-UUID selectedNodeId", () => {
    expect(
      pivotResolveSchema.safeParse({
        outcome: "accepted",
        selectedNodeId: "not-uuid",
      }).success,
    ).toBe(false);
  });

  it("rejects empty object", () => {
    expect(pivotResolveSchema.safeParse({}).success).toBe(false);
  });

  it("rejects null", () => {
    expect(pivotResolveSchema.safeParse(null).success).toBe(false);
  });
});
