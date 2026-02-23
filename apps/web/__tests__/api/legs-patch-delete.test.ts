import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: { findUnique: vi.fn() },
    trip: { findUnique: vi.fn() },
    tripLeg: {
      findUnique: vi.fn(),
      findMany: vi.fn(),
      count: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
    itinerarySlot: { count: vi.fn(), deleteMany: vi.fn() },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({ authOptions: {} }));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { PATCH, DELETE } = await import(
  "../../app/api/trips/[id]/legs/[legId]/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const TRIP_ID = "11111111-1111-1111-1111-111111111111";
const LEG_ID = "22222222-2222-2222-2222-222222222222";
const USER_ID = "33333333-3333-3333-3333-333333333333";

function makePatchRequest(
  body: unknown
): [NextRequest, { params: { id: string; legId: string } }] {
  const req = new NextRequest(
    `http://localhost:3000/api/trips/${TRIP_ID}/legs/${LEG_ID}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }
  );
  return [req, { params: { id: TRIP_ID, legId: LEG_ID } }];
}

function makeDeleteRequest(): [
  NextRequest,
  { params: { id: string; legId: string } },
] {
  const req = new NextRequest(
    `http://localhost:3000/api/trips/${TRIP_ID}/legs/${LEG_ID}`,
    { method: "DELETE" }
  );
  return [req, { params: { id: TRIP_ID, legId: LEG_ID } }];
}

function setupOrganizerAuth() {
  mockGetServerSession.mockResolvedValue({
    user: { id: USER_ID },
  } as any);
  (mockPrisma.tripMember.findUnique as any).mockResolvedValue({
    role: "organizer",
    status: "joined",
  });
  (mockPrisma.trip.findUnique as any).mockResolvedValue({
    status: "planning",
  });
}

// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.resetAllMocks();
});

// ===========================================================================
// PATCH /api/trips/[id]/legs/[legId]
// ===========================================================================
describe("PATCH /api/trips/[id]/legs/[legId]", () => {
  it("returns 401 without a session", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const [req, ctx] = makePatchRequest({ city: "Osaka" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 404 if the leg does not exist", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue(null);

    const [req, ctx] = makePatchRequest({ city: "Osaka" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Leg not found");
  });

  it("returns 404 if leg.tripId does not match params.id (IDOR guard)", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", // different trip
    });

    const [req, ctx] = makePatchRequest({ city: "Osaka" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Leg not found");
  });

  it("returns 400 for invalid body (validation failure)", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });

    // city is a string with max length, empty string should fail min(1) via cityNameSchema
    const [req, ctx] = makePatchRequest({ city: "" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details).toBeDefined();
  });

  it("returns 200 with the updated leg on success", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });

    const updatedLeg = {
      id: LEG_ID,
      tripId: TRIP_ID,
      city: "Osaka",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Osaka, Japan",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-05T00:00:00.000Z"),
      position: 0,
    };
    (mockPrisma.tripLeg.update as any).mockResolvedValue(updatedLeg);

    const [req, ctx] = makePatchRequest({
      city: "Osaka",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Osaka, Japan",
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-05T00:00:00.000Z",
    });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.leg).toBeDefined();
    expect(json.leg.city).toBe("Osaka");
    expect(mockPrisma.tripLeg.update).toHaveBeenCalledOnce();
  });

  it("only updates provided fields (partial update)", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });

    const updatedLeg = {
      id: LEG_ID,
      tripId: TRIP_ID,
      city: "Kyoto",
      country: "Japan",
      position: 1,
    };
    (mockPrisma.tripLeg.update as any).mockResolvedValue(updatedLeg);

    // Only send city — other fields should not be in the update data
    const [req, ctx] = makePatchRequest({ city: "Kyoto" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(200);
    const updateCall = (mockPrisma.tripLeg.update as any).mock.calls[0][0];
    expect(updateCall.data).toEqual({ city: "Kyoto" });
    // country, timezone, destination, startDate, endDate should NOT be present
    expect(updateCall.data.country).toBeUndefined();
    expect(updateCall.data.timezone).toBeUndefined();
    expect(updateCall.data.destination).toBeUndefined();
    expect(updateCall.data.startDate).toBeUndefined();
    expect(updateCall.data.endDate).toBeUndefined();
  });

  it("returns 403 for non-organizer members", async () => {
    mockGetServerSession.mockResolvedValue({
      user: { id: USER_ID },
    } as any);
    (mockPrisma.tripMember.findUnique as any).mockResolvedValue({
      role: "member",
      status: "joined",
    });

    const [req, ctx] = makePatchRequest({ city: "Osaka" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toMatch(/organizer/i);
  });

  it("returns 409 for trips not in draft or planning status", async () => {
    mockGetServerSession.mockResolvedValue({
      user: { id: USER_ID },
    } as any);
    (mockPrisma.tripMember.findUnique as any).mockResolvedValue({
      role: "organizer",
      status: "joined",
    });
    (mockPrisma.trip.findUnique as any).mockResolvedValue({
      status: "active",
    });

    const [req, ctx] = makePatchRequest({ city: "Osaka" });
    const res = await PATCH(req, ctx);

    expect(res.status).toBe(409);
  });
});

// ===========================================================================
// DELETE /api/trips/[id]/legs/[legId]
// ===========================================================================
describe("DELETE /api/trips/[id]/legs/[legId]", () => {
  it("returns 401 without a session", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 404 if the leg does not exist", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue(null);

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Leg not found");
  });

  it("returns 404 if leg.tripId does not match params.id (IDOR guard)", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    });

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Leg not found");
  });

  it("returns 409 if only 1 leg remains (cannot delete last leg)", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });
    (mockPrisma.tripLeg.count as any).mockResolvedValue(1);

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toBe("Cannot delete the last leg");
  });

  it("returns 200 with deletedSlotCount on success", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });
    (mockPrisma.tripLeg.count as any).mockResolvedValue(3);
    (mockPrisma.itinerarySlot.count as any).mockResolvedValue(7);

    // $transaction executes the callback with the prisma client
    (mockPrisma.$transaction as any).mockImplementation((fn: any) =>
      fn(mockPrisma)
    );
    (mockPrisma.itinerarySlot.deleteMany as any).mockResolvedValue({
      count: 7,
    });
    (mockPrisma.tripLeg.delete as any).mockResolvedValue({ id: LEG_ID });
    (mockPrisma.tripLeg.findMany as any).mockResolvedValue([
      { id: "44444444-4444-4444-4444-444444444444" },
      { id: "55555555-5555-5555-5555-555555555555" },
    ]);
    (mockPrisma.tripLeg.update as any).mockResolvedValue({});

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.deleted).toBe(true);
    expect(json.deletedSlotCount).toBe(7);
  });

  it("uses $transaction for atomic delete and renumber", async () => {
    setupOrganizerAuth();
    (mockPrisma.tripLeg.findUnique as any).mockResolvedValue({
      id: LEG_ID,
      tripId: TRIP_ID,
    });
    (mockPrisma.tripLeg.count as any).mockResolvedValue(2);
    (mockPrisma.itinerarySlot.count as any).mockResolvedValue(0);

    const txCalls: string[] = [];
    (mockPrisma.$transaction as any).mockImplementation(async (fn: any) => {
      const txProxy = {
        itinerarySlot: {
          deleteMany: vi.fn().mockImplementation(async (...args: any[]) => {
            txCalls.push("deleteMany");
            return { count: 0 };
          }),
        },
        tripLeg: {
          delete: vi.fn().mockImplementation(async (...args: any[]) => {
            txCalls.push("deleteLeg");
            return { id: LEG_ID };
          }),
          findMany: vi.fn().mockImplementation(async () => {
            txCalls.push("findMany");
            return [{ id: "44444444-4444-4444-4444-444444444444" }];
          }),
          update: vi.fn().mockImplementation(async () => {
            txCalls.push("updatePosition");
            return {};
          }),
        },
      };
      return fn(txProxy);
    });

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(200);
    expect(mockPrisma.$transaction).toHaveBeenCalledOnce();
    // Verify the ordering: slots deleted, then leg deleted, then renumber
    expect(txCalls).toEqual([
      "deleteMany",
      "deleteLeg",
      "findMany",
      "updatePosition",
    ]);
  });

  it("returns 403 for non-organizer members", async () => {
    mockGetServerSession.mockResolvedValue({
      user: { id: USER_ID },
    } as any);
    (mockPrisma.tripMember.findUnique as any).mockResolvedValue({
      role: "member",
      status: "joined",
    });

    const [req, ctx] = makeDeleteRequest();
    const res = await DELETE(req, ctx);

    expect(res.status).toBe(403);
  });
});
