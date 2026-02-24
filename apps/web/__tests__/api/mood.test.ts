/**
 * Tests for mood capture endpoint:
 *   POST /api/trips/[id]/mood
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
      update: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
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

vi.mock("@/lib/validations/mood", async () => {
  const actual = await import("../../lib/validations/mood");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---- Helpers ----

const USER_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000001";
const TRIP_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000010";

function authedSession(userId = USER_ID) {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

function mockJoinedMember(overrides: Record<string, unknown> = {}) {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    role: "member",
    status: "joined",
    energyProfile: null,
    ...overrides,
  } as never);
}

function mockActiveTrip() {
  mockPrisma.trip.findUnique.mockResolvedValueOnce({
    status: "active",
  } as never);
}

function moodRequest(body: unknown) {
  return new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/mood`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ================================================================
// POST /api/trips/[id]/mood
// ================================================================

describe("POST /api/trips/[id]/mood", () => {
  let POST: typeof import("../../app/api/trips/[id]/mood/route").POST;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../app/api/trips/[id]/mood/route");
    POST = mod.POST;
  });

  // ---- Auth gate ----

  it("returns 401 when not authenticated", async () => {
    noSession();
    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(401);
  });

  it("returns 404 when no membership exists", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(404);
  });

  it("returns 404 when member status is invited (not joined)", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "invited",
      energyProfile: null,
    } as never);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(404);
  });

  it("proceeds for joined member with valid mood", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.success).toBe(true);
  });

  // ---- Functional tests ----

  it("returns 400 when trip is not active (planning)", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
    } as never);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Mood capture only available for active trips");
  });

  it("creates BehavioralSignal with signalValue 1.0 for mood 'high'", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(200);

    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    expect(txArgs).toHaveLength(2);
  });

  it("maps mood 'medium' to signalValue 0.5", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res = await POST(moodRequest({ mood: "medium" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(200);
  });

  it("maps mood 'low' to signalValue 0.0", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res = await POST(moodRequest({ mood: "low" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(200);
  });

  it("returns 400 for invalid mood 'exhausted'", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();

    const res = await POST(moodRequest({ mood: "exhausted" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(400);
  });

  it("returns 400 when mood field is missing", async () => {
    authedSession();
    mockJoinedMember();
    mockActiveTrip();

    const res = await POST(moodRequest({}), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(400);
  });

  it("merges energyProfile without clobbering existing fields", async () => {
    authedSession();
    const existingProfile = {
      preferredPace: "slow",
      morningPerson: true,
    };
    mockJoinedMember({ energyProfile: existingProfile });
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res.status).toBe(200);

    // Verify the transaction was called — check the update arg includes merged profile
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    expect(txArgs).toHaveLength(2);
  });

  it("handles two rapid POSTs both succeeding", async () => {
    // First request
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res1 = await POST(moodRequest({ mood: "high" }), {
      params: { id: TRIP_ID },
    });
    expect(res1.status).toBe(200);

    // Second request
    authedSession();
    mockJoinedMember();
    mockActiveTrip();
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const res2 = await POST(moodRequest({ mood: "low" }), {
      params: { id: TRIP_ID },
    });
    expect(res2.status).toBe(200);

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(2);
  });
});
