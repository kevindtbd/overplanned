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
    tripLeg: { count: vi.fn(), aggregate: vi.fn(), create: vi.fn() },
    userPreference: { findUnique: vi.fn() },
  },
}));

vi.mock("@/lib/auth/config", () => ({ authOptions: {} }));
vi.mock("@/lib/generation/generate-itinerary", () => ({
  generateLegItinerary: vi.fn().mockResolvedValue({}),
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { generateLegItinerary } = await import(
  "@/lib/generation/generate-itinerary"
);
const { POST } = await import("../../app/api/trips/[id]/legs/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);
const mockGenerateLeg = vi.mocked(generateLegItinerary);

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TRIP_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "22222222-2222-2222-2222-222222222222";
const LEG_ID = "33333333-3333-3333-3333-333333333333";

const VALID_BODY = {
  city: "Taipei",
  country: "Taiwan",
  timezone: "Asia/Taipei",
  destination: "Taipei, Taiwan",
  startDate: "2026-04-10T00:00:00.000Z",
  endDate: "2026-04-14T00:00:00.000Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makePostRequest(
  tripId: string,
  body: unknown
): [NextRequest, { params: { id: string } }] {
  const req = new NextRequest(
    `http://localhost:3000/api/trips/${tripId}/legs`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }
  );
  return [req, { params: { id: tripId } }];
}

/** Sets up the full happy-path mock chain so individual tests can override one layer. */
function setupSuccessMocks() {
  mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);

  mockPrisma.tripMember.findUnique.mockResolvedValue({
    role: "organizer",
    status: "joined",
  } as never);

  mockPrisma.trip.findUnique.mockResolvedValue({
    status: "planning",
  } as never);

  mockPrisma.tripLeg.count.mockResolvedValue(2 as never);

  mockPrisma.tripLeg.aggregate.mockResolvedValue({
    _max: { position: 1 },
  } as never);

  mockPrisma.tripLeg.create.mockResolvedValue({
    id: LEG_ID,
    tripId: TRIP_ID,
    position: 2,
    city: VALID_BODY.city,
    country: VALID_BODY.country,
    timezone: VALID_BODY.timezone,
    destination: VALID_BODY.destination,
    startDate: new Date(VALID_BODY.startDate),
    endDate: new Date(VALID_BODY.endDate),
  } as never);

  mockPrisma.userPreference.findUnique.mockResolvedValue(null as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("POST /api/trips/[id]/legs", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockGenerateLeg.mockResolvedValue({} as never);
  });

  // 1. Unauthenticated
  it("returns 401 if no session", async () => {
    mockGetServerSession.mockResolvedValue(null as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Unauthorized");
  });

  // 2. Not a trip member
  it("returns 404 if user is not a trip member", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);
    mockPrisma.tripMember.findUnique.mockResolvedValue(null as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Trip not found");
  });

  // 3. Member status is not "joined"
  it("returns 404 if member status is not joined", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);
    mockPrisma.tripMember.findUnique.mockResolvedValue({
      role: "organizer",
      status: "invited",
    } as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Trip not found");
  });

  // 4. Not an organizer
  it("returns 403 if member role is not organizer", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);
    mockPrisma.tripMember.findUnique.mockResolvedValue({
      role: "viewer",
      status: "joined",
    } as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toMatch(/organizer/i);
  });

  // 5. Trip status is active (not draft/planning)
  it("returns 409 if trip status is active", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);
    mockPrisma.tripMember.findUnique.mockResolvedValue({
      role: "organizer",
      status: "joined",
    } as never);
    mockPrisma.trip.findUnique.mockResolvedValue({
      status: "active",
    } as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toMatch(/draft or planning/i);
  });

  // 6. Invalid body (missing required fields)
  it("returns 400 for invalid body with missing required fields", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } } as never);
    mockPrisma.tripMember.findUnique.mockResolvedValue({
      role: "organizer",
      status: "joined",
    } as never);
    mockPrisma.trip.findUnique.mockResolvedValue({
      status: "planning",
    } as never);

    const [req, ctx] = makePostRequest(TRIP_ID, { city: "Taipei" });
    const res = await POST(req, ctx);

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details).toBeDefined();
  });

  // 7. Max legs reached (8)
  it("returns 409 if trip already has 8 legs", async () => {
    setupSuccessMocks();
    mockPrisma.tripLeg.count.mockResolvedValue(8 as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(409);
    const json = await res.json();
    expect(json.error).toMatch(/maximum 8/i);
  });

  // 8. Success: returns 201 with created leg
  it("returns 201 with created leg on success", async () => {
    setupSuccessMocks();

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.leg).toBeDefined();
    expect(json.leg.id).toBe(LEG_ID);
    expect(json.leg.city).toBe("Taipei");
    expect(json.leg.country).toBe("Taiwan");
    expect(json.leg.tripId).toBe(TRIP_ID);
  });

  // 9. Correct position calculation (max existing + 1)
  it("sets correct position as max existing position + 1", async () => {
    setupSuccessMocks();
    mockPrisma.tripLeg.aggregate.mockResolvedValue({
      _max: { position: 4 },
    } as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    await POST(req, ctx);

    expect(mockPrisma.tripLeg.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          position: 5,
          tripId: TRIP_ID,
          city: "Taipei",
        }),
      })
    );
  });

  // 10. Fire-and-forget generation does not block response
  it("fires generation in background without blocking response", async () => {
    setupSuccessMocks();

    // Make generation hang indefinitely — response should still arrive
    let resolveGeneration: () => void;
    const generationPromise = new Promise<void>((resolve) => {
      resolveGeneration = resolve;
    });
    mockGenerateLeg.mockReturnValue(generationPromise as never);

    const [req, ctx] = makePostRequest(TRIP_ID, VALID_BODY);
    const res = await POST(req, ctx);

    // Response returns immediately even though generation has not resolved
    expect(res.status).toBe(201);
    expect(mockGenerateLeg).toHaveBeenCalledTimes(1);
    expect(mockGenerateLeg).toHaveBeenCalledWith(
      TRIP_ID,
      LEG_ID,
      USER_ID,
      "Taipei",
      "Taiwan",
      expect.any(Date),
      expect.any(Date),
      expect.objectContaining({
        pace: "moderate",
        morningPreference: "mid",
        foodPreferences: [],
      })
    );

    // Clean up hanging promise
    resolveGeneration!();
  });
});
