/**
 * Route handler tests for PATCH /api/trips/[id]
 * Tests state machine enforcement, field-level write guards, and draft->planning generation trigger.
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
      update: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/generation/promote-draft", () => ({
  promoteDraftToPlanning: vi.fn(),
}));

vi.mock("@/lib/trip-status", () => ({
  shouldAutoTransition: vi.fn(() => false),
  validateTransition: vi.fn((from: string, to: string) => {
    const allowed: Record<string, string[]> = {
      draft: ["planning"],
      planning: ["active"],
      active: ["completed"],
      completed: ["archived"],
    };
    return (allowed[from] ?? []).includes(to);
  }),
  getWritableFields: vi.fn((status: string) => {
    const fields: Record<string, Set<string>> = {
      draft: new Set(["name", "status", "startDate", "endDate", "mode", "presetTemplate", "personaSeed"]),
      planning: new Set(["name", "status", "startDate", "endDate", "planningProgress"]),
      active: new Set(["name", "status", "planningProgress"]),
      completed: new Set(["status"]),
      archived: new Set([]),
    };
    return fields[status] ?? new Set();
  }),
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { promoteDraftToPlanning } = await import("@/lib/generation/promote-draft");
const { PATCH } = await import("../../app/api/trips/[id]/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);
const mockPromoteDraft = vi.mocked(promoteDraftToPlanning);

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/trips/trip-123", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

const mockParams = { params: { id: "trip-123" } };

const authedSession = { user: { id: "user-abc" } };

const organizerMembership = { role: "organizer", status: "joined" };

describe("PATCH /api/trips/[id] — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ name: "New Name" }), mockParams);
    expect(res.status).toBe(401);
  });

  it("returns 404 when caller is not a TripMember", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ name: "New Name" }), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 404 when member status is not joined", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "organizer",
      status: "invited",
    } as never);
    const res = await PATCH(makePatchRequest({ name: "New Name" }), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 403 when caller is not an organizer", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "joined",
    } as never);
    const res = await PATCH(makePatchRequest({ name: "New Name" }), mockParams);
    expect(res.status).toBe(403);
  });
});

describe("PATCH /api/trips/[id] — state machine: invalid transitions return 409", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const invalidTransitions = [
    { current: "draft", requested: "active" },
    { current: "draft", requested: "completed" },
    { current: "draft", requested: "archived" },
    { current: "planning", requested: "draft" },
    { current: "planning", requested: "completed" },
    { current: "active", requested: "planning" },
    { current: "active", requested: "draft" },
    { current: "completed", requested: "planning" },
    { current: "completed", requested: "active" },
    { current: "archived", requested: "completed" },
    { current: "archived", requested: "planning" },
  ];

  for (const { current, requested } of invalidTransitions) {
    it(`rejects ${current} -> ${requested} with 409`, async () => {
      mockGetServerSession.mockResolvedValueOnce(authedSession as never);
      mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
      mockPrisma.trip.findUnique.mockResolvedValueOnce({
        status: current,
        startDate: new Date("2027-01-01T00:00:00.000Z"),
        endDate: new Date("2027-01-07T00:00:00.000Z"),
      } as never);

      const res = await PATCH(makePatchRequest({ status: requested }), mockParams);
      expect(res.status).toBe(409);
      const json = await res.json();
      expect(json.error).toBe("Invalid status transition");
    });
  }
});

describe("PATCH /api/trips/[id] — state machine: valid transitions succeed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("allows planning -> active transition", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "active" } as never);

    const res = await PATCH(makePatchRequest({ status: "active" }), mockParams);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.trip).toBeDefined();
  });

  it("allows active -> completed transition", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "active",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "completed" } as never);

    const res = await PATCH(makePatchRequest({ status: "completed" }), mockParams);
    expect(res.status).toBe(200);
  });

  it("allows completed -> archived transition", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "completed",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "archived" } as never);

    const res = await PATCH(makePatchRequest({ status: "archived" }), mockParams);
    expect(res.status).toBe(200);
  });
});

describe("PATCH /api/trips/[id] — field-level write guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("allows startDate when trip is in planning status", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", name: "New Name" } as never);

    const res = await PATCH(
      makePatchRequest({ name: "New Name", startDate: "2027-01-01T00:00:00.000Z" }),
      mockParams
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    expect(updateCall.data.startDate).toEqual(new Date("2027-01-01T00:00:00.000Z"));
    expect(updateCall.data.name).toBe("New Name");
  });

  it("silently ignores mode when trip is in active status", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "active",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", name: "Updated" } as never);

    const res = await PATCH(
      makePatchRequest({ name: "Updated", mode: "group" }),
      mockParams
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    expect(updateCall.data.mode).toBeUndefined();
  });

  it("ignores all fields for archived trips (terminal state)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "archived",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123" } as never);

    const res = await PATCH(
      makePatchRequest({ name: "Trying to rename archived trip" }),
      mockParams
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    expect(updateCall.data.name).toBeUndefined();
  });

  it("allows all draft-writable fields through when trip is in draft status", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "draft",
      startDate: new Date("2027-06-01T00:00:00.000Z"),
      endDate: new Date("2027-06-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "draft" } as never);

    const res = await PATCH(
      makePatchRequest({
        name: "Renamed Draft",
        startDate: "2027-06-01T00:00:00.000Z",
        endDate: "2027-06-07T00:00:00.000Z",
        mode: "group",
        presetTemplate: "adventure",
        personaSeed: { pace: "packed" },
      }),
      mockParams
    );
    expect(res.status).toBe(200);

    const updateCall = mockPrisma.trip.update.mock.calls[0][0];
    expect(updateCall.data.name).toBe("Renamed Draft");
    expect(updateCall.data.startDate).toBeInstanceOf(Date);
    expect(updateCall.data.endDate).toBeInstanceOf(Date);
    expect(updateCall.data.mode).toBe("group");
    expect(updateCall.data.presetTemplate).toBe("adventure");
    expect(updateCall.data.personaSeed).toEqual({ pace: "packed" });
  });
});

describe("PATCH /api/trips/[id] — date range validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects partial date update that exceeds 14 nights", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-07T00:00:00.000Z"),
    } as never);

    const res = await PATCH(
      makePatchRequest({ endDate: "2026-04-20T00:00:00.000Z" }),
      mockParams
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toMatch(/exceed 14 nights/i);
  });

  it("rejects date update where end <= start", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-07T00:00:00.000Z"),
    } as never);

    const res = await PATCH(
      makePatchRequest({ endDate: "2026-03-30T00:00:00.000Z" }),
      mockParams
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toMatch(/after start date/i);
  });

  it("allows non-date PATCH on an existing trip with >14 day range (no regression)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-05-01T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", name: "Renamed" } as never);

    const res = await PATCH(makePatchRequest({ name: "Renamed" }), mockParams);
    expect(res.status).toBe(200);
  });

  it("allows valid date update within 14 nights", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123" } as never);

    const res = await PATCH(
      makePatchRequest({
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-15T00:00:00.000Z",
      }),
      mockParams
    );
    expect(res.status).toBe(200);
  });
});

describe("PATCH /api/trips/[id] — draft -> planning triggers generation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls promoteDraftToPlanning and returns { trip, generated } shape on draft -> planning", async () => {
    const mockGeneratedTrip = {
      id: "trip-123",
      status: "planning",
      slots: [{ id: "slot-1" }],
    };
    const mockGenerationResult = { slotsCreated: 4, source: "seeded" };

    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "draft",
      startDate: new Date("2027-06-01T00:00:00.000Z"),
      endDate: new Date("2027-06-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "planning" } as never);
    mockPromoteDraft.mockResolvedValueOnce({
      trip: mockGeneratedTrip,
      generated: mockGenerationResult,
    } as never);

    const res = await PATCH(makePatchRequest({ status: "planning" }), mockParams);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.trip).toMatchObject({ id: "trip-123", status: "planning" });
    expect(json.generated).toMatchObject({ slotsCreated: 4, source: "seeded" });
    expect(mockPromoteDraft).toHaveBeenCalledWith("trip-123", "user-abc");
  });

  it("returns graceful fallback if generation throws after promotion", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "draft",
      startDate: new Date("2027-06-01T00:00:00.000Z"),
      endDate: new Date("2027-06-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "planning" } as never);
    mockPromoteDraft.mockRejectedValueOnce(new Error("Generation failed"));

    const res = await PATCH(makePatchRequest({ status: "planning" }), mockParams);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.trip).toBeDefined();
    expect(json.generated).toMatchObject({ slotsCreated: 0, source: "empty" });
  });

  it("does NOT call promoteDraftToPlanning for non-promotion status updates", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(organizerMembership as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      status: "planning",
      startDate: new Date("2027-01-01T00:00:00.000Z"),
      endDate: new Date("2027-01-07T00:00:00.000Z"),
    } as never);
    mockPrisma.trip.update.mockResolvedValueOnce({ id: "trip-123", status: "active" } as never);

    const res = await PATCH(makePatchRequest({ status: "active" }), mockParams);
    expect(res.status).toBe(200);
    expect(mockPromoteDraft).not.toHaveBeenCalled();

    const json = await res.json();
    expect(json.generated).toBeUndefined();
  });
});
