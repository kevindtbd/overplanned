/**
 * Route handler tests for /api/trips (GET/POST)
 * Tests auth bypass, database errors, and response shape
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// Mock next-auth BEFORE importing route
vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

// Mock prisma BEFORE importing route
vi.mock("@/lib/prisma", () => ({
  prisma: {
    tripMember: {
      findMany: vi.fn(),
    },
    trip: {
      create: vi.fn(),
    },
  },
}));

// Mock authOptions
vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

// Mock uuid
vi.mock("uuid", () => ({
  v4: vi.fn(() => "mock-uuid"),
}));

// Mock validations - use real implementation
vi.mock("@/lib/validations/trip", async () => {
  // Import using relative path since @ alias doesn't work in vitest
  const actual = await import("../../lib/validations/trip");
  return actual;
});

// Import after mocks are set up
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { GET, POST } = await import("../../app/api/trips/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

describe("GET /api/trips", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 if session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const req = new NextRequest("http://localhost:3000/api/trips");
    const response = await GET(req);

    expect(response.status).toBe(401);
    const json = await response.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 401 if session.user is undefined", async () => {
    mockGetServerSession.mockResolvedValueOnce({} as never);
    const req = new NextRequest("http://localhost:3000/api/trips");
    const response = await GET(req);

    expect(response.status).toBe(401);
    const json = await response.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 200 with empty trips array if no memberships found", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.tripMember.findMany.mockResolvedValueOnce([]);

    const req = new NextRequest("http://localhost:3000/api/trips");
    const response = await GET(req);

    expect(response.status).toBe(200);
    const json = await response.json();
    expect(json.trips).toEqual([]);
    expect(mockPrisma.tripMember.findMany).toHaveBeenCalledWith({
      where: { userId: "user-123" },
      select: expect.any(Object),
      orderBy: expect.any(Object),
    });
  });

  it("returns 200 with trips array when memberships exist", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const mockMemberships = [
      {
        role: "organizer",
        status: "active",
        joinedAt: new Date("2026-01-01T00:00:00.000Z"),
        trip: {
          id: "trip-1",
          name: "Kyoto Trip",
          destination: "Kyoto, Japan",
          city: "Kyoto",
          country: "Japan",
          mode: "solo",
          status: "draft",
          startDate: new Date("2026-04-01T00:00:00.000Z"),
          endDate: new Date("2026-04-07T00:00:00.000Z"),
          planningProgress: 0.5,
          createdAt: new Date("2026-01-01T00:00:00.000Z"),
          _count: { members: 1 },
        },
      },
    ];
    mockPrisma.tripMember.findMany.mockResolvedValueOnce(mockMemberships as never);

    const req = new NextRequest("http://localhost:3000/api/trips");
    const response = await GET(req);

    expect(response.status).toBe(200);
    const json = await response.json();
    expect(json.trips).toHaveLength(1);
    expect(json.trips[0]).toMatchObject({
      id: "trip-1",
      name: "Kyoto Trip",
      memberCount: 1,
      myRole: "organizer",
      myStatus: "active",
    });
  });

  it("returns 500 if database throws an error", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.tripMember.findMany.mockRejectedValueOnce(
      new Error("DB connection failed")
    );

    const req = new NextRequest("http://localhost:3000/api/trips");
    const response = await GET(req);

    expect(response.status).toBe(500);
    const json = await response.json();
    expect(json.error).toBe("Internal server error");
  });
});

describe("POST /api/trips", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 if session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const response = await POST(req);

    expect(response.status).toBe(401);
    const json = await response.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 400 if request body is invalid JSON", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: "not valid json{",
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Invalid JSON");
  });

  it("returns 400 if Zod validation fails (missing destination)", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({
        city: "Kyoto",
        country: "Japan",
        timezone: "Asia/Tokyo",
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-07T00:00:00.000Z",
        mode: "solo",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details.destination).toBeDefined();
  });

  it("returns 400 if mode is invalid", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({
        destination: "Kyoto, Japan",
        city: "Kyoto",
        country: "Japan",
        timezone: "Asia/Tokyo",
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-07T00:00:00.000Z",
        mode: "invalid-mode",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details.mode).toBeDefined();
  });

  it("returns 201 with created trip on success (no optional fields)", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const mockTrip = {
      id: "trip-abc",
      userId: "user-123",
      name: null,
      destination: "Kyoto, Japan",
      city: "Kyoto",
      country: "Japan",
      timezone: "Asia/Tokyo",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-07T00:00:00.000Z"),
      mode: "solo",
      presetTemplate: null,
      personaSeed: undefined,
      members: [
        {
          id: "member-xyz",
          userId: "user-123",
          role: "organizer",
          status: "active",
        },
      ],
    };
    mockPrisma.trip.create.mockResolvedValueOnce(mockTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({
        destination: "Kyoto, Japan",
        city: "Kyoto",
        country: "Japan",
        timezone: "Asia/Tokyo",
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-07T00:00:00.000Z",
        mode: "solo",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    const json = await response.json();
    expect(json.trip).toMatchObject({
      id: "trip-abc",
      destination: "Kyoto, Japan",
      mode: "solo",
    });
    expect(json.trip.members).toHaveLength(1);
    expect(json.trip.members[0].role).toBe("organizer");
  });

  it("returns 201 with created trip including optional name", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const mockTrip = {
      id: "trip-abc",
      userId: "user-123",
      name: "Cherry Blossom Trip",
      destination: "Kyoto, Japan",
      city: "Kyoto",
      country: "Japan",
      timezone: "Asia/Tokyo",
      startDate: new Date("2026-04-01T00:00:00.000Z"),
      endDate: new Date("2026-04-07T00:00:00.000Z"),
      mode: "group",
      presetTemplate: null,
      personaSeed: undefined,
      members: [
        {
          id: "member-xyz",
          userId: "user-123",
          role: "organizer",
          status: "active",
        },
      ],
    };
    mockPrisma.trip.create.mockResolvedValueOnce(mockTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({
        name: "Cherry Blossom Trip",
        destination: "Kyoto, Japan",
        city: "Kyoto",
        country: "Japan",
        timezone: "Asia/Tokyo",
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-07T00:00:00.000Z",
        mode: "group",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    const json = await response.json();
    expect(json.trip.name).toBe("Cherry Blossom Trip");
    expect(json.trip.mode).toBe("group");
  });

  it("returns 500 if database throws an error during creation", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.create.mockRejectedValueOnce(
      new Error("DB constraint violation")
    );

    const req = new NextRequest("http://localhost:3000/api/trips", {
      method: "POST",
      body: JSON.stringify({
        destination: "Kyoto, Japan",
        city: "Kyoto",
        country: "Japan",
        timezone: "Asia/Tokyo",
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-07T00:00:00.000Z",
        mode: "solo",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(500);
    const json = await response.json();
    expect(json.error).toBe("Internal server error");
  });
});
