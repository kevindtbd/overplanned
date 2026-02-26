/**
 * Tests for POST /api/signals/behavioral
 *
 * Covers: allowlist, clamping, rate limiting, weather context, candidate fields.
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
    behavioralSignal: {
      create: vi.fn(),
    },
    tripLeg: {
      findFirst: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("uuid", () => ({
  v4: () => "a1b2c3d4-0000-4000-8000-000000000099",
}));

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

// ---- Helpers ----

const USER_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000001";
const TRIP_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000010";
const SLOT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000020";
const ACTIVITY_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000030";
const CANDIDATE_SET_ID = "a1b2c3d4-e5f6-4a7b-8c9d-000000000040";
const CANDIDATE_ID_1 = "a1b2c3d4-e5f6-4a7b-8c9d-000000000050";
const CANDIDATE_ID_2 = "a1b2c3d4-e5f6-4a7b-8c9d-000000000060";

function authedSession(userId = USER_ID) {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

function signalRequest(body: unknown) {
  return new NextRequest("http://localhost:3000/api/signals/behavioral", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function validPayload(overrides: Record<string, unknown> = {}) {
  return {
    tripId: TRIP_ID,
    slotId: SLOT_ID,
    activityNodeId: ACTIVITY_ID,
    signalType: "slot_confirmed",
    signalValue: 0.8,
    tripPhase: "pre_trip",
    rawAction: "user confirmed slot",
    ...overrides,
  };
}

// ================================================================
// POST /api/signals/behavioral
// ================================================================

describe("POST /api/signals/behavioral", () => {
  let POST: typeof import("../../../app/api/signals/behavioral/route").POST;
  let rateLimitMap: typeof import("../../../app/api/signals/behavioral/_rate-limit").rateLimitMap;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../../app/api/signals/behavioral/route");
    POST = mod.POST;
    const rl = await import("../../../app/api/signals/behavioral/_rate-limit");
    rateLimitMap = rl.rateLimitMap;
    // Clear rate limit state between tests
    rateLimitMap.clear();
  });

  // ---- Auth ----

  it("returns 401 when not authenticated", async () => {
    noSession();
    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(401);
  });

  // ---- Signal type allowlist ----

  it("accepts valid signal type 'slot_confirmed'", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.success).toBe(true);
  });

  it("accepts valid signal type 'discover_swipe_right'", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalType: "discover_swipe_right" }))
    );
    expect(res.status).toBe(200);
  });

  it("accepts valid signal type 'pre_trip_slot_swap'", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalType: "pre_trip_slot_swap" }))
    );
    expect(res.status).toBe(200);
  });

  it("accepts valid signal type 'pre_trip_reorder'", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalType: "pre_trip_reorder" }))
    );
    expect(res.status).toBe(200);
  });

  it("returns 400 for unknown signal type", async () => {
    authedSession();

    const res = await POST(
      signalRequest(validPayload({ signalType: "totally_fake_signal" }))
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toContain("Unknown signalType");
  });

  it("returns 400 for signal type that exists in DB enum but not allowlist", async () => {
    authedSession();

    // dwell_time is in the SignalType enum but NOT in the behavioral route allowlist
    const res = await POST(
      signalRequest(validPayload({ signalType: "dwell_time" }))
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toContain("Unknown signalType");
  });

  // ---- signalValue clamping ----

  it("clamps signalValue above 1.0 to 1.0", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalValue: 5.0 }))
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.signalValue).toBe(1.0);
  });

  it("clamps signalValue below -1.0 to -1.0", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalValue: -3.5 }))
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.signalValue).toBe(-1.0);
  });

  it("does not clamp signalValue within [-1, 1]", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ signalValue: 0.5 }))
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.signalValue).toBe(0.5);
  });

  // ---- Rate limiting ----

  it("allows up to 120 signals per window", async () => {
    // Send 120 signals -- all should succeed
    for (let i = 0; i < 120; i++) {
      authedSession();
      mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
      mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);
    }

    for (let i = 0; i < 120; i++) {
      const res = await POST(signalRequest(validPayload()));
      expect(res.status).toBe(200);
    }
  });

  it("returns 429 on the 121st signal in the same window", async () => {
    // Pre-fill the rate limit map to 120
    rateLimitMap.set(USER_ID, { count: 120, windowStart: Date.now() });

    authedSession();
    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(429);
    const json = await res.json();
    expect(json.error).toContain("Too many signals");
  });

  it("resets rate limit after window expires", async () => {
    // Set an expired window
    rateLimitMap.set(USER_ID, {
      count: 999,
      windowStart: Date.now() - 61_000, // 61 seconds ago
    });

    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);
  });

  // ---- Weather context auto-attach ----

  it("attaches weather context when trip has a city and dates", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce({
      city: "Tokyo",
      startDate: new Date("2026-07-15"),
    } as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    const metadata = createCall.data.metadata as Record<string, unknown>;
    expect(metadata).toBeDefined();

    const weatherCtx = metadata.weatherContext as Record<string, unknown>;
    expect(weatherCtx.city).toBe("Tokyo");
    expect(weatherCtx.month).toBe(7);
    expect(weatherCtx.season).toBe("summer");
  });

  it("attaches winter season for January dates", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce({
      city: "Sapporo",
      startDate: new Date("2026-01-10"),
    } as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    const metadata = createCall.data.metadata as Record<string, unknown>;
    const weatherCtx = metadata.weatherContext as Record<string, unknown>;
    expect(weatherCtx.season).toBe("winter");
    expect(weatherCtx.month).toBe(1);
  });

  it("attaches spring season for April dates", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce({
      city: "Kyoto",
      startDate: new Date("2026-04-05"),
    } as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    const metadata = createCall.data.metadata as Record<string, unknown>;
    const weatherCtx = metadata.weatherContext as Record<string, unknown>;
    expect(weatherCtx.season).toBe("spring");
  });

  it("attaches autumn season for October dates", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce({
      city: "Seoul",
      startDate: new Date("2026-10-15"),
    } as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    const metadata = createCall.data.metadata as Record<string, unknown>;
    const weatherCtx = metadata.weatherContext as Record<string, unknown>;
    expect(weatherCtx.season).toBe("autumn");
  });

  it("does not attach weather context when no tripId provided", async () => {
    authedSession();
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(validPayload({ tripId: null }))
    );
    expect(res.status).toBe(200);

    // tripLeg.findFirst should NOT have been called
    expect(mockPrisma.tripLeg.findFirst).not.toHaveBeenCalled();
  });

  it("does not attach weather context when trip has no legs", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    // metadata should be undefined (no enrichments, no client metadata)
    expect(createCall.data.metadata).toBeUndefined();
  });

  it("still writes signal when weather lookup throws", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockRejectedValueOnce(
      new Error("DB connection lost")
    );
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);
    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledTimes(1);
  });

  // ---- candidateSetId and candidateIds persistence ----

  it("persists candidateSetId when provided", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(
        validPayload({ candidateSetId: CANDIDATE_SET_ID })
      )
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.candidateSetId).toBe(CANDIDATE_SET_ID);
  });

  it("persists candidateIds array when provided", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(
        validPayload({
          candidateSetId: CANDIDATE_SET_ID,
          candidateIds: [CANDIDATE_ID_1, CANDIDATE_ID_2],
        })
      )
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.candidateIds).toEqual([
      CANDIDATE_ID_1,
      CANDIDATE_ID_2,
    ]);
  });

  it("sets candidateSetId to null when not provided", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(createCall.data.candidateSetId).toBeNull();
  });

  // ---- Client metadata merge ----

  it("merges client metadata with weather context", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce({
      city: "Tokyo",
      startDate: new Date("2026-07-15"),
    } as never);
    mockPrisma.behavioralSignal.create.mockResolvedValueOnce({} as never);

    const res = await POST(
      signalRequest(
        validPayload({
          metadata: { source: "discover_feed", position: 3 },
        })
      )
    );
    expect(res.status).toBe(200);

    const createCall = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    const metadata = createCall.data.metadata as Record<string, unknown>;
    expect(metadata.source).toBe("discover_feed");
    expect(metadata.position).toBe(3);
    expect(metadata.weatherContext).toBeDefined();
  });

  // ---- Validation edge cases ----

  it("returns 400 for invalid JSON body", async () => {
    authedSession();
    const req = new NextRequest(
      "http://localhost:3000/api/signals/behavioral",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "not-json",
      }
    );
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing rawAction", async () => {
    authedSession();

    const res = await POST(
      signalRequest(validPayload({ rawAction: "" }))
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid tripPhase", async () => {
    authedSession();

    const res = await POST(
      signalRequest(validPayload({ tripPhase: "mid_trip" }))
    );
    expect(res.status).toBe(400);
  });

  it("returns 500 when DB create fails", async () => {
    authedSession();
    mockPrisma.tripLeg.findFirst.mockResolvedValueOnce(null);
    mockPrisma.behavioralSignal.create.mockRejectedValueOnce(
      new Error("DB write failed")
    );

    const res = await POST(signalRequest(validPayload()));
    expect(res.status).toBe(500);
  });
});
