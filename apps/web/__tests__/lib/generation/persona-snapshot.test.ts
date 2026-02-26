import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    behavioralSignal: {
      findMany: vi.fn(),
    },
  },
  PrismaJsonNull: Symbol("JsonNull"),
}));

const { prisma } = await import("@/lib/prisma");
const { getPersonaSnapshot } = await import(
  "@/lib/generation/persona-snapshot"
);

const mockPrisma = vi.mocked(prisma, true);

describe("getPersonaSnapshot", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns empty object for user with no signals", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([]);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    expect(result).toEqual({});
  });

  it("aggregates food-related signals into food_focus", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([
      { rawAction: "viewed_restaurant_detail", signalType: "soft_positive" },
      { rawAction: "dining_bookmark", signalType: "soft_positive" },
      { rawAction: "food_market_search", signalType: "soft_positive" },
      { rawAction: "clicked_museum", signalType: "soft_positive" },
    ] as any);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    expect(result.food_focus).toBe(0.75); // 3 of 4 match food patterns
  });

  it("aggregates adventure signals correctly", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([
      { rawAction: "hiking_trail_viewed", signalType: "soft_positive" },
      { rawAction: "outdoor_activity_saved", signalType: "soft_positive" },
      { rawAction: "sport_climbing_event", signalType: "soft_positive" },
      { rawAction: "cafe_visited", signalType: "soft_positive" },
      { rawAction: "shopping_area_viewed", signalType: "soft_positive" },
    ] as any);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    // 3 of 5 match adventure patterns (hiking, outdoor, sport)
    expect(result.adventure_score).toBe(0.6);
  });

  it("aggregates culture signals correctly", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([
      { rawAction: "museum_detail_viewed", signalType: "soft_positive" },
      { rawAction: "temple_visit_planned", signalType: "soft_positive" },
      { rawAction: "gallery_bookmarked", signalType: "soft_positive" },
      { rawAction: "bar_hopping_route", signalType: "soft_positive" },
    ] as any);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    expect(result.culture_interest).toBe(0.75); // 3 of 4 match culture
  });

  it("handles multiple dimensions in the same signal set", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([
      { rawAction: "restaurant_viewed", signalType: "soft_positive" },
      { rawAction: "hiking_trail_saved", signalType: "soft_positive" },
      { rawAction: "museum_bookmarked", signalType: "soft_positive" },
      { rawAction: "beach_resort_viewed", signalType: "soft_positive" },
      { rawAction: "budget_hotel_search", signalType: "soft_positive" },
    ] as any);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");

    // Each dimension independently computed
    expect(result.food_focus).toBe(0.2);       // 1/5 (restaurant)
    expect(result.adventure_score).toBe(0.2);   // 1/5 (hiking)
    expect(result.culture_interest).toBe(0.2);  // 1/5 (museum)
    expect(result.nature_preference).toBe(0.2); // 1/5 (beach only — hiking matches adventure not nature)
    expect(result.budget_sensitivity).toBe(0.2); // 1/5 (budget)
  });

  it("omits zero-value dimensions from result", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([
      { rawAction: "viewed_generic_page", signalType: "soft_positive" },
      { rawAction: "clicked_notification", signalType: "soft_positive" },
    ] as any);

    const result = await getPersonaSnapshot(prisma, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");

    // No patterns match these generic actions
    expect(Object.keys(result).length).toBe(0);
  });

  it("queries with correct parameters", async () => {
    mockPrisma.behavioralSignal.findMany.mockResolvedValueOnce([]);
    const userId = "11111111-2222-3333-4444-555555555555";

    await getPersonaSnapshot(prisma, userId);

    expect(mockPrisma.behavioralSignal.findMany).toHaveBeenCalledWith({
      where: {
        userId,
        source: "user_behavioral",
      },
      select: {
        rawAction: true,
        signalType: true,
      },
      orderBy: { createdAt: "desc" },
      take: 200,
    });
  });
});
