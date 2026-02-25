/**
 * Route handler tests for GET /api/settings/export
 * Tests auth, rate limiting, content-disposition, data shape, and field filtering.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// We need to handle rate limit state between tests.
// The route uses an in-memory Map, so we use the exported reset function.

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: vi.fn(),
    user: { findUniqueOrThrow: vi.fn() },
    userPreference: { findUnique: vi.fn() },
    notificationPreference: { findUnique: vi.fn() },
    dataConsent: { findUnique: vi.fn() },
    tripMember: { findMany: vi.fn() },
    behavioralSignal: { findMany: vi.fn() },
    intentionSignal: { findMany: vi.fn() },
    rawEvent: { findMany: vi.fn() },
    personaDimension: { findMany: vi.fn() },
    rankingEvent: { findMany: vi.fn() },
    backfillTrip: { findMany: vi.fn() },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { GET } = await import("../../app/api/settings/export/route");
const { _resetRateLimitForTest } = await import(
  "../../app/api/settings/export/rate-limit"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

function makeEmptyExportData() {
  return [
    { name: null, email: "test@example.com", createdAt: new Date("2026-01-01"), subscriptionTier: "beta" },
    null, // UserPreference
    null, // NotificationPreference
    null, // DataConsent
    [],   // TripMember (trips)
    [],   // BehavioralSignals
    [],   // IntentionSignals
    [],   // RawEvents
    [],   // PersonaDimensions
    [],   // RankingEvents
    [],   // BackfillTrips
  ];
}

describe("GET /api/settings/export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    _resetRateLimitForTest();
  });

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("returns Content-Disposition header with date-stamped filename", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(makeEmptyExportData() as never);

    const res = await GET();
    expect(res.status).toBe(200);

    const disposition = res.headers.get("content-disposition");
    expect(disposition).toMatch(/^attachment; filename="overplanned-export-\d{4}-\d{2}-\d{2}\.json"$/);
  });

  it("returns valid structure with empty arrays for user with no data", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(makeEmptyExportData() as never);

    const res = await GET();
    const json = await res.json();

    expect(json).toHaveProperty("exportedAt");
    expect(json).toHaveProperty("profile");
    expect(json).toHaveProperty("preferences");
    expect(json).toHaveProperty("notifications");
    expect(json).toHaveProperty("consent");
    expect(json).toHaveProperty("trips");
    expect(json).toHaveProperty("behavioralSignals");
    expect(json).toHaveProperty("intentionSignals");
    expect(json).toHaveProperty("rawEvents");
    expect(json).toHaveProperty("personaDimensions");
    expect(json).toHaveProperty("rankingEvents");
    expect(json).toHaveProperty("backfillTrips");

    expect(json.trips).toEqual([]);
    expect(json.behavioralSignals).toEqual([]);
    expect(json.consent).toEqual({ modelTraining: false, anonymizedResearch: false });

    // Preferences fallback — all new fields present with correct defaults
    expect(json.preferences).toEqual({
      dietary: [],
      mobility: [],
      languages: [],
      travelFrequency: null,
      vibePreferences: [],
      travelStyleNote: null,
      budgetComfort: null,
      spendingPriorities: [],
      accommodationTypes: [],
      transitModes: [],
      preferencesNote: null,
    });

    // Notifications fallback — all fields including checkinReminder + preTripDaysBefore
    expect(json.notifications).toMatchObject({
      tripReminders: true,
      morningBriefing: true,
      groupActivity: true,
      postTripPrompt: true,
      citySeeded: true,
      inspirationNudges: false,
      productUpdates: false,
      checkinReminder: false,
      preTripDaysBefore: 3,
    });
  });

  it("has trip data populated from transaction", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);

    const data = makeEmptyExportData();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (data as any)[4] = [{
      trip: {
        name: "Rome Trip",
        destination: "Rome",
        city: "Rome",
        country: "Italy",
        startDate: new Date("2026-03-01"),
        endDate: new Date("2026-03-05"),
        status: "planning",
        mode: "solo",
        createdAt: new Date(),
        slots: [{ dayNumber: 1, slotType: "morning", status: "confirmed", activityNode: { name: "Colosseum", category: "culture" } }],
      },
    }];
    mockPrisma.$transaction.mockResolvedValueOnce(data as never);

    const res = await GET();
    const json = await res.json();

    expect(json.trips).toHaveLength(1);
    expect(json.trips[0].destination).toBe("Rome");
    expect(json.trips[0].slots).toHaveLength(1);
  });

  it("returns 429 on second request within 10 minutes", async () => {
    // First request succeeds
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(makeEmptyExportData() as never);
    const res1 = await GET();
    expect(res1.status).toBe(200);

    // Second request rate-limited
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res2 = await GET();
    expect(res2.status).toBe(429);
    const json = await res2.json();
    expect(json.error).toBe("Please wait before requesting another export.");
  });

  it("includes new preference fields when a preferences record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);

    const data = makeEmptyExportData();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (data as any)[1] = {
      dietary: ["vegetarian", "gluten-free"],
      mobility: ["wheelchair"],
      languages: ["en", "es"],
      travelFrequency: "monthly",
      vibePreferences: ["chill", "adventurous"],
      travelStyleNote: "I like slow travel with lots of local food stops.",
      budgetComfort: "mid-range",
      spendingPriorities: ["food", "accommodation"],
      accommodationTypes: ["boutique", "airbnb"],
      transitModes: ["train", "walk"],
      preferencesNote: "Avoid tourist traps.",
    };
    mockPrisma.$transaction.mockResolvedValueOnce(data as never);

    const res = await GET();
    const json = await res.json();

    expect(json.preferences).toEqual({
      dietary: ["vegetarian", "gluten-free"],
      mobility: ["wheelchair"],
      languages: ["en", "es"],
      travelFrequency: "monthly",
      vibePreferences: ["chill", "adventurous"],
      travelStyleNote: "I like slow travel with lots of local food stops.",
      budgetComfort: "mid-range",
      spendingPriorities: ["food", "accommodation"],
      accommodationTypes: ["boutique", "airbnb"],
      transitModes: ["train", "walk"],
      preferencesNote: "Avoid tourist traps.",
    });
  });

  it("includes checkinReminder and preTripDaysBefore when a notifications record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);

    const data = makeEmptyExportData();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (data as any)[2] = {
      tripReminders: true,
      morningBriefing: false,
      groupActivity: true,
      postTripPrompt: false,
      citySeeded: true,
      inspirationNudges: true,
      productUpdates: false,
      checkinReminder: true,
      preTripDaysBefore: 7,
    };
    mockPrisma.$transaction.mockResolvedValueOnce(data as never);

    const res = await GET();
    const json = await res.json();

    expect(json.notifications).toMatchObject({
      checkinReminder: true,
      preTripDaysBefore: 7,
    });
    // Confirm it's the real record, not the fallback
    expect(json.notifications.morningBriefing).toBe(false);
    expect(json.notifications.inspirationNudges).toBe(true);
  });
});
