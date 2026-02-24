/**
 * Tests for expense endpoints:
 *   GET    /api/trips/[id]/expenses
 *   POST   /api/trips/[id]/expenses
 *   DELETE /api/trips/[id]/expenses/[expenseId]
 *   GET    /api/trips/[id]/expenses/settle
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
      findMany: vi.fn(),
    },
    expense: {
      findMany: vi.fn(),
      create: vi.fn(),
      findFirst: vi.fn(),
      delete: vi.fn(),
    },
    itinerarySlot: {
      findFirst: vi.fn(),
    },
    auditLog: {
      create: vi.fn(),
    },
    trip: {
      findUnique: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/validations/expenses", async () => {
  const actual = await import("../../lib/validations/expenses");
  return actual;
});

vi.mock("@/lib/settle", async () => {
  const actual = await import("../../lib/settle");
  return actual;
});

// Import after mocks
const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");

const mockSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// ---- Helpers ----

const USER_ID = "550e8400-e29b-41d4-a716-446655440000";
const OTHER_USER_ID = "550e8400-e29b-41d4-a716-446655440001";
const TRIP_ID = "660e8400-e29b-41d4-a716-446655440000";
const EXPENSE_ID = "770e8400-e29b-41d4-a716-446655440000";
const SLOT_ID = "880e8400-e29b-41d4-a716-446655440000";

function authedSession(userId = USER_ID) {
  mockSession.mockResolvedValueOnce({ user: { id: userId } } as never);
}

function noSession() {
  mockSession.mockResolvedValueOnce(null);
}

function joinedMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    status: "joined",
  } as never);
}

function invitedMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
    status: "invited",
  } as never);
}

function noMember() {
  mockPrisma.tripMember.findUnique.mockResolvedValueOnce(null);
}

function makeExpense(overrides: Record<string, unknown> = {}) {
  return {
    id: EXPENSE_ID,
    tripId: TRIP_ID,
    paidById: USER_ID,
    description: "Dinner",
    amountCents: 5000,
    splitWith: [],
    slotId: null,
    createdAt: new Date("2026-02-20"),
    paidBy: { id: USER_ID, name: "Alice", avatarUrl: null },
    ...overrides,
  };
}

// ================================================================
// GET /api/trips/[id]/expenses
// ================================================================

describe("GET /api/trips/[id]/expenses", () => {
  let GET: typeof import("../../app/api/trips/[id]/expenses/route").GET;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../app/api/trips/[id]/expenses/route");
    GET = mod.GET;
  });

  it("returns 401 if not authenticated", async () => {
    noSession();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 404 if not a trip member", async () => {
    authedSession();
    noMember();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns 404 if invited but not joined", async () => {
    authedSession();
    invitedMember();
    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns expenses for joined member", async () => {
    authedSession();
    joinedMember();
    const expenses = [makeExpense()];
    mockPrisma.expense.findMany.mockResolvedValueOnce(expenses as never);

    const req = new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses`
    );
    const res = await GET(req, { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.expenses).toHaveLength(1);
    expect(json.expenses[0].description).toBe("Dinner");
  });
});

// ================================================================
// POST /api/trips/[id]/expenses
// ================================================================

describe("POST /api/trips/[id]/expenses", () => {
  let POST: typeof import("../../app/api/trips/[id]/expenses/route").POST;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import("../../app/api/trips/[id]/expenses/route");
    POST = mod.POST;
  });

  function postRequest(body: unknown) {
    return new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses`,
      {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  it("returns 401 if not authenticated", async () => {
    noSession();
    const res = await POST(
      postRequest({ description: "Test", amountCents: 1000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(401);
  });

  it("returns 404 if not a trip member", async () => {
    authedSession();
    noMember();
    const res = await POST(
      postRequest({ description: "Test", amountCents: 1000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(404);
  });

  it("returns 404 if invited but not joined", async () => {
    authedSession();
    invitedMember();
    const res = await POST(
      postRequest({ description: "Test", amountCents: 1000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(404);
  });

  it("creates a valid expense and returns 201", async () => {
    authedSession();
    joinedMember();
    const created = makeExpense();
    mockPrisma.expense.create.mockResolvedValueOnce(created as never);

    const res = await POST(
      postRequest({ description: "Dinner", amountCents: 5000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.expense.description).toBe("Dinner");

    // Verify paidById comes from session, not body
    const createCall = mockPrisma.expense.create.mock.calls[0][0];
    expect(createCall.data.paidById).toBe(USER_ID);
  });

  it("ignores paidById in body, uses session user", async () => {
    authedSession();
    joinedMember();
    mockPrisma.expense.create.mockResolvedValueOnce(makeExpense() as never);

    const res = await POST(
      postRequest({
        description: "Dinner",
        amountCents: 5000,
        paidById: "attacker-id",
      }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(201);

    const createCall = mockPrisma.expense.create.mock.calls[0][0];
    expect(createCall.data.paidById).toBe(USER_ID);
    expect(createCall.data.paidById).not.toBe("attacker-id");
  });

  it("returns 400 for splitWith with non-member userId", async () => {
    authedSession();
    joinedMember();
    const nonMemberId = "990e8400-e29b-41d4-a716-446655440099";
    mockPrisma.tripMember.findMany.mockResolvedValueOnce([] as never);

    const res = await POST(
      postRequest({
        description: "Dinner",
        amountCents: 5000,
        splitWith: [nonMemberId],
      }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toContain("split members");
  });

  it("deduplicates splitWith IDs without error", async () => {
    authedSession();
    joinedMember();
    mockPrisma.tripMember.findMany.mockResolvedValueOnce([
      { userId: OTHER_USER_ID },
    ] as never);
    mockPrisma.expense.create.mockResolvedValueOnce(makeExpense() as never);

    const res = await POST(
      postRequest({
        description: "Dinner",
        amountCents: 5000,
        splitWith: [OTHER_USER_ID, OTHER_USER_ID, OTHER_USER_ID],
      }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(201);

    // Verify deduped in findMany call
    const findManyCall = mockPrisma.tripMember.findMany.mock.calls[0][0];
    expect(findManyCall.where.userId.in).toHaveLength(1);
  });

  it("returns 400 for amountCents 0", async () => {
    authedSession();
    const res = await POST(
      postRequest({ description: "Test", amountCents: 0 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for negative amountCents", async () => {
    authedSession();
    const res = await POST(
      postRequest({ description: "Test", amountCents: -100 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for amountCents > 10M", async () => {
    authedSession();
    const res = await POST(
      postRequest({ description: "Test", amountCents: 10_000_001 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for empty description", async () => {
    authedSession();
    const res = await POST(
      postRequest({ description: "", amountCents: 1000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for description > 200 chars", async () => {
    authedSession();
    const res = await POST(
      postRequest({ description: "x".repeat(201), amountCents: 1000 }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 for slotId from different trip", async () => {
    authedSession();
    joinedMember();
    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce(null);

    const res = await POST(
      postRequest({
        description: "Dinner",
        amountCents: 5000,
        slotId: SLOT_ID,
      }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toContain("Slot");
  });

  it("accepts valid slotId from same trip", async () => {
    authedSession();
    joinedMember();
    mockPrisma.itinerarySlot.findFirst.mockResolvedValueOnce({
      id: SLOT_ID,
      tripId: TRIP_ID,
    } as never);
    mockPrisma.expense.create.mockResolvedValueOnce(
      makeExpense({ slotId: SLOT_ID }) as never
    );

    const res = await POST(
      postRequest({
        description: "Dinner",
        amountCents: 5000,
        slotId: SLOT_ID,
      }),
      { params: { id: TRIP_ID } }
    );
    expect(res.status).toBe(201);
  });
});

// ================================================================
// DELETE /api/trips/[id]/expenses/[expenseId]
// ================================================================

describe("DELETE /api/trips/[id]/expenses/[expenseId]", () => {
  let DELETE: typeof import("../../app/api/trips/[id]/expenses/[expenseId]/route").DELETE;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import(
      "../../app/api/trips/[id]/expenses/[expenseId]/route"
    );
    DELETE = mod.DELETE;
  });

  function deleteRequest() {
    return new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses/${EXPENSE_ID}`,
      { method: "DELETE" }
    );
  }

  it("returns 401 if not authenticated", async () => {
    noSession();
    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: EXPENSE_ID },
    });
    expect(res.status).toBe(401);
  });

  it("returns 404 if not a trip member", async () => {
    authedSession();
    noMember();
    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: EXPENSE_ID },
    });
    expect(res.status).toBe(404);
  });

  it("returns 404 if invited but not joined", async () => {
    authedSession();
    invitedMember();
    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: EXPENSE_ID },
    });
    expect(res.status).toBe(404);
  });

  it("author deletes own expense -> 200 + AuditLog created", async () => {
    authedSession();
    joinedMember();
    const expense = makeExpense();
    mockPrisma.expense.findFirst.mockResolvedValueOnce(expense as never);
    mockPrisma.auditLog.create.mockResolvedValueOnce({} as never);
    mockPrisma.expense.delete.mockResolvedValueOnce({} as never);

    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: EXPENSE_ID },
    });
    expect(res.status).toBe(200);

    // Verify audit log was created
    expect(mockPrisma.auditLog.create).toHaveBeenCalledOnce();
    const auditCall = mockPrisma.auditLog.create.mock.calls[0][0];
    expect(auditCall.data.action).toBe("expense_delete");
    expect(auditCall.data.targetType).toBe("Expense");
    expect(auditCall.data.targetId).toBe(EXPENSE_ID);
    expect(auditCall.data.actorId).toBe(USER_ID);
  });

  it("non-author cannot delete -> 404", async () => {
    authedSession(OTHER_USER_ID);
    mockPrisma.tripMember.findUnique.mockResolvedValueOnce({
      status: "joined",
    } as never);
    // findFirst returns null because paidById won't match OTHER_USER_ID
    mockPrisma.expense.findFirst.mockResolvedValueOnce(null);

    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: EXPENSE_ID },
    });
    expect(res.status).toBe(404);
  });

  it("expenseId from different trip -> 404", async () => {
    authedSession();
    joinedMember();
    // findFirst returns null because tripId won't match
    mockPrisma.expense.findFirst.mockResolvedValueOnce(null);

    const res = await DELETE(deleteRequest(), {
      params: { id: TRIP_ID, expenseId: "999e8400-e29b-41d4-a716-446655440099" },
    });
    expect(res.status).toBe(404);
  });
});

// ================================================================
// GET /api/trips/[id]/expenses/settle
// ================================================================

describe("GET /api/trips/[id]/expenses/settle", () => {
  let GET: typeof import("../../app/api/trips/[id]/expenses/settle/route").GET;

  beforeEach(async () => {
    vi.resetAllMocks();
    const mod = await import(
      "../../app/api/trips/[id]/expenses/settle/route"
    );
    GET = mod.GET;
  });

  function settleRequest() {
    return new NextRequest(
      `http://localhost:3000/api/trips/${TRIP_ID}/expenses/settle`
    );
  }

  it("returns 401 if not authenticated", async () => {
    noSession();
    const res = await GET(settleRequest(), { params: { id: TRIP_ID } });
    expect(res.status).toBe(401);
  });

  it("returns 404 if not a trip member", async () => {
    authedSession();
    noMember();
    const res = await GET(settleRequest(), { params: { id: TRIP_ID } });
    expect(res.status).toBe(404);
  });

  it("returns empty settlements for trip with no expenses", async () => {
    authedSession();
    joinedMember();
    mockPrisma.expense.findMany.mockResolvedValueOnce([] as never);
    mockPrisma.tripMember.findMany.mockResolvedValueOnce([
      { userId: USER_ID, user: { id: USER_ID, name: "Alice", avatarUrl: null } },
      { userId: OTHER_USER_ID, user: { id: OTHER_USER_ID, name: "Bob", avatarUrl: null } },
    ] as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({ currency: "USD" } as never);

    const res = await GET(settleRequest(), { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.settlements).toEqual([]);
    expect(json.currency).toBe("USD");
  });

  it("returns correct settlement for 2-person trip", async () => {
    authedSession();
    joinedMember();
    mockPrisma.expense.findMany.mockResolvedValueOnce([
      { paidById: USER_ID, amountCents: 10000, splitWith: [] },
    ] as never);
    mockPrisma.tripMember.findMany.mockResolvedValueOnce([
      { userId: USER_ID, user: { id: USER_ID, name: "Alice", avatarUrl: null } },
      { userId: OTHER_USER_ID, user: { id: OTHER_USER_ID, name: "Bob", avatarUrl: null } },
    ] as never);
    mockPrisma.trip.findUnique.mockResolvedValueOnce({ currency: "JPY" } as never);

    const res = await GET(settleRequest(), { params: { id: TRIP_ID } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.settlements).toHaveLength(1);
    expect(json.settlements[0].fromId).toBe(OTHER_USER_ID);
    expect(json.settlements[0].fromName).toBe("Bob");
    expect(json.settlements[0].toId).toBe(USER_ID);
    expect(json.settlements[0].toName).toBe("Alice");
    expect(json.settlements[0].amountCents).toBe(5000);
    expect(json.currency).toBe("JPY");
  });
});
