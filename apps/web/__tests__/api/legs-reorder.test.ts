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
    tripLeg: { findMany: vi.fn(), update: vi.fn() },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({ authOptions: {} }));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import(
  "../../app/api/trips/[id]/legs/reorder/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TRIP_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "33333333-3333-3333-3333-333333333333";
const LEG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const LEG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const LEG_C = "cccccccc-cccc-cccc-cccc-cccccccccccc";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeRequest(
  body: unknown
): [NextRequest, { params: { id: string } }] {
  const req = new NextRequest(
    `http://localhost:3000/api/trips/${TRIP_ID}/legs/reorder`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }
  );
  return [req, { params: { id: TRIP_ID } }];
}

function setupAuth() {
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

function setupLegs() {
  (mockPrisma.tripLeg.findMany as any).mockResolvedValue([
    { id: LEG_A },
    { id: LEG_B },
    { id: LEG_C },
  ]);
  (mockPrisma.$transaction as any).mockResolvedValue([{}, {}, {}]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("POST /api/trips/[id]/legs/reorder", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // -------------------------------------------------------------------------
  // Auth & authorization
  // -------------------------------------------------------------------------
  it("returns 401 without session", async () => {
    mockGetServerSession.mockResolvedValue(null);
    const [req, ctx] = makeRequest({ legOrder: [LEG_A] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: "Unauthorized" });
  });

  it("returns 404 if user is not a trip member", async () => {
    mockGetServerSession.mockResolvedValue({
      user: { id: USER_ID },
    } as any);
    (mockPrisma.tripMember.findUnique as any).mockResolvedValue(null);
    const [req, ctx] = makeRequest({ legOrder: [LEG_A] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "Trip not found" });
  });

  it("returns 403 if member is not an organizer", async () => {
    mockGetServerSession.mockResolvedValue({
      user: { id: USER_ID },
    } as any);
    (mockPrisma.tripMember.findUnique as any).mockResolvedValue({
      role: "member",
      status: "joined",
    });
    const [req, ctx] = makeRequest({ legOrder: [LEG_A] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({
      error: "Only the trip organizer can modify legs",
    });
  });

  // -------------------------------------------------------------------------
  // Status gate
  // -------------------------------------------------------------------------
  it("returns 409 if trip status is active", async () => {
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
    const [req, ctx] = makeRequest({ legOrder: [LEG_A] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({
      error: "Legs can only be modified on draft or planning trips",
    });
  });

  // -------------------------------------------------------------------------
  // Body validation
  // -------------------------------------------------------------------------
  it("returns 400 for invalid body (not array of UUIDs)", async () => {
    setupAuth();
    const [req, ctx] = makeRequest({ legOrder: ["not-a-uuid", 42] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details).toBeDefined();
  });

  it("returns 400 if legOrder contains duplicate IDs", async () => {
    setupAuth();
    setupLegs();
    const [req, ctx] = makeRequest({
      legOrder: [LEG_A, LEG_A, LEG_B],
    });

    const res = await POST(req, ctx);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      error: "legOrder contains duplicate IDs",
    });
  });

  it("returns 400 if legOrder is missing existing leg IDs", async () => {
    setupAuth();
    setupLegs();
    // Only send 2 of 3 existing legs
    const [req, ctx] = makeRequest({ legOrder: [LEG_A, LEG_B] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("legOrder is missing existing leg IDs");
    expect(json.missing).toEqual([LEG_C]);
  });

  it("returns 400 if legOrder contains foreign IDs not belonging to trip", async () => {
    setupAuth();
    // Trip only has LEG_A
    (mockPrisma.tripLeg.findMany as any).mockResolvedValue([
      { id: LEG_A },
    ]);
    const foreignId = "dddddddd-dddd-dddd-dddd-dddddddddddd";
    const [req, ctx] = makeRequest({ legOrder: [LEG_A, foreignId] });

    const res = await POST(req, ctx);
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe(
      "legOrder contains IDs that do not belong to this trip"
    );
    expect(json.foreign).toEqual([foreignId]);
  });

  // -------------------------------------------------------------------------
  // Success path
  // -------------------------------------------------------------------------
  it("returns 200 with { reordered: true } on valid reorder", async () => {
    setupAuth();
    setupLegs();
    const [req, ctx] = makeRequest({
      legOrder: [LEG_C, LEG_A, LEG_B],
    });

    const res = await POST(req, ctx);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ reordered: true });
  });

  it("calls $transaction with correct position updates", async () => {
    setupAuth();
    setupLegs();
    const [req, ctx] = makeRequest({
      legOrder: [LEG_C, LEG_A, LEG_B],
    });

    await POST(req, ctx);

    expect(mockPrisma.$transaction).toHaveBeenCalledOnce();
    // The route maps legOrder to prisma.tripLeg.update calls, so
    // $transaction receives the array of update promises.
    // Verify tripLeg.update was called for each leg with correct position.
    expect(mockPrisma.tripLeg.update).toHaveBeenCalledTimes(3);
    expect(mockPrisma.tripLeg.update).toHaveBeenCalledWith({
      where: { id: LEG_C },
      data: { position: 0 },
    });
    expect(mockPrisma.tripLeg.update).toHaveBeenCalledWith({
      where: { id: LEG_A },
      data: { position: 1 },
    });
    expect(mockPrisma.tripLeg.update).toHaveBeenCalledWith({
      where: { id: LEG_B },
      data: { position: 2 },
    });
  });
});
