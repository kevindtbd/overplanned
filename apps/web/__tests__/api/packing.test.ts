/**
 * Tests for packing list endpoints:
 *   POST  /api/trips/[id]/packing — Generate packing list
 *   PATCH /api/trips/[id]/packing — Toggle item checked state
 *
 * Uses Vitest with mocked Prisma + next-auth + Anthropic SDK.
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
    },
    trip: {
      findUnique: vi.fn(),
      update: vi.fn(),
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

vi.mock("@/lib/rate-limit", () => ({
  rateLimit: vi.fn().mockReturnValue(null),
  rateLimitPresets: {
    llm: { limit: 3, windowMs: 3600000 },
  },
}));

vi.mock("@anthropic-ai/sdk", () => {
  const mockCreate = vi.fn();
  return {
    default: class {
      messages = { create: mockCreate };
    },
    __mockCreate: mockCreate,
  };
});

vi.mock("@/lib/validations/packing", async () => {
  const actual = await import("../../lib/validations/packing");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { rateLimit } = await import("@/lib/rate-limit");
const { __mockCreate: mockLLMCreate } = await import("@anthropic-ai/sdk") as { __mockCreate: ReturnType<typeof vi.fn> };

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);
const mockRateLimit = vi.mocked(rateLimit);

// ---- Helpers ----

function authedSession(userId = "user-123") {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

const TRIP_ID = "trip-001";

function mockJoinedMember(role = "member") {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    role,
    status: "joined",
  } as never);
}

function mockTrip(overrides: Record<string, unknown> = {}) {
  return {
    id: TRIP_ID,
    packingList: null,
    startDate: new Date("2026-06-01"),
    endDate: new Date("2026-06-07"),
    presetTemplate: "foodie",
    personaSeed: { pace: "moderate" },
    legs: [
      { destination: "Tokyo, Japan", city: "Tokyo", country: "Japan" },
    ],
    ...overrides,
  };
}

function mockLLMResponse(items: Array<{ text: string; category: string }>) {
  const responseItems = items.map((item, i) => ({
    id: String(i + 1),
    text: item.text,
    category: item.category,
    checked: false,
  }));
  mockLLMCreate.mockResolvedValueOnce({
    content: [
      {
        type: "text",
        text: JSON.stringify({ items: responseItems }),
      },
    ],
  });
}

const ITEM_ID_1 = "a1b2c3d4-e5f6-4a7b-8c9d-000000000001";
const ITEM_ID_2 = "a1b2c3d4-e5f6-4a7b-8c9d-000000000002";
const ITEM_ID_3 = "a1b2c3d4-e5f6-4a7b-8c9d-000000000003";

const MOCK_PACKING_LIST = {
  items: [
    { id: ITEM_ID_1, text: "Sunscreen SPF 50+", category: "essentials", checked: false },
    { id: ITEM_ID_2, text: "Passport", category: "documents", checked: true },
    { id: ITEM_ID_3, text: "Phone charger", category: "tech", checked: false },
  ],
  generatedAt: "2026-02-22T00:00:00.000Z",
  model: "claude-haiku-4-5-20251001",
};

// ================================================================
// POST /api/trips/[id]/packing
// ================================================================

describe("POST /api/trips/[id]/packing", () => {
  let POST: typeof import("../../app/api/trips/[id]/packing/route").POST;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockRateLimit.mockReturnValue(null);
    const mod = await import("../../app/api/trips/[id]/packing/route");
    POST = mod.POST;
  });

  it("returns 401 when not authenticated", async () => {
    noSession();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 429 when rate limited", async () => {
    authedSession();
    const { NextResponse } = await import("next/server");
    mockRateLimit.mockReturnValueOnce(
      NextResponse.json({ error: "Too many requests" }, { status: 429 })
    );

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(429);
  });

  it("returns 404 when user is not a joined member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 404 when member status is not joined", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      role: "member",
      status: "invited",
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns existing packing list without regenerating", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(
      mockTrip({ packingList: MOCK_PACKING_LIST }) as never
    );

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.packingList).toEqual(MOCK_PACKING_LIST);
    expect(mockLLMCreate).not.toHaveBeenCalled();
  });

  it("regenerates when regenerate flag is true", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(
      mockTrip({ packingList: MOCK_PACKING_LIST }) as never
    );
    mockLLMResponse([
      { text: "New item 1", category: "essentials" },
      { text: "New item 2", category: "clothing" },
    ]);
    mockPrisma.trip.update.mockResolvedValueOnce({} as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ regenerate: true }),
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    expect(mockLLMCreate).toHaveBeenCalledOnce();
    const json = await res.json();
    expect(json.packingList.items).toHaveLength(2);
    // All items should be unchecked on regeneration
    expect(json.packingList.items.every((i: { checked: boolean }) => !i.checked)).toBe(true);
  });

  it("generates packing list when none exists", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockTrip() as never);
    mockLLMResponse([
      { text: "Sunscreen", category: "essentials" },
      { text: "T-shirts", category: "clothing" },
      { text: "Passport", category: "documents" },
    ]);
    mockPrisma.trip.update.mockResolvedValueOnce({} as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.packingList.items).toHaveLength(3);
    expect(json.packingList.model).toBe("claude-haiku-4-5-20251001");
    expect(json.packingList.generatedAt).toBeDefined();
    // Each item should have a UUID
    for (const item of json.packingList.items) {
      expect(item.id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
      );
    }
  });

  it("caps items at 30", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockTrip() as never);

    const manyItems = Array.from({ length: 40 }, (_, i) => ({
      text: `Item ${i + 1}`,
      category: "misc",
    }));
    mockLLMResponse(manyItems);
    mockPrisma.trip.update.mockResolvedValueOnce({} as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.packingList.items).toHaveLength(30);
  });

  it("returns 502 when LLM returns invalid JSON", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockTrip() as never);
    mockLLMCreate.mockResolvedValueOnce({
      content: [{ type: "text", text: "not valid json" }],
    });

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(502);
  });

  it("returns 502 when LLM output fails schema validation", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(mockTrip() as never);
    mockLLMCreate.mockResolvedValueOnce({
      content: [
        {
          type: "text",
          text: JSON.stringify({
            items: [{ id: "1", text: "Item", category: "invalid_cat", checked: false }],
          }),
        },
      ],
    });

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(502);
  });

  it("returns 400 when trip has no legs", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(
      mockTrip({ legs: [] }) as never
    );

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("sanitizes destination in LLM prompt", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce(
      mockTrip({
        legs: [
          {
            destination: '<script>alert("xss")</script>Tokyo',
            city: "Tokyo<img>",
            country: "Japan\x00",
          },
        ],
      }) as never
    );
    mockLLMResponse([{ text: "Item", category: "essentials" }]);
    mockPrisma.trip.update.mockResolvedValueOnce({} as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "POST",
    });
    const res = await POST(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);

    // Verify the prompt was sanitized
    const callArgs = mockLLMCreate.mock.calls[0][0];
    const userMessage = callArgs.messages[0].content as string;
    expect(userMessage).not.toContain("<script>");
    expect(userMessage).not.toContain("<img>");
    expect(userMessage).not.toContain("\x00");
  });
});

// ================================================================
// PATCH /api/trips/[id]/packing
// ================================================================

describe("PATCH /api/trips/[id]/packing", () => {
  let PATCH: typeof import("../../app/api/trips/[id]/packing/route").PATCH;

  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("../../app/api/trips/[id]/packing/route");
    PATCH = mod.PATCH;
  });

  it("returns 401 when not authenticated", async () => {
    noSession();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: "item-1", checked: true }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 400 for invalid body", async () => {
    authedSession();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: "not-a-uuid", checked: true }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 400 when checked is missing", async () => {
    authedSession();
    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: "550e8400-e29b-41d4-a716-446655440000" }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("returns 404 when not a member", async () => {
    authedSession();
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
        checked: true,
      }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 404 when no packing list exists", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: null,
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
        checked: true,
      }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toContain("No packing list");
  });

  it("returns 404 when item not found in list", async () => {
    authedSession();
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: MOCK_PACKING_LIST,
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
        checked: true,
      }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Item not found");
  });

  it("checks an item and logs packing_checked signal", async () => {
    authedSession("user-123");
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...MOCK_PACKING_LIST },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, checked: true }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.packingList.items[0].checked).toBe(true);

    // Verify $transaction was called with both update and signal create
    expect(mockPrisma.$transaction).toHaveBeenCalledOnce();
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown[];
    expect(txArgs).toHaveLength(2);
  });

  it("unchecks an item and logs packing_unchecked signal", async () => {
    authedSession("user-123");
    mockJoinedMember();
    const listWithChecked = {
      ...MOCK_PACKING_LIST,
      items: MOCK_PACKING_LIST.items.map((i) =>
        i.id === ITEM_ID_1 ? { ...i, checked: true } : i
      ),
    };
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: listWithChecked,
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, checked: false }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.packingList.items[0].checked).toBe(false);
  });
});

// ================================================================
// PATCH /api/trips/[id]/packing — claims
// ================================================================

describe("PATCH /api/trips/[id]/packing — claims", () => {
  let PATCH: typeof import("../../app/api/trips/[id]/packing/route").PATCH;

  const USER_ID = "b2c3d4e5-f6a7-4b8c-9d00-111111111111";
  const OTHER_USER_ID = "a1b2c3d4-e5f6-4a7b-8c9d-aaaaaaaaaaaa";

  const PACKING_LIST_WITH_CLAIMS = {
    items: [
      { id: ITEM_ID_1, text: "Sunscreen SPF 50+", category: "essentials", checked: false },
      { id: ITEM_ID_2, text: "Passport", category: "documents", checked: true, claimedBy: USER_ID },
      { id: ITEM_ID_3, text: "Phone charger", category: "tech", checked: false, claimedBy: OTHER_USER_ID },
    ],
    generatedAt: "2026-02-22T00:00:00.000Z",
    model: "claude-haiku-4-5-20251001",
  };

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../app/api/trips/[id]/packing/route");
    PATCH = mod.PATCH;
  });

  it("claims own item -> 200, claimedBy set", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    const item = json.packingList.items.find((i: { id: string }) => i.id === ITEM_ID_1);
    expect(item.claimedBy).toBe(USER_ID);
  });

  it("unclaims own item -> 200, claimedBy null", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_2, claimedBy: null }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    const item = json.packingList.items.find((i: { id: string }) => i.id === ITEM_ID_2);
    expect(item.claimedBy).toBeNull();
  });

  it("rejects claiming as different userId -> 403", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, claimedBy: OTHER_USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toContain("Cannot claim");
  });

  it("rejects unclaiming someone else's item -> 403", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_3, claimedBy: null }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toContain("Cannot unclaim");
  });

  it("returns 404 when item not found (claim)", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: "550e8400-e29b-41d4-a716-446655440000", claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe("Item not found");
  });

  it("returns 404 when packingList is null (claim)", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: null,
    } as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toContain("No packing list");
  });

  it("claim does not change checked state", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    // Item 1 has checked: false — after claiming, checked should still be false
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    const item = json.packingList.items.find((i: { id: string }) => i.id === ITEM_ID_1);
    expect(item.checked).toBe(false);
    expect(item.claimedBy).toBe(USER_ID);
  });

  it("check does not change claimedBy", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    // Item 2 has claimedBy: USER_ID — toggling checked should preserve claimedBy
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...PACKING_LIST_WITH_CLAIMS, items: [...PACKING_LIST_WITH_CLAIMS.items] },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_2, checked: false }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    const item = json.packingList.items.find((i: { id: string }) => i.id === ITEM_ID_2);
    expect(item.checked).toBe(false);
    expect(item.claimedBy).toBe(USER_ID);
  });

  it("old items without claimedBy field can be claimed", async () => {
    authedSession(USER_ID);
    mockJoinedMember();
    // MOCK_PACKING_LIST has no claimedBy on items — legacy format
    mockPrisma.trip.findUnique.mockResolvedValueOnce({
      packingList: { ...MOCK_PACKING_LIST, items: [...MOCK_PACKING_LIST.items] },
    } as never);
    mockPrisma.$transaction.mockResolvedValueOnce([{}, {}] as never);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: ITEM_ID_1, claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    const item = json.packingList.items.find((i: { id: string }) => i.id === ITEM_ID_1);
    expect(item.claimedBy).toBe(USER_ID);
  });

  it("rejects invalid UUID for itemId in claim", async () => {
    authedSession(USER_ID);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itemId: "not-a-uuid", claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });

  it("rejects missing itemId in claim", async () => {
    authedSession(USER_ID);

    const req = new NextRequest(`http://localhost:3000/api/trips/${TRIP_ID}/packing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claimedBy: USER_ID }),
    });
    const res = await PATCH(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(400);
  });
});

// ================================================================
// Zod Schema Unit Tests
// ================================================================

describe("Packing validation schemas", () => {
  it("packingGenerateSchema accepts empty body", async () => {
    const { packingGenerateSchema } = await import("../../lib/validations/packing");
    expect(packingGenerateSchema.safeParse(undefined).success).toBe(true);
  });

  it("packingGenerateSchema accepts regenerate flag", async () => {
    const { packingGenerateSchema } = await import("../../lib/validations/packing");
    const result = packingGenerateSchema.safeParse({ regenerate: true });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data?.regenerate).toBe(true);
    }
  });

  it("packingGenerateSchema defaults regenerate to false", async () => {
    const { packingGenerateSchema } = await import("../../lib/validations/packing");
    const result = packingGenerateSchema.safeParse({});
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data?.regenerate).toBe(false);
    }
  });

  it("packingCheckSchema validates uuid format", async () => {
    const { packingCheckSchema } = await import("../../lib/validations/packing");
    expect(
      packingCheckSchema.safeParse({ itemId: "not-uuid", checked: true }).success
    ).toBe(false);
    expect(
      packingCheckSchema.safeParse({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
        checked: true,
      }).success
    ).toBe(true);
  });

  it("packingCheckSchema requires checked boolean", async () => {
    const { packingCheckSchema } = await import("../../lib/validations/packing");
    expect(
      packingCheckSchema.safeParse({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
      }).success
    ).toBe(false);
    expect(
      packingCheckSchema.safeParse({
        itemId: "550e8400-e29b-41d4-a716-446655440000",
        checked: "yes",
      }).success
    ).toBe(false);
  });

  it("packingItemSchema rejects invalid category", async () => {
    const { packingItemSchema } = await import("../../lib/validations/packing");
    expect(
      packingItemSchema.safeParse({
        id: "1",
        text: "Item",
        category: "weapons",
        checked: false,
      }).success
    ).toBe(false);
  });

  it("packingItemSchema accepts all valid categories", async () => {
    const { packingItemSchema } = await import("../../lib/validations/packing");
    const categories = ["essentials", "clothing", "documents", "tech", "toiletries", "misc"];
    for (const category of categories) {
      expect(
        packingItemSchema.safeParse({
          id: "1",
          text: "Item",
          category,
          checked: false,
        }).success
      ).toBe(true);
    }
  });

  it("packingItemSchema rejects text over 100 chars", async () => {
    const { packingItemSchema } = await import("../../lib/validations/packing");
    expect(
      packingItemSchema.safeParse({
        id: "1",
        text: "A".repeat(101),
        category: "essentials",
        checked: false,
      }).success
    ).toBe(false);
  });

  it("packingListSchema rejects more than 50 items", async () => {
    const { packingListSchema } = await import("../../lib/validations/packing");
    const items = Array.from({ length: 51 }, (_, i) => ({
      id: String(i),
      text: `Item ${i}`,
      category: "misc",
      checked: false,
    }));
    expect(packingListSchema.safeParse({ items }).success).toBe(false);
  });

  it("packingListSchema accepts valid packing list", async () => {
    const { packingListSchema } = await import("../../lib/validations/packing");
    const result = packingListSchema.safeParse({
      items: [
        { id: "1", text: "Sunscreen", category: "essentials", checked: false },
        { id: "2", text: "Passport", category: "documents", checked: true },
      ],
    });
    expect(result.success).toBe(true);
  });
});
