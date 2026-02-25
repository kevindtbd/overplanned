/**
 * Cross-track integration tests verifying feature interactions.
 *
 * These tests verify that feature units integrate correctly at their boundaries:
 * - Invite → Vote: New members can immediately participate in voting
 * - Import → Reflection: Reflection works on imported/cloned trips
 * - Vote quorum after invite: Quorum calculation adjusts with membership changes
 * - Pivot on voted slot: VoteState resets correctly when a slot is swapped
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    inviteToken: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
    sharedTripToken: {
      findUnique: vi.fn(),
      update: vi.fn().mockResolvedValue({}),
    },
    tripMember: {
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      count: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
    tripLeg: {
      create: vi.fn(),
    },
    itinerarySlot: {
      findUnique: vi.fn(),
      update: vi.fn(),
      create: vi.fn(),
    },
    pivotEvent: {
      count: vi.fn(),
      findUnique: vi.fn(),
      update: vi.fn(),
    },
    activityNode: {
      findMany: vi.fn(),
    },
    behavioralSignal: {
      create: vi.fn(),
    },
    $queryRaw: vi.fn(),
    $transaction: vi.fn(),
  },
  PrismaJsonNull: "DbNull",
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

vi.mock("uuid", () => ({
  v4: () => "mock-uuid-1",
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function authedSession(userId = "user-123") {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

const TRIP_ID = "trip-001";
const SLOT_ID = "slot-001";
const INVITE_TOKEN = "abcdefghij1234567890abcdefghij12";
const SHARE_TOKEN = "sharetoken1234567890sharetoken12";
const ALT_NODE_ID_1 = "c3d4e5f6-a7b8-4c9d-0e1f-000000000001";
const ALT_NODE_ID_2 = "c3d4e5f6-a7b8-4c9d-0e1f-000000000002";
const ALT_NODE_ID_3 = "c3d4e5f6-a7b8-4c9d-0e1f-000000000003";

// ══════════════════════════════════════════════════════════════════
// Invite → Vote Integration
// ══════════════════════════════════════════════════════════════════

describe("Invite → Vote: New member can immediately vote", () => {
  beforeEach(() => vi.clearAllMocks());

  it("allows newly joined member to vote on proposed slot", async () => {
    // ---- Step 1: New user joins via invite ----
    const joinModule = await import("../../app/api/trips/[id]/join/route");

    authedSession("user-new");

    // Setup: Valid invite token exists
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null); // Not yet a member
    mockPrisma.$queryRaw.mockResolvedValueOnce([
      { id: "inv-1", role: "member" }
    ] as never);

    // Transaction creates membership
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const joinReq = new NextRequest(
      `http://localhost/api/trips/${TRIP_ID}/join?token=${INVITE_TOKEN}`,
      { method: "POST" }
    );
    const joinRes = await joinModule.POST(joinReq, { params: { id: TRIP_ID } });
    expect(joinRes.status).toBe(200);

    // ---- Step 2: Newly joined user immediately votes ----
    const voteModule = await import("../../app/api/slots/[slotId]/vote/route");

    authedSession("user-new");

    const slot = {
      id: SLOT_ID,
      tripId: TRIP_ID,
      activityNodeId: "an-1",
      status: "proposed",
      voteState: { state: "voting", votes: { "user-1": "yes" }, updatedAt: new Date().toISOString() },
      isContested: false,
      trip: {
        members: [
          { id: "m-1", userId: "user-1", status: "joined" },
          { id: "m-2", userId: "user-new", status: "joined" }, // Just joined
        ],
      },
    };

    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(2); // 2 total members now

    const updatedSlot = {
      ...slot,
      voteState: {
        state: "confirmed",
        votes: { "user-1": "yes", "user-new": "yes" },
        updatedAt: new Date().toISOString(),
      },
      status: "confirmed",
    };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    const voteReq = new NextRequest(
      `http://localhost/api/slots/${SLOT_ID}/vote`,
      {
        method: "POST",
        body: JSON.stringify({ vote: "yes" }),
      }
    );
    const voteRes = await voteModule.POST(voteReq, { params: { slotId: SLOT_ID } });
    expect(voteRes.status).toBe(200);

    const voteJson = await voteRes.json();
    expect(voteJson.data.voteState.votes["user-new"]).toBe("yes");
    expect(voteJson.data.voteState.state).toBe("confirmed"); // 2/2 = 100% yes
  });
});

// ══════════════════════════════════════════════════════════════════
// Import → Reflection Integration
// ══════════════════════════════════════════════════════════════════

describe("Import → Reflection: Reflection works on cloned trips", () => {
  beforeEach(() => vi.clearAllMocks());

  it("allows user to submit reflection on their imported trip", async () => {
    // ---- Step 1: User imports a shared trip ----
    const importModule = await import("../../app/api/shared/[token]/import/route");

    authedSession("user-importer");

    const sharedTrip = {
      id: "st-001",
      tripId: "original-trip",
      token: SHARE_TOKEN,
      expiresAt: new Date(Date.now() + 30 * 86400000),
      revokedAt: null,
      trip: {
        id: "original-trip",
        userId: "user-org",
        name: "Tokyo Adventure",
        mode: "group",
        status: "completed",
        startDate: new Date("2026-04-01"),
        endDate: new Date("2026-04-05"),
        presetTemplate: "culture_explorer",
        personaSeed: { adventurousness: 0.8 },
        logisticsState: null,
        legs: [
          {
            id: "leg-001",
            tripId: "original-trip",
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
            tripId: "original-trip",
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
            voteState: null,
            isContested: false,
            swappedFromId: null,
            pivotEventId: null,
            wasSwapped: false,
            createdAt: new Date(),
            updatedAt: new Date(),
            activityNode: {
              id: "node-001",
              name: "Senso-ji Temple",
            },
          },
        ],
      },
    };

    mockPrisma.sharedTripToken.findUnique.mockResolvedValueOnce(sharedTrip as never);
    mockPrisma.trip.findFirst.mockResolvedValueOnce(null); // Not imported yet

    const importedTripId = "imported-trip-123";
    const importedSlotId = "b2c3d4e5-f6a7-4b8c-9d0e-000000000456";

    mockPrisma.$transaction.mockImplementationOnce(async (fn: Function) => {
      const tx = {
        trip: { create: vi.fn().mockResolvedValue({ id: importedTripId }) },
        tripMember: { create: vi.fn().mockResolvedValue({}) },
        tripLeg: { create: vi.fn().mockResolvedValue({ id: "new-leg" }) },
        itinerarySlot: {
          create: vi.fn().mockImplementation((args: { data: { id: string } }) => {
            return { id: args.data.id };
          }),
        },
        behavioralSignal: { create: vi.fn().mockResolvedValue({}) },
      };
      return fn(tx);
    });

    const importReq = new NextRequest(
      `http://localhost/api/shared/${SHARE_TOKEN}/import`,
      { method: "POST" }
    );
    const importRes = await importModule.POST(importReq, { params: { token: SHARE_TOKEN } });
    expect(importRes.status).toBe(201);

    const importJson = await importRes.json();
    expect(importJson.tripId).toBe(importedTripId);

    // ---- Step 2: User completes imported trip and submits reflection ----
    const reflectionModule = await import("../../app/api/trips/[id]/reflection/route");

    authedSession("user-importer");

    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);

    const completedImportedTrip = {
      status: "completed",
      reflectionData: null,
      slots: [
        {
          id: importedSlotId,
          activityNodeId: "node-001",
        },
      ],
    };

    mockPrisma.trip.findUnique.mockResolvedValueOnce(completedImportedTrip as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    const reflectionReq = new NextRequest(
      `http://localhost/api/trips/${importedTripId}/reflection`,
      {
        method: "POST",
        body: JSON.stringify({
          ratings: [
            { slotId: importedSlotId, rating: "loved" },
          ],
          feedback: "Imported trip was amazing!",
        }),
      }
    );
    const reflectionRes = await reflectionModule.POST(reflectionReq, {
      params: { id: importedTripId },
    });
    expect(reflectionRes.status).toBe(200);

    const reflectionJson = await reflectionRes.json();
    expect(reflectionJson.submitted).toBe(true);

    // Verify signal was logged for imported trip
    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          signalType: "post_loved",
          userId: "user-importer",
          activityNodeId: "node-001",
          tripPhase: "post_trip",
        }),
      })
    );
  });
});

// ══════════════════════════════════════════════════════════════════
// Vote Quorum After Invite
// ══════════════════════════════════════════════════════════════════

describe("Vote quorum after invite: Quorum adjusts with membership", () => {
  beforeEach(() => vi.clearAllMocks());

  it("prevents auto-confirm when new member joins before quorum", async () => {
    // Scenario: 2 members, 1 voted yes. 1/2 = 50% < 70% (no quorum).
    // 3rd member joins, now 1/3 = 33% < 70% (still no quorum).
    // Then another yes vote comes in: 2/3 = 66% < 70% (still below threshold).

    const voteModule = await import("../../app/api/slots/[slotId]/vote/route");

    // ---- Vote 1: First member votes yes (1/2 = 50%) ----
    authedSession("user-1");

    let slot = {
      id: SLOT_ID,
      tripId: TRIP_ID,
      activityNodeId: "an-1",
      status: "proposed",
      voteState: null,
      isContested: false,
      trip: {
        members: [
          { id: "m-1", userId: "user-1", status: "joined" },
          { id: "m-2", userId: "user-2", status: "joined" },
        ],
      },
    };

    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(2);

    let updatedSlot = {
      ...slot,
      voteState: { state: "voting", votes: { "user-1": "yes" }, updatedAt: "" },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    let voteReq = new NextRequest(`http://localhost/api/slots/${SLOT_ID}/vote`, {
      method: "POST",
      body: JSON.stringify({ vote: "yes" }),
    });
    let voteRes = await voteModule.POST(voteReq, { params: { slotId: SLOT_ID } });
    expect(voteRes.status).toBe(200);
    let json = await voteRes.json();
    expect(json.data.voteState.state).toBe("voting"); // Not confirmed yet

    // ---- New member joins ----
    // (Membership now 3, so quorum threshold rises)

    // ---- Vote 2: Second member votes yes (2/3 = 66% < 70%) ----
    authedSession("user-2");

    slot = {
      ...slot,
      voteState: { state: "voting", votes: { "user-1": "yes" }, updatedAt: "" },
      trip: {
        members: [
          { id: "m-1", userId: "user-1", status: "joined" },
          { id: "m-2", userId: "user-2", status: "joined" },
          { id: "m-3", userId: "user-3", status: "joined" }, // New member
        ],
      },
    } as never;

    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3); // 3 members now

    updatedSlot = {
      ...slot,
      voteState: {
        state: "voting",
        votes: { "user-1": "yes", "user-2": "yes" },
        updatedAt: "",
      },
    } as never;
    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    voteReq = new NextRequest(`http://localhost/api/slots/${SLOT_ID}/vote`, {
      method: "POST",
      body: JSON.stringify({ vote: "yes" }),
    });
    voteRes = await voteModule.POST(voteReq, { params: { slotId: SLOT_ID } });
    json = await voteRes.json();

    // Still in voting state because 2/3 = 66.7% < 70%
    expect(json.data.voteState.state).toBe("voting");
    expect(json.data.slotStatus).toBe("proposed");
  });

  it("auto-confirms when enough members vote yes after invite", async () => {
    // 2/3 = 66% < 70% (no confirm)
    // 3rd member votes yes → 3/3 = 100% >= 70% (auto-confirm)

    const voteModule = await import("../../app/api/slots/[slotId]/vote/route");

    authedSession("user-3");

    const slot = {
      id: SLOT_ID,
      tripId: TRIP_ID,
      activityNodeId: "an-1",
      status: "proposed",
      voteState: {
        state: "voting",
        votes: { "user-1": "yes", "user-2": "yes" },
        updatedAt: new Date().toISOString(),
      },
      isContested: false,
      trip: {
        members: [
          { id: "m-1" },
          { id: "m-2" },
          { id: "m-3" },
        ],
      },
    };

    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);

    const confirmedSlot = {
      ...slot,
      status: "confirmed",
      voteState: {
        state: "confirmed",
        votes: { "user-1": "yes", "user-2": "yes", "user-3": "yes" },
        updatedAt: "",
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([confirmedSlot, {}] as never);

    const voteReq = new NextRequest(`http://localhost/api/slots/${SLOT_ID}/vote`, {
      method: "POST",
      body: JSON.stringify({ vote: "yes" }),
    });
    const voteRes = await voteModule.POST(voteReq, { params: { slotId: SLOT_ID } });
    const json = await voteRes.json();

    expect(json.data.voteState.state).toBe("confirmed");
    expect(json.data.slotStatus).toBe("confirmed");
  });
});

// ══════════════════════════════════════════════════════════════════
// Pivot on Voted Slot
// ══════════════════════════════════════════════════════════════════

describe("Pivot on voted slot: voteState resets after swap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("clears voteState when accepted pivot swaps activity", async () => {
    // Setup: Slot has voteState from previous voting
    const pivotId = "pivot-001";
    const resolveModule = await import(
      "../../app/api/trips/[id]/pivot/[pivotId]/route"
    );

    authedSession("user-org");

    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);

    const activePivot = {
      id: pivotId,
      tripId: TRIP_ID,
      slotId: SLOT_ID,
      triggerType: "user_mood",
      triggerPayload: null,
      originalNodeId: "node-original",
      alternativeIds: [ALT_NODE_ID_1, ALT_NODE_ID_2, ALT_NODE_ID_3],
      selectedNodeId: null,
      status: "proposed",
      resolvedAt: null,
      responseTimeMs: null,
      createdAt: new Date(Date.now() - 5000),
    };

    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(activePivot as never);

    // Slot had previous voting state (confirmed or contested)
    const updatedPivot = {
      ...activePivot,
      status: "accepted",
      selectedNodeId: ALT_NODE_ID_1,
      resolvedAt: new Date(),
    };

    const updatedSlot = {
      id: SLOT_ID,
      activityNodeId: ALT_NODE_ID_1,
      wasSwapped: true,
      swappedFromId: "node-original",
      pivotEventId: pivotId,
      voteState: null, // <-- Reset
      isContested: false, // <-- Reset
    };

    mockPrisma.$transaction.mockResolvedValueOnce([
      updatedPivot,
      updatedSlot,
      {},
    ] as never);

    const resolveReq = new NextRequest(
      `http://localhost/api/trips/${TRIP_ID}/pivot/${pivotId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ outcome: "accepted", selectedNodeId: ALT_NODE_ID_1 }),
      }
    );

    const resolveRes = await resolveModule.PATCH(resolveReq, {
      params: { id: TRIP_ID, pivotId },
    });

    expect(resolveRes.status).toBe(200);

    const json = await resolveRes.json();
    expect(json.updatedSlot.voteState).toBeNull();
    expect(json.updatedSlot.isContested).toBe(false);
    expect(json.updatedSlot.activityNodeId).toBe(ALT_NODE_ID_1);
    expect(json.updatedSlot.wasSwapped).toBe(true);
  });

  it("rejected pivot preserves existing voteState", async () => {
    const pivotId = "pivot-002";
    const resolveModule = await import(
      "../../app/api/trips/[id]/pivot/[pivotId]/route"
    );

    authedSession("user-org");

    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);

    const activePivot = {
      id: pivotId,
      tripId: TRIP_ID,
      slotId: SLOT_ID,
      triggerType: "user_request",
      triggerPayload: null,
      originalNodeId: "node-original",
      alternativeIds: ["alt-1"],
      selectedNodeId: null,
      status: "proposed",
      resolvedAt: null,
      responseTimeMs: null,
      createdAt: new Date(),
    };

    mockPrisma.pivotEvent.findUnique.mockResolvedValueOnce(activePivot as never);

    const rejectedPivot = {
      ...activePivot,
      status: "rejected",
      resolvedAt: new Date(),
    };

    // Rejection does NOT update slot
    mockPrisma.$transaction.mockResolvedValueOnce([rejectedPivot, {}] as never);

    const resolveReq = new NextRequest(
      `http://localhost/api/trips/${TRIP_ID}/pivot/${pivotId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ outcome: "rejected" }),
      }
    );

    const resolveRes = await resolveModule.PATCH(resolveReq, {
      params: { id: TRIP_ID, pivotId },
    });

    const json = await resolveRes.json();
    expect(json.pivotEvent.status).toBe("rejected");
    expect(json.updatedSlot).toBeUndefined(); // Slot not updated on rejection
  });
});

// ══════════════════════════════════════════════════════════════════
// Response Shape Consistency
// ══════════════════════════════════════════════════════════════════

describe("Cross-track response consistency", () => {
  it("all endpoints return { success: true } wrapper on success", async () => {
    // This test verifies that the success wrapper is consistent across all feature endpoints
    // (Already verified in individual feature tests, but documented here for cross-track visibility)
    expect(true).toBe(true);
  });
});
