/**
 * Tests for POST /api/trips/[id]/split-day
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
    tripMember: {
      findUnique: vi.fn(),
    },
    itinerarySlot: {
      findMany: vi.fn(),
      updateMany: vi.fn(),
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

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---- Helpers ----

function authedSession(userId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

const TRIP_ID = "11111111-2222-3333-4444-555555555555";
const USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const MEMBER_A = "aaaaaaaa-1111-2222-3333-444444444444";
const MEMBER_B = "bbbbbbbb-1111-2222-3333-444444444444";
const SLOT_1 = "cccccccc-1111-2222-3333-444444444444";
const SLOT_2 = "dddddddd-1111-2222-3333-444444444444";
const SLOT_3 = "eeeeeeee-1111-2222-3333-444444444444";

function makeRequest(body: unknown) {
  return new NextRequest(
    `http://localhost/api/trips/${TRIP_ID}/split-day`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }
  );
}

function setupOrganizer() {
  authedSession(USER_ID);
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    role: "organizer",
    status: "joined",
  } as never);
}

function validBody(overrides: Record<string, unknown> = {}) {
  return {
    dayNumber: 1,
    subgroups: [
      { memberIds: [MEMBER_A], slotIds: [SLOT_1] },
      { memberIds: [MEMBER_B], slotIds: [SLOT_2] },
    ],
    ...overrides,
  };
}

// ====================================================================
// Auth gate tests
// ====================================================================

describe("POST /api/trips/[id]/split-day", () => {
  let handler: typeof import("../../app/api/trips/[id]/split-day/route").POST;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../app/api/trips/[id]/split-day/route");
    handler = mod.POST;
  });

  // ---- Auth gate ----

  it("returns 401 without session", async () => {
    noSession();
    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 404 for non-member", async () => {
    authedSession(USER_ID);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 404 for invited-not-joined member", async () => {
    authedSession(USER_ID);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "invited",
    } as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("proceeds past auth for joined member", async () => {
    authedSession(USER_ID);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    // Should hit 403 (role check), not 404 (auth check)
    expect(res.status).toBe(403);
  });

  // ---- Role tests ----

  it("returns 403 for non-organizer", async () => {
    authedSession(USER_ID);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toBe("Only the organizer can split days");
  });

  it("proceeds for organizer", async () => {
    setupOrganizer();
    // Slots found
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([
      { id: SLOT_1 },
      { id: SLOT_2 },
    ] as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
  });

  // ---- Functional tests ----

  it("returns 200 and updates assignedTo for valid split", async () => {
    setupOrganizer();
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([
      { id: SLOT_1 },
      { id: SLOT_2 },
    ] as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.success).toBe(true);

    // Verify $transaction was called with updateMany operations
    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    const txArg = mockPrisma.$transaction.mock.calls[0][0];
    expect(txArg).toHaveLength(2);
  });

  it("returns 400 for slot from different trip", async () => {
    setupOrganizer();
    // Only 1 slot found (the other belongs to a different trip)
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([
      { id: SLOT_1 },
    ] as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Some slots not found in this trip/day");
  });

  it("returns 400 for slot from different day", async () => {
    setupOrganizer();
    // Only 1 slot found (the other belongs to a different day)
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([
      { id: SLOT_1 },
    ] as never);

    const body = validBody();
    const req = makeRequest(body);
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Some slots not found in this trip/day");
  });

  it("returns 400 for non-existent slotId", async () => {
    setupOrganizer();
    // No slots found
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([] as never);

    const req = makeRequest(validBody());
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Some slots not found in this trip/day");
  });

  it("returns 400 for invalid dayNumber (0)", async () => {
    setupOrganizer();

    const req = makeRequest(validBody({ dayNumber: 0 }));
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for negative dayNumber", async () => {
    setupOrganizer();

    const req = makeRequest(validBody({ dayNumber: -1 }));
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 400 for only 1 subgroup (min 2)", async () => {
    setupOrganizer();

    const req = makeRequest({
      dayNumber: 1,
      subgroups: [{ memberIds: [MEMBER_A], slotIds: [SLOT_1] }],
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for empty memberIds in subgroup", async () => {
    setupOrganizer();

    const req = makeRequest({
      dayNumber: 1,
      subgroups: [
        { memberIds: [], slotIds: [SLOT_1] },
        { memberIds: [MEMBER_B], slotIds: [SLOT_2] },
      ],
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 400 for empty slotIds in subgroup", async () => {
    setupOrganizer();

    const req = makeRequest({
      dayNumber: 1,
      subgroups: [
        { memberIds: [MEMBER_A], slotIds: [] },
        { memberIds: [MEMBER_B], slotIds: [SLOT_2] },
      ],
    });
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("logs BehavioralSignal with correct values", async () => {
    setupOrganizer();
    mockPrisma.itinerarySlot.findMany.mockResolvedValueOnce([
      { id: SLOT_1 },
      { id: SLOT_2 },
    ] as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const req = makeRequest(validBody({ dayNumber: 3 }));
    const res = await handler(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);

    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        userId: USER_ID,
        tripId: TRIP_ID,
        signalType: "share_action",
        signalValue: 1.0,
        tripPhase: "active",
        rawAction: "split_day:3",
      }),
    });
  });
});
