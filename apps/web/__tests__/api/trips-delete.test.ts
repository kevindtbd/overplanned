/**
 * Route handler tests for DELETE /api/trips/[id]
 * Tests auth guards, draft-only restriction, and signal/event cleanup before deletion.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: {
      findUnique: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
      delete: vi.fn(),
    },
    behavioralSignal: {
      deleteMany: vi.fn(),
    },
    pivotEvent: {
      deleteMany: vi.fn(),
    },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/generation/promote-draft", () => ({
  promoteDraftToPlanning: vi.fn(),
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { DELETE } = await import("../../app/api/trips/[id]/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

function makeDeleteRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/trips/trip-123", {
    method: "DELETE",
  });
}

const mockParams = { params: { id: "trip-123" } };
const authedSession = { user: { id: "user-abc" } };
const organizerMembership = { role: "organizer", status: "joined" };

describe("DELETE /api/trips/[id] — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await DELETE(makeDeleteRequest(), mockParams);
    expect(res.status).toBe(401);
  });

  it("returns 404 when caller is not a TripMember", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    const res = await DELETE(makeDeleteRequest(), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 404 when member status is not joined", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "invited",
    } as never);
    const res = await DELETE(makeDeleteRequest(), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 403 when caller is not an organizer", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);
    const res = await DELETE(makeDeleteRequest(), mockParams);
    expect(res.status).toBe(403);
  });
});

describe("DELETE /api/trips/[id] — status restrictions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const nonDraftStatuses = ["planning", "active", "completed", "archived"];

  for (const status of nonDraftStatuses) {
    it(`returns 409 for ${status} trip`, async () => {
      mockGetServerSession.mockResolvedValueOnce(authedSession as never);
      mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
      mockPrisma.trip.findUnique.mockResolvedValueOnce({ status } as never);

      const res = await DELETE(makeDeleteRequest(), mockParams);
      expect(res.status).toBe(409);
      const json = await res.json();
      expect(json.error).toMatch(/draft/i);
    });
  }
});

describe("DELETE /api/trips/[id] — successful deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 200 on draft trip and calls $transaction with cleanup", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({ status: "draft" } as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const res = await DELETE(makeDeleteRequest(), mockParams);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.deleted).toBe(true);
  });

  it("calls $transaction with BehavioralSignal.deleteMany, PivotEvent.deleteMany, then trip.delete", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({ status: "draft" } as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    await DELETE(makeDeleteRequest(), mockParams);

    // $transaction is called with an array of 3 operations
    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    const transactionArgs = mockPrisma.$transaction.mock.calls[0][0];
    expect(Array.isArray(transactionArgs)).toBe(true);
    expect(transactionArgs).toHaveLength(3);

    // Verify the individual operations were called with correct args
    expect(mockPrisma.behavioralSignal.deleteMany).toHaveBeenCalledWith({
      where: { tripId: "trip-123" },
    });
    expect(mockPrisma.pivotEvent.deleteMany).toHaveBeenCalledWith({
      where: { tripId: "trip-123" },
    });
    expect(mockPrisma.trip.delete).toHaveBeenCalledWith({
      where: { id: "trip-123" },
    });
  });
});
