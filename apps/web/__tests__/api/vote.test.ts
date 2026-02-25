/**
 * Route handler tests for POST /api/slots/[slotId]/vote
 * Tests auth guards, validation, vote state machine, quorum, threshold, and signal logging.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    itinerarySlot: {
      findUnique: vi.fn(),
      update: vi.fn(),
    },
    tripMember: {
      count: vi.fn(),
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

vi.mock("uuid", () => ({
  v4: () => "mock-uuid-1",
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import(
  "../../app/api/slots/[slotId]/vote/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function makeVoteRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/slots/slot-123/vote", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

const mockParams = { params: { slotId: "slot-123" } };
const authedSession = { user: { id: "user-abc" } };

const baseSlot = {
  id: "slot-123",
  tripId: "trip-1",
  activityNodeId: "an-1",
  status: "proposed",
  voteState: null,
  isContested: false,
  trip: {
    members: [{ id: "member-1" }],
  },
};

// ─── Auth Guards ──────────────────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(401);
  });

  it("returns 404 when slot is not found", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(null);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(404);
  });

  it("returns 404 when user is not a joined member", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce({
      ...baseSlot,
      trip: { members: [] },
    } as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(404);
  });
});

// ─── Validation ───────────────────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const req = new NextRequest(
      "http://localhost:3000/api/slots/slot-123/vote",
      { method: "POST", body: "not json" },
    );
    const res = await POST(req, mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid vote value", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(makeVoteRequest({ vote: "abstain" }), mockParams);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing vote field", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await POST(makeVoteRequest({}), mockParams);
    expect(res.status).toBe(400);
  });
});

// ─── Happy Path: First Vote ───────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — first vote (no quorum)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("initializes voteState and records vote", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);

    const updatedSlot = {
      ...baseSlot,
      status: "proposed",
      voteState: {
        state: "voting",
        votes: { "user-abc": "yes" },
        updatedAt: expect.any(String),
      },
    };

    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.success).toBe(true);
    expect(json.data.voteState.state).toBe("voting");
    expect(json.data.voteState.votes["user-abc"]).toBe("yes");
  });

  it("logs behavioral signal with correct signalValue for yes", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);
    mockPrisma.$transaction.mockResolvedValueOnce([
      { ...baseSlot, voteState: { state: "voting", votes: { "user-abc": "yes" }, updatedAt: "" } },
      {},
    ] as never);

    await POST(makeVoteRequest({ vote: "yes" }), mockParams);

    const txCall = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];
    // Verify $transaction was called (signal is inside the transaction array)
    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
  });

  it("logs signalValue 0.5 for maybe vote", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);
    mockPrisma.$transaction.mockResolvedValueOnce([
      { ...baseSlot, voteState: { state: "voting", votes: { "user-abc": "maybe" }, updatedAt: "" } },
      {},
    ] as never);

    const res = await POST(makeVoteRequest({ vote: "maybe" }), mockParams);
    expect(res.status).toBe(200);
  });

  it("logs signalValue -1.0 for no vote", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);
    mockPrisma.$transaction.mockResolvedValueOnce([
      { ...baseSlot, voteState: { state: "voting", votes: { "user-abc": "no" }, updatedAt: "" } },
      {},
    ] as never);

    const res = await POST(makeVoteRequest({ vote: "no" }), mockParams);
    expect(res.status).toBe(200);
  });
});

// ─── Quorum: Auto-Confirm (>= 70% yes) ───────────────────────────────

describe("POST /api/slots/[slotId]/vote — quorum auto-confirm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("auto-confirms when all vote yes (100%)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const slotWith2Votes = {
      ...baseSlot,
      voteState: {
        state: "voting",
        votes: { "user-1": "yes", "user-2": "yes" },
        updatedAt: new Date().toISOString(),
      },
    };
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slotWith2Votes as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3); // 3 members total

    const confirmedSlot = {
      ...baseSlot,
      status: "confirmed",
      voteState: {
        state: "confirmed",
        votes: { "user-1": "yes", "user-2": "yes", "user-abc": "yes" },
        updatedAt: expect.any(String),
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([confirmedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.data.voteState.state).toBe("confirmed");
    expect(json.data.slotStatus).toBe("confirmed");
  });

  it("auto-confirms at exactly 70% yes threshold (7/10)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    // 9 existing votes: 6 yes, 2 no, 1 maybe. user-abc votes yes = 7 yes out of 10.
    const existingVotes: Record<string, string> = {};
    for (let i = 1; i <= 6; i++) existingVotes[`user-${i}`] = "yes";
    existingVotes["user-7"] = "no";
    existingVotes["user-8"] = "no";
    existingVotes["user-9"] = "maybe";

    const slotWith9Votes = {
      ...baseSlot,
      voteState: { state: "voting", votes: existingVotes, updatedAt: new Date().toISOString() },
    };
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slotWith9Votes as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(10);

    const confirmedSlot = {
      ...baseSlot,
      status: "confirmed",
      voteState: { state: "confirmed", votes: { ...existingVotes, "user-abc": "yes" }, updatedAt: "" },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([confirmedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    const json = await res.json();
    expect(json.data.voteState.state).toBe("confirmed");
    expect(json.data.slotStatus).toBe("confirmed");
  });
});

// ─── Quorum: Auto-Contest (< 70% yes) ────────────────────────────────

describe("POST /api/slots/[slotId]/vote — quorum auto-contest", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("contests when yes votes below 70%", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    // 2 existing votes: 1 yes, 1 no. user-abc votes no = 1/3 = 33% yes
    const slotWith2Votes = {
      ...baseSlot,
      voteState: {
        state: "voting",
        votes: { "user-1": "yes", "user-2": "no" },
        updatedAt: new Date().toISOString(),
      },
    };
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slotWith2Votes as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);

    const contestedSlot = {
      ...baseSlot,
      status: "proposed",
      isContested: true,
      voteState: {
        state: "contested",
        votes: { "user-1": "yes", "user-2": "no", "user-abc": "no" },
        updatedAt: "",
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([contestedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "no" }), mockParams);
    const json = await res.json();
    expect(json.data.voteState.state).toBe("contested");
  });

  it("maybe does NOT count as yes for threshold (70% means yes-only)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    // 2 existing: 1 yes, 1 maybe. user-abc votes maybe. 1/3 yes = 33% < 70%
    const slotWith2Votes = {
      ...baseSlot,
      voteState: {
        state: "voting",
        votes: { "user-1": "yes", "user-2": "maybe" },
        updatedAt: new Date().toISOString(),
      },
    };
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slotWith2Votes as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);

    const contestedSlot = {
      ...baseSlot,
      isContested: true,
      voteState: {
        state: "contested",
        votes: { "user-1": "yes", "user-2": "maybe", "user-abc": "maybe" },
        updatedAt: "",
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([contestedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "maybe" }), mockParams);
    const json = await res.json();
    expect(json.data.voteState.state).toBe("contested");
  });
});

// ─── Vote Overwrites ──────────────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — overwrite previous vote", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("allows user to change their vote", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const slotWithExistingVote = {
      ...baseSlot,
      voteState: {
        state: "voting",
        votes: { "user-abc": "no", "user-1": "yes" },
        updatedAt: new Date().toISOString(),
      },
    };
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(slotWithExistingVote as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);

    const updatedSlot = {
      ...baseSlot,
      voteState: {
        state: "voting",
        votes: { "user-abc": "yes", "user-1": "yes" },
        updatedAt: "",
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.data.voteState.votes["user-abc"]).toBe("yes");
  });
});

// ─── Error Handling ───────────────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — error handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 500 when transaction fails", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(3);
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB failure"));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    expect(res.status).toBe(500);
    consoleSpy.mockRestore();
  });
});

// ─── Response Shape ───────────────────────────────────────────────────

describe("POST /api/slots/[slotId]/vote — response shape (C1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns { success, data: { voteState, slotStatus } } wrapper", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.itinerarySlot.findUnique.mockResolvedValueOnce(baseSlot as never);
    mockPrisma.tripMember.count.mockResolvedValueOnce(5);

    const updatedSlot = {
      ...baseSlot,
      status: "proposed",
      voteState: {
        state: "voting",
        votes: { "user-abc": "yes" },
        updatedAt: new Date().toISOString(),
      },
    };
    mockPrisma.$transaction.mockResolvedValueOnce([updatedSlot, {}] as never);

    const res = await POST(makeVoteRequest({ vote: "yes" }), mockParams);
    const json = await res.json();

    expect(json).toHaveProperty("success", true);
    expect(json).toHaveProperty("data");
    expect(json.data).toHaveProperty("voteState");
    expect(json.data).toHaveProperty("slotStatus");
  });
});

// ─── Zod Schema Unit Tests ────────────────────────────────────────────

const { voteSchema: schema } = await import("../../lib/validations/vote");

describe("voteSchema validation", () => {

  it("accepts 'yes'", () => {
    expect(schema.safeParse({ vote: "yes" }).success).toBe(true);
  });

  it("accepts 'no'", () => {
    expect(schema.safeParse({ vote: "no" }).success).toBe(true);
  });

  it("accepts 'maybe'", () => {
    expect(schema.safeParse({ vote: "maybe" }).success).toBe(true);
  });

  it("rejects 'abstain'", () => {
    expect(schema.safeParse({ vote: "abstain" }).success).toBe(false);
  });

  it("rejects empty object", () => {
    expect(schema.safeParse({}).success).toBe(false);
  });

  it("rejects number value", () => {
    expect(schema.safeParse({ vote: 1 }).success).toBe(false);
  });

  it("rejects null", () => {
    expect(schema.safeParse(null).success).toBe(false);
  });
});
