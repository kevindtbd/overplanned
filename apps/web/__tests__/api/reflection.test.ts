/**
 * Route handler tests for POST /api/trips/[id]/reflection
 * Tests auth guards, validation, status gating, read-merge-write, signal logging, and HTML stripping.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: { findUnique: vi.fn() },
    trip: { findUnique: vi.fn(), update: vi.fn() },
    behavioralSignal: { create: vi.fn() },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import(
  "../../app/api/trips/[id]/reflection/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function makeRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/trips/trip-1/reflection", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

const mockParams = { params: { id: "trip-1" } };
const authedSession = { user: { id: "user-abc" } };

const validBody = {
  ratings: [
    { slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" },
    { slotId: "00000000-0000-0000-0000-000000000002", rating: "skipped" },
  ],
  feedback: "Great trip!",
};

const baseTripWithSlots = {
  status: "completed",
  reflectionData: null,
  slots: [
    { id: "00000000-0000-0000-0000-000000000001", activityNodeId: "an-1" },
    { id: "00000000-0000-0000-0000-000000000002", activityNodeId: "an-2" },
    { id: "00000000-0000-0000-0000-000000000003", activityNodeId: null },
  ],
};

// ─── Auth Guards ──────────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — auth guards", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(401);
  });

  it("returns 404 when user is not a trip member", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 404 when member status is not joined", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "invited",
    } as never);
    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(404);
  });
});

// ─── Validation ───────────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const req = new NextRequest(
      "http://localhost:3000/api/trips/trip-1/reflection",
      { method: "POST", body: "not json" }
    );
    const res = await POST(req, mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for empty ratings array", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(makeRequest({ ratings: [] }), mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid rating value", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "hated" }],
      }),
      mockParams
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for non-uuid slotId", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeRequest({
        ratings: [{ slotId: "not-a-uuid", rating: "loved" }],
      }),
      mockParams
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing ratings field", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(makeRequest({ feedback: "hi" }), mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for feedback over 500 chars", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" }],
        feedback: "a".repeat(501),
      }),
      mockParams
    );
    expect(res.status).toBe(400);
  });
});

// ─── Status Gating ────────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — status gating", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 409 when trip status is planning", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      ...baseTripWithSlots,
      status: "planning",
    } as never);

    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(409);
  });

  it("returns 409 when trip status is draft", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      ...baseTripWithSlots,
      status: "draft",
    } as never);

    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(409);
  });

  it("allows reflection on active trips", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      ...baseTripWithSlots,
      status: "active",
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(200);
  });
});

// ─── Slot Validation ──────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — slot validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 400 when slotId does not belong to trip", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);

    const res = await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-999999999999", rating: "loved" }],
      }),
      mockParams
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.details.ratings[0]).toContain("not found in this trip");
  });
});

// ─── Happy Path ───────────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — happy path", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns { submitted: true } on success", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.submitted).toBe(true);
  });

  it("calls $transaction with trip update + behavioral signals", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    await POST(makeRequest(validBody), mockParams);

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    // 1 trip update + 2 signal creates = 3 operations
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];
    expect(txArgs).toHaveLength(3);
  });

  it("merges with existing reflectionData (does not overwrite)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);

    const existingReflection = {
      "user-other": {
        ratings: [{ slotId: "s1", rating: "loved" }],
        feedback: "nice",
        submittedAt: "2026-01-01T00:00:00.000Z",
      },
    };
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      ...baseTripWithSlots,
      reflectionData: existingReflection,
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    await POST(makeRequest(validBody), mockParams);

    // Verify the trip.update call inside the transaction contains merged data
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];
    // First element should be the trip update
    expect(mockPrisma.trip.update).toHaveBeenCalled();
    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    const mergedData = updateCall.data.reflectionData as Record<string, unknown>;
    // Existing user's data preserved
    expect(mergedData["user-other"]).toBeDefined();
    // New user's data added
    expect(mergedData["user-abc"]).toBeDefined();
  });

  it("accepts request without optional feedback", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    const res = await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "missed" }],
      }),
      mockParams
    );
    expect(res.status).toBe(200);
  });
});

// ─── Signal Logging ───────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — signal logging", () => {
  beforeEach(() => vi.clearAllMocks());

  it("creates behavioral signals with correct signal types and values", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    const body = {
      ratings: [
        { slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" },
        { slotId: "00000000-0000-0000-0000-000000000002", rating: "skipped" },
        { slotId: "00000000-0000-0000-0000-000000000003", rating: "missed" },
      ],
    };

    await POST(makeRequest(body), mockParams);

    // 3 signal creates
    expect(mockPrisma.behavioralSignal.create).toHaveBeenCalledTimes(3);

    const calls = mockPrisma.behavioralSignal.create.mock.calls;

    // loved -> post_loved, 1.0
    expect(calls[0][0].data.signalType).toBe("post_loved");
    expect(calls[0][0].data.signalValue).toBe(1.0);
    expect(calls[0][0].data.activityNodeId).toBe("an-1");

    // skipped -> post_skipped, -0.5
    expect(calls[1][0].data.signalType).toBe("post_skipped");
    expect(calls[1][0].data.signalValue).toBe(-0.5);
    expect(calls[1][0].data.activityNodeId).toBe("an-2");

    // missed -> post_missed, 0.8 (slot 3 has null activityNodeId)
    expect(calls[2][0].data.signalType).toBe("post_missed");
    expect(calls[2][0].data.signalValue).toBe(0.8);
    expect(calls[2][0].data.activityNodeId).toBeNull();
  });

  it("sets tripPhase to post_trip for all signals", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" }],
      }),
      mockParams
    );

    const call = mockPrisma.behavioralSignal.create.mock.calls[0][0];
    expect(call.data.tripPhase).toBe("post_trip");
    expect(call.data.userId).toBe("user-abc");
    expect(call.data.tripId).toBe("trip-1");
  });
});

// ─── HTML Stripping (V7) ─────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — HTML stripping (V7)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("strips HTML tags from feedback before persisting", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockResolvedValueOnce([] as never);

    await POST(
      makeRequest({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" }],
        feedback: '<script>alert("xss")</script>Great trip!',
      }),
      mockParams
    );

    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    const reflection = (updateCall.data.reflectionData as Record<string, { feedback: string }>)["user-abc"];
    expect(reflection.feedback).toBe('alert("xss")Great trip!');
    expect(reflection.feedback).not.toContain("<script>");
  });
});

// ─── Error Handling ───────────────────────────────────────────────────

describe("POST /api/trips/[id]/reflection — error handling", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 500 when transaction fails", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({ status: "joined" } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(baseTripWithSlots as never);
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB failure"));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await POST(makeRequest(validBody), mockParams);
    expect(res.status).toBe(500);
    consoleSpy.mockRestore();
  });
});

// ─── Zod Schema Unit Tests ────────────────────────────────────────────

const { reflectionSchema: schema } = await import(
  "../../lib/validations/reflection"
);

describe("reflectionSchema validation", () => {
  const validRating = { slotId: "00000000-0000-0000-0000-000000000001", rating: "loved" as const };

  it("accepts valid ratings with feedback", () => {
    expect(schema.safeParse({ ratings: [validRating], feedback: "Nice" }).success).toBe(true);
  });

  it("accepts valid ratings without feedback", () => {
    expect(schema.safeParse({ ratings: [validRating] }).success).toBe(true);
  });

  it("accepts all three rating values", () => {
    for (const rating of ["loved", "skipped", "missed"]) {
      expect(
        schema.safeParse({
          ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating }],
        }).success
      ).toBe(true);
    }
  });

  it("rejects invalid rating value", () => {
    expect(
      schema.safeParse({
        ratings: [{ slotId: "00000000-0000-0000-0000-000000000001", rating: "hated" }],
      }).success
    ).toBe(false);
  });

  it("rejects empty ratings", () => {
    expect(schema.safeParse({ ratings: [] }).success).toBe(false);
  });

  it("rejects non-uuid slotId", () => {
    expect(
      schema.safeParse({ ratings: [{ slotId: "abc", rating: "loved" }] }).success
    ).toBe(false);
  });

  it("rejects null body", () => {
    expect(schema.safeParse(null).success).toBe(false);
  });

  it("rejects ratings over 100 items", () => {
    const ratings = Array.from({ length: 101 }, (_, i) => ({
      slotId: `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`,
      rating: "loved",
    }));
    expect(schema.safeParse({ ratings }).success).toBe(false);
  });

  it("strips HTML from feedback via transform", () => {
    const result = schema.parse({
      ratings: [validRating],
      feedback: "<b>bold</b> text",
    });
    expect(result.feedback).toBe("bold text");
  });
});
