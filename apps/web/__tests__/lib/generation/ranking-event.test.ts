/**
 * Tests that RankingEvent records are created correctly during itinerary generation.
 * Validates that the generation pipeline logs ranking data for ML training.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock all dependencies before any imports
vi.mock("@/lib/prisma", () => ({
  prisma: {
    activityNode: {
      count: vi.fn(),
      findMany: vi.fn(),
    },
    itinerarySlot: {
      createMany: vi.fn(),
    },
    behavioralSignal: {
      create: vi.fn(),
      findMany: vi.fn(),
    },
    rankingEvent: {
      create: vi.fn(),
    },
    $transaction: vi.fn(),
    tripLeg: {
      findMany: vi.fn(),
    },
  },
  PrismaJsonNull: Symbol("JsonNull"),
}));

vi.mock("@/lib/generation/llm-enrichment", () => ({
  enrichWithLLM: vi.fn(() => Promise.resolve(undefined)),
}));

vi.mock("@/lib/climate", () => ({
  getClimateContext: vi.fn(() => null),
}));

vi.mock("uuid", () => ({
  v4: vi.fn().mockReturnValue("00000000-0000-0000-0000-000000000001"),
}));

const { prisma } = await import("@/lib/prisma");
const { generateLegItinerary } = await import(
  "@/lib/generation/generate-itinerary"
);

const mockPrisma = vi.mocked(prisma, true);

// Helper: build mock ActivityNode rows
function buildMockNodes(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `node-${String(i + 1).padStart(4, "0")}`,
    name: `Place ${i + 1}`,
    category: i % 3 === 0 ? "dining" : i % 3 === 1 ? "culture" : "outdoors",
    latitude: 35.6762 + i * 0.01,
    longitude: 139.6503 + i * 0.01,
    neighborhood: "Shibuya",
    descriptionShort: `A nice place ${i + 1}`,
    priceLevel: 2,
    authorityScore: 0.7,
    vibeTags: [],
  }));
}

describe("RankingEvent creation during generation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Default: resolve $transaction successfully
    mockPrisma.$transaction.mockResolvedValue(undefined as any);
    // Default: persona snapshot returns empty (no signals)
    mockPrisma.behavioralSignal.findMany.mockResolvedValue([]);
  });

  it("creates RankingEvent records in the same transaction as slots", async () => {
    const nodes = buildMockNodes(12);
    mockPrisma.activityNode.count.mockResolvedValueOnce(12);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-03"), // 2 days
      { pace: "moderate", morningPreference: "mid", foodPreferences: [] },
    );

    // $transaction should be called once with an array
    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];

    // Array should contain: createMany (slots) + behavioralSignal.create + N rankingEvent.create
    // For 2 days of moderate pace (4 slots/day), we expect 2 RankingEvent creates
    // Total operations: 1 (createMany) + 1 (signal) + 2 (ranking events) = 4
    expect(txArgs.length).toBeGreaterThanOrEqual(4);
  });

  it("creates one RankingEvent per day", async () => {
    const nodes = buildMockNodes(20);
    mockPrisma.activityNode.count.mockResolvedValueOnce(20);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-04"), // 3 days
      { pace: "moderate", morningPreference: "mid", foodPreferences: [] },
    );

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    const txArgs = mockPrisma.$transaction.mock.calls[0][0] as unknown as unknown[];

    // 1 (createMany) + 1 (signal) + 3 (one ranking event per day) = 5
    expect(txArgs.length).toBe(5);
  });

  it("passes candidateIds from the full scored node pool", async () => {
    const nodes = buildMockNodes(15);
    mockPrisma.activityNode.count.mockResolvedValueOnce(15);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-02"), // 1 day
      { pace: "relaxed", morningPreference: "mid", foodPreferences: [] },
    );

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);

    // Verify rankingEvent.create was called with candidateIds containing all 15 node IDs
    expect(mockPrisma.rankingEvent.create).toHaveBeenCalled();
    const createCall = mockPrisma.rankingEvent.create.mock.calls[0][0];
    expect(createCall.data.candidateIds).toHaveLength(15);
    expect(createCall.data.surface).toBe("itinerary");
    expect(createCall.data.modelName).toBe("deterministic_scorer");
    expect(createCall.data.modelVersion).toBe("1.0.0");
  });

  it("includes correct tripId and userId on RankingEvent", async () => {
    const nodes = buildMockNodes(8);
    mockPrisma.activityNode.count.mockResolvedValueOnce(8);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-aaaa",
      "leg-bbbb",
      "user-cccc",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-02"),
      { pace: "relaxed", morningPreference: "mid", foodPreferences: [] },
    );

    expect(mockPrisma.rankingEvent.create).toHaveBeenCalled();
    const createCall = mockPrisma.rankingEvent.create.mock.calls[0][0];
    expect(createCall.data.tripId).toBe("trip-aaaa");
    expect(createCall.data.userId).toBe("user-cccc");
  });

  it("does not create RankingEvent for unseeded cities", async () => {
    mockPrisma.activityNode.count.mockResolvedValueOnce(0);

    const result = await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "UnknownCity",
      "Unknown",
      new Date("2026-04-01"),
      new Date("2026-04-03"),
      { pace: "moderate", morningPreference: "mid", foodPreferences: [] },
    );

    expect(result.slotsCreated).toBe(0);
    expect(result.source).toBe("empty");
    expect(mockPrisma.$transaction).not.toHaveBeenCalled();
    expect(mockPrisma.rankingEvent.create).not.toHaveBeenCalled();
  });

  it("sets latencyMs on RankingEvent", async () => {
    const nodes = buildMockNodes(8);
    mockPrisma.activityNode.count.mockResolvedValueOnce(8);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-02"),
      { pace: "relaxed", morningPreference: "mid", foodPreferences: [] },
    );

    const createCall = mockPrisma.rankingEvent.create.mock.calls[0][0];
    expect(typeof createCall.data.latencyMs).toBe("number");
    expect(createCall.data.latencyMs).toBeGreaterThanOrEqual(0);
  });

  it("sets dayNumber on each RankingEvent matching the placed slots", async () => {
    const nodes = buildMockNodes(12);
    mockPrisma.activityNode.count.mockResolvedValueOnce(12);
    mockPrisma.activityNode.findMany.mockResolvedValueOnce(nodes as any);

    await generateLegItinerary(
      "trip-0001",
      "leg-0001",
      "user-0001",
      "Tokyo",
      "Japan",
      new Date("2026-04-01"),
      new Date("2026-04-03"), // 2 days
      { pace: "moderate", morningPreference: "mid", foodPreferences: [] },
    );

    // Should have 2 RankingEvent creates (one per day)
    const calls = mockPrisma.rankingEvent.create.mock.calls;
    expect(calls.length).toBe(2);

    const dayNumbers = calls.map((c) => c[0].data.dayNumber).sort();
    expect(dayNumbers).toEqual([1, 2]);
  });
});
