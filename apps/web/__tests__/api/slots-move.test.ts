/**
 * Route handler tests for PATCH /api/slots/[slotId]/move
 * Tests auth guards, validation, day/sort moves, locked slot rejection, and signal logging.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    itinerarySlot: {
      findUnique: vi.fn(),
      update: vi.fn(),
      updateMany: vi.fn(),
      aggregate: vi.fn(),
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

vi.mock("uuid", () => ({
  v4: () => "mock-uuid-1",
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { PATCH } = await import("../../app/api/slots/[slotId]/move/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function makeMoveRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/slots/slot-123/move", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

const mockParams = { params: { slotId: "slot-123" } };
const authedSession = { user: { id: "user-abc" } };

const baseSlot = {
  id: "slot-123",
  tripId: "trip-1",
  dayNumber: 1,
  sortOrder: 2,
  isLocked: false,
  trip: {
    startDate: "2026-07-01",
    endDate: "2026-07-04", // 3-day trip
    members: [{ id: "member-1" }],
  },
};

const updatedSlotResponse = {
  id: "slot-123",
  dayNumber: 2,
  sortOrder: 1,
  activityNode: { id: "an-1", name: "Test", category: "dining", latitude: 0, longitude: 0, priceLevel: null, primaryImageUrl: null },
};

describe("PATCH /api/slots/[slotId]/move — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(401);
  });

  it("returns 404 when slot is not found", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(null);

    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 403 when user is not a joined member", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      trip: { ...baseSlot.trip, members: [] },
    } as never);

    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(403);
  });
});

describe("PATCH /api/slots/[slotId]/move — validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when neither dayNumber nor sortOrder is provided", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makeMoveRequest({}), mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 when dayNumber is 0 (below min of 1)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makeMoveRequest({ dayNumber: 0 }), mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 when dayNumber exceeds total days", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);

    const res = await PATCH(makeMoveRequest({ dayNumber: 5 }), mockParams);
    // 3-day trip, day 5 is out of bounds
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toMatch(/dayNumber must be between/);
  });

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const req = new NextRequest("http://localhost:3000/api/slots/slot-123/move", {
      method: "PATCH",
      body: "not json",
    });
    const res = await PATCH(req, mockParams);
    expect(res.status).toBe(400);
  });
});

describe("PATCH /api/slots/[slotId]/move — locked slot", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 409 when slot is locked", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      isLocked: true,
    } as never);

    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toMatch(/locked/i);
  });
});

describe("PATCH /api/slots/[slotId]/move — day move", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("moves slot to target day with max sortOrder + 1", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);

    // $transaction receives a callback; we mock it to execute the callback
    mockPrisma.$transaction.mockImplementation((async (cb: (tx: unknown) => Promise<unknown>) => {
      const tx = {
        itinerarySlot: {
          aggregate: vi.fn().mockResolvedValue({ _max: { sortOrder: 3 } }),
          update: vi.fn().mockResolvedValue(updatedSlotResponse),
          updateMany: vi.fn(),
        },
      };
      return cb(tx);
    }) as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.success).toBe(true);
    expect(json.data).toBeDefined();
  });

  it("logs behavioral signal after move", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.$transaction.mockImplementation((async (cb: (tx: unknown) => Promise<unknown>) => {
      const tx = {
        itinerarySlot: {
          aggregate: vi.fn().mockResolvedValue({ _max: { sortOrder: 1 } }),
          update: vi.fn().mockResolvedValue(updatedSlotResponse),
          updateMany: vi.fn(),
        },
      };
      return cb(tx);
    }) as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);

    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        userId: "user-abc",
        tripId: "trip-1",
        slotId: "slot-123",
        signalType: "pre_trip_reorder",
        rawAction: "moved_to_day_2",
      }),
    });
  });
});

describe("PATCH /api/slots/[slotId]/move — reorder within same day", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reorders slot to target sortOrder within same day", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.$transaction.mockImplementation((async (cb: (tx: unknown) => Promise<unknown>) => {
      const tx = {
        itinerarySlot: {
          updateMany: vi.fn(),
          update: vi.fn().mockResolvedValue({ ...updatedSlotResponse, sortOrder: 1 }),
        },
      };
      return cb(tx);
    }) as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(makeMoveRequest({ sortOrder: 1 }), mockParams);
    expect(res.status).toBe(200);

    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        rawAction: "reordered_to_1",
      }),
    });
  });
});

describe("PATCH /api/slots/[slotId]/move — both dayNumber and sortOrder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("moves to different day at specific position", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.$transaction.mockImplementation((async (cb: (tx: unknown) => Promise<unknown>) => {
      const tx = {
        itinerarySlot: {
          updateMany: vi.fn(),
          update: vi.fn().mockResolvedValue({ ...updatedSlotResponse, dayNumber: 3, sortOrder: 2 }),
        },
      };
      return cb(tx);
    }) as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await PATCH(makeMoveRequest({ dayNumber: 3, sortOrder: 2 }), mockParams);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.success).toBe(true);
  });
});

describe("PATCH /api/slots/[slotId]/move — signal failure is non-blocking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("succeeds even when behavioral signal logging fails", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.$transaction.mockImplementation((async (cb: (tx: unknown) => Promise<unknown>) => {
      const tx = {
        itinerarySlot: {
          aggregate: vi.fn().mockResolvedValue({ _max: { sortOrder: 0 } }),
          update: vi.fn().mockResolvedValue(updatedSlotResponse),
          updateMany: vi.fn(),
        },
      };
      return cb(tx);
    }) as never);
    mockPrisma.behavioralSignal.create.mockRejectedValueOnce(new Error("DB failure"));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await PATCH(makeMoveRequest({ dayNumber: 2 }), mockParams);
    expect(res.status).toBe(200);
    consoleSpy.mockRestore();
  });
});
