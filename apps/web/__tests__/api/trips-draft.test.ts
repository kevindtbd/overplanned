import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    trip: {
      count: vi.fn(),
      create: vi.fn(),
      findUnique: vi.fn(),
    },
    tripLeg: {
      createMany: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("uuid", () => ({
  v4: vi.fn(() => "mock-uuid"),
}));

vi.mock("@/lib/validations/trip", async () => {
  const actual = await import("../../lib/validations/trip");
  return actual;
});

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import("../../app/api/trips/draft/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

const validLeg = {
  city: "Tokyo",
  country: "Japan",
  timezone: "Asia/Tokyo",
  destination: "Tokyo, Japan",
  startDate: "2026-06-01T00:00:00.000Z",
  endDate: "2026-06-07T00:00:00.000Z",
};

const validDraftPayload = {
  startDate: "2026-06-01T00:00:00.000Z",
  endDate: "2026-06-07T00:00:00.000Z",
  legs: [validLeg],
};

const mockDraftTrip = {
  id: "mock-uuid",
  userId: "user-123",
  startDate: new Date("2026-06-01T00:00:00.000Z"),
  endDate: new Date("2026-06-07T00:00:00.000Z"),
  mode: "solo",
  status: "draft",
  name: null,
  presetTemplate: null,
  personaSeed: null,
  members: [
    {
      id: "mock-uuid",
      userId: "user-123",
      role: "organizer",
      status: "joined",
    },
  ],
  legs: [
    {
      id: "mock-uuid",
      tripId: "mock-uuid",
      position: 0,
      city: "Tokyo",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Tokyo, Japan",
      startDate: new Date("2026-06-01T00:00:00.000Z"),
      endDate: new Date("2026-06-07T00:00:00.000Z"),
    },
  ],
};

describe("POST /api/trips/draft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 for unauthenticated requests", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(401);
    const json = await response.json();
    expect(json.error).toBe("Unauthorized");
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({} as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(401);
  });

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: "not-json{",
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Invalid JSON");
  });

  it("returns 400 when legs array is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { legs, ...payload } = validDraftPayload;
    void legs;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when city is missing from leg", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { city, ...legWithoutCity } = validLeg;
    void city;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({ ...validDraftPayload, legs: [legWithoutCity] }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when destination is missing from leg", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { destination, ...legWithoutDest } = validLeg;
    void destination;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({ ...validDraftPayload, legs: [legWithoutDest] }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when startDate is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { startDate, ...payload } = validDraftPayload;
    void startDate;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details.startDate).toBeDefined();
  });

  it("returns 400 when endDate is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { endDate, ...payload } = validDraftPayload;
    void endDate;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details.endDate).toBeDefined();
  });

  it("returns 400 when country is missing from leg", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const { country, ...legWithoutCountry } = validLeg;
    void country;

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({ ...validDraftPayload, legs: [legWithoutCountry] }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 when legs array is empty", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({ ...validDraftPayload, legs: [] }),
    });
    const response = await POST(req);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 429 when user has 10 or more existing drafts", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(10 as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(429);
    const json = await response.json();
    expect(json.error).toMatch(/too many saved drafts/i);
  });

  it("enforces draft cap at exactly 10, not 9", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(9 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
  });

  it("creates draft trip with status draft", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    const json = await response.json();
    expect(json.trip.status).toBe("draft");
  });

  it("sets mode to solo automatically", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    await POST(req);

    expect(mockPrisma.trip.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ mode: "solo" }),
      })
    );
  });

  it("creates TripMember with role organizer and status joined", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    const json = await response.json();
    expect(json.trip.members).toHaveLength(1);
    expect(json.trip.members[0].role).toBe("organizer");
    expect(json.trip.members[0].status).toBe("joined");

    expect(mockPrisma.trip.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          members: {
            create: expect.objectContaining({
              role: "organizer",
              status: "joined",
            }),
          },
        }),
      })
    );
  });

  it("ignores template field if provided — schema strips it", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({
        ...validDraftPayload,
        presetTemplate: "adventure",
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    expect(mockPrisma.trip.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.not.objectContaining({ presetTemplate: "adventure" }),
      })
    );
  });

  it("ignores personaSeed field if provided — schema strips it", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify({
        ...validDraftPayload,
        personaSeed: { pace: "packed" },
      }),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    expect(mockPrisma.trip.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.not.objectContaining({ personaSeed: { pace: "packed" } }),
      })
    );
  });

  it("returns 500 if database throws during creation", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockRejectedValueOnce(new Error("DB constraint violation"));

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(500);
    const json = await response.json();
    expect(json.error).toBe("Internal server error");
  });

  it("counts only the authed user's drafts for cap check", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(0 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    await POST(req);

    expect(mockPrisma.trip.count).toHaveBeenCalledWith({
      where: { userId: "user-123", status: "draft" },
    });
  });

  it("returns 201 with trip object on successful creation", async () => {
    mockGetServerSession.mockResolvedValueOnce({
      user: { id: "user-123" },
    } as never);
    mockPrisma.trip.count.mockResolvedValueOnce(2 as never);
    mockPrisma.trip.create.mockResolvedValueOnce(mockDraftTrip as never);
    mockPrisma.tripLeg.createMany.mockResolvedValueOnce({ count: 1 } as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockDraftTrip as never);

    const req = new NextRequest("http://localhost:3000/api/trips/draft", {
      method: "POST",
      body: JSON.stringify(validDraftPayload),
    });
    const response = await POST(req);

    expect(response.status).toBe(201);
    const json = await response.json();
    expect(json.trip).toBeDefined();
    // Leg data is now accessible via trip.legs[0]
    expect(json.trip.legs[0].city).toBe("Tokyo");
    expect(json.trip.legs[0].country).toBe("Japan");
    expect(json.trip.legs[0].destination).toBe("Tokyo, Japan");
  });
});
