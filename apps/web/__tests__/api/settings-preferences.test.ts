/**
 * Route handler tests for GET + PATCH /api/settings/preferences
 * Tests auth guards, validation, array deduplication, upsert behavior,
 * field whitelisting (userId from session only), and all 11 preference fields.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    userPreference: {
      findUnique: vi.fn(),
      upsert: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { GET, PATCH } = await import(
  "../../app/api/settings/preferences/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function makeGetRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "GET",
  });
}

function makePatchRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function makePatchRequestInvalidJSON(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/preferences", {
    method: "PATCH",
    body: "not json",
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

// Full PREF_SELECT shape — all 11 fields
const FULL_PREF_SELECT = {
  dietary: true,
  mobility: true,
  languages: true,
  travelFrequency: true,
  vibePreferences: true,
  travelStyleNote: true,
  budgetComfort: true,
  spendingPriorities: true,
  accommodationTypes: true,
  transitModes: true,
  preferencesNote: true,
};

// ---------------------------------------------------------------------------
// GET — auth guards
// ---------------------------------------------------------------------------
describe("GET /api/settings/preferences — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({ user: null } as never);
    const res = await GET();
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// GET — data retrieval
// ---------------------------------------------------------------------------
describe("GET /api/settings/preferences — data retrieval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns defaults when no record exists (all 11 fields)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.findUnique.mockResolvedValueOnce(null);

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual({
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
  });

  it("returns saved preferences when record exists", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const savedPrefs = {
      dietary: ["vegan", "halal"],
      mobility: ["wheelchair"],
      languages: ["non-english-menus"],
      travelFrequency: "monthly",
      vibePreferences: ["hidden-gem"],
      travelStyleNote: "I like slow travel",
      budgetComfort: "mid-range",
      spendingPriorities: ["food-drink", "experiences"],
      accommodationTypes: ["boutique-hotel"],
      transitModes: ["walking", "public-transit"],
      preferencesNote: "Prefer quieter neighborhoods",
    };
    mockPrisma.userPreference.findUnique.mockResolvedValueOnce(
      savedPrefs as never
    );

    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(savedPrefs);
  });
});

// ---------------------------------------------------------------------------
// PATCH — auth guards
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await PATCH(makePatchRequest({ dietary: ["vegan"] }));
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// PATCH — validation
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequestInvalidJSON());
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Invalid JSON");
  });

  it("returns 400 for empty body (refine guard)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({}));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid dietary array items", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ dietary: ["pizza"] }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid travelFrequency value", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(
      makePatchRequest({ travelFrequency: "every-decade" })
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid budgetComfort value", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ budgetComfort: "luxury" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid enum in spendingPriorities", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(
      makePatchRequest({ spendingPriorities: ["flights"] })
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid enum in accommodationTypes", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(
      makePatchRequest({ accommodationTypes: ["luxury-resort"] })
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid enum in transitModes", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await PATCH(makePatchRequest({ transitModes: ["helicopter"] }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });
});

// ---------------------------------------------------------------------------
// PATCH — upsert behavior
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — upsert behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("upserts on first write with userId from session and empty defaults (all 11 fields)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const upsertResult = {
      dietary: ["vegan"],
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
    };
    mockPrisma.userPreference.upsert.mockResolvedValueOnce(
      upsertResult as never
    );

    const res = await PATCH(makePatchRequest({ dietary: ["vegan"] }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create.userId).toBe("user-abc");

    // Original 6 fields
    expect(upsertCall.create.dietary).toEqual(["vegan"]);
    expect(upsertCall.create.mobility).toEqual([]);
    expect(upsertCall.create.languages).toEqual([]);
    expect(upsertCall.create.travelFrequency).toBeNull();
    expect(upsertCall.create.vibePreferences).toEqual([]);
    expect(upsertCall.create.travelStyleNote).toBeNull();

    // New 5 fields
    expect(upsertCall.create.budgetComfort).toBeNull();
    expect(upsertCall.create.spendingPriorities).toEqual([]);
    expect(upsertCall.create.accommodationTypes).toEqual([]);
    expect(upsertCall.create.transitModes).toEqual([]);
    expect(upsertCall.create.preferencesNote).toBeNull();

    expect(upsertCall.select).toEqual(FULL_PREF_SELECT);
  });

  it("deduplicates dietary arrays before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["vegan"],
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
    } as never);

    await PATCH(makePatchRequest({ dietary: ["vegan", "vegan"] }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.dietary).toEqual(["vegan"]);
    expect(upsertCall.create.dietary).toEqual(["vegan"]);
  });

  it("deduplicates spendingPriorities before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      spendingPriorities: ["food-drink"],
    } as never);

    await PATCH(
      makePatchRequest({
        spendingPriorities: ["food-drink", "food-drink", "experiences", "experiences"],
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.spendingPriorities).toEqual([
      "food-drink",
      "experiences",
    ]);
    expect(upsertCall.create.spendingPriorities).toEqual([
      "food-drink",
      "experiences",
    ]);
  });

  it("deduplicates accommodationTypes before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      accommodationTypes: ["hostel"],
    } as never);

    await PATCH(
      makePatchRequest({
        accommodationTypes: ["hostel", "hostel", "airbnb"],
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.accommodationTypes).toEqual(["hostel", "airbnb"]);
    expect(upsertCall.create.accommodationTypes).toEqual(["hostel", "airbnb"]);
  });

  it("deduplicates transitModes before saving", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      transitModes: ["walking"],
    } as never);

    await PATCH(
      makePatchRequest({
        transitModes: ["walking", "walking", "biking"],
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.transitModes).toEqual(["walking", "biking"]);
    expect(upsertCall.create.transitModes).toEqual(["walking", "biking"]);
  });

  it("stores empty array when clearing selections", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
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
    } as never);

    await PATCH(makePatchRequest({ dietary: [] }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.dietary).toEqual([]);
    expect(upsertCall.create.dietary).toEqual([]);
  });

  it("PATCH with valid budgetComfort succeeds", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      budgetComfort: "mid-range",
    } as never);

    const res = await PATCH(makePatchRequest({ budgetComfort: "mid-range" }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.budgetComfort).toBe("mid-range");
    expect(upsertCall.create.budgetComfort).toBe("mid-range");
  });

  it("PATCH with budgetComfort null clears the field", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      budgetComfort: null,
    } as never);

    const res = await PATCH(makePatchRequest({ budgetComfort: null }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.budgetComfort).toBeNull();
    expect(upsertCall.create.budgetComfort).toBeNull();
  });

  it("PATCH with valid spendingPriorities array succeeds", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      spendingPriorities: ["food-drink", "accommodation"],
    } as never);

    const res = await PATCH(
      makePatchRequest({ spendingPriorities: ["food-drink", "accommodation"] })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.spendingPriorities).toEqual([
      "food-drink",
      "accommodation",
    ]);
  });

  it("PATCH preferencesNote empty string normalizes to null", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      preferencesNote: null,
    } as never);

    await PATCH(makePatchRequest({ preferencesNote: "" }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.preferencesNote).toBeNull();
    expect(upsertCall.create.preferencesNote).toBeNull();
  });

  it("PATCH preferencesNote whitespace-only string normalizes to null", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      preferencesNote: null,
    } as never);

    await PATCH(makePatchRequest({ preferencesNote: "   " }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.preferencesNote).toBeNull();
    expect(upsertCall.create.preferencesNote).toBeNull();
  });

  it("PATCH preferencesNote with content passes through trimmed", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      preferencesNote: "Quiet neighborhoods preferred",
    } as never);

    await PATCH(
      makePatchRequest({ preferencesNote: "  Quiet neighborhoods preferred  " })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.preferencesNote).toBe(
      "Quiet neighborhoods preferred"
    );
    expect(upsertCall.create.preferencesNote).toBe(
      "Quiet neighborhoods preferred"
    );
  });
});

// ---------------------------------------------------------------------------
// PATCH — field whitelisting & response shape
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — field whitelisting", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores extra fields like userId and id in body", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["halal"],
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
    } as never);

    await PATCH(
      makePatchRequest({
        dietary: ["halal"],
        userId: "attacker-id",
        id: "fake-id",
      })
    );

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    // userId in where/create comes from session, not body
    expect(upsertCall.where).toEqual({ userId: "user-abc" });
    expect(upsertCall.create.userId).toBe("user-abc");
    // update block should not contain userId or id
    expect(upsertCall.update).not.toHaveProperty("userId");
    expect(upsertCall.update).not.toHaveProperty("id");
  });

  it("returns only data fields in response (no id/userId/timestamps)", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["kosher"],
      mobility: [],
      languages: [],
      travelFrequency: "monthly",
      vibePreferences: [],
      travelStyleNote: null,
      budgetComfort: "splurge",
      spendingPriorities: ["experiences"],
      accommodationTypes: ["boutique-hotel"],
      transitModes: ["walking"],
      preferencesNote: null,
    } as never);

    const res = await PATCH(
      makePatchRequest({ dietary: ["kosher"], travelFrequency: "monthly" })
    );
    const json = await res.json();

    // Verify the upsert uses PREF_SELECT to limit returned fields (all 11)
    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.select).toEqual(FULL_PREF_SELECT);

    // Response should only contain data fields
    expect(json).not.toHaveProperty("id");
    expect(json).not.toHaveProperty("userId");
    expect(json).not.toHaveProperty("createdAt");
    expect(json).not.toHaveProperty("updatedAt");
  });

  it("PREF_SELECT includes all 11 preference fields", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      budgetComfort: "mix",
    } as never);

    await PATCH(makePatchRequest({ budgetComfort: "mix" }));

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0]?.[0];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const selectKeys = Object.keys((upsertCall as any)?.select ?? {});

    expect(selectKeys).toContain("dietary");
    expect(selectKeys).toContain("mobility");
    expect(selectKeys).toContain("languages");
    expect(selectKeys).toContain("travelFrequency");
    expect(selectKeys).toContain("vibePreferences");
    expect(selectKeys).toContain("travelStyleNote");
    expect(selectKeys).toContain("budgetComfort");
    expect(selectKeys).toContain("spendingPriorities");
    expect(selectKeys).toContain("accommodationTypes");
    expect(selectKeys).toContain("transitModes");
    expect(selectKeys).toContain("preferencesNote");
    expect(selectKeys).toHaveLength(11);
  });
});

// ---------------------------------------------------------------------------
// PATCH — new enum validation (dairy-free, pescatarian, no-pork, service-animal, limited-stamina)
// ---------------------------------------------------------------------------
describe("PATCH /api/settings/preferences — expanded enum coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts new dietary options: dairy-free, pescatarian, no-pork", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      dietary: ["dairy-free", "pescatarian", "no-pork"],
    } as never);

    const res = await PATCH(
      makePatchRequest({ dietary: ["dairy-free", "pescatarian", "no-pork"] })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.dietary).toEqual([
      "dairy-free",
      "pescatarian",
      "no-pork",
    ]);
  });

  it("accepts new mobility options: service-animal, limited-stamina", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      mobility: ["service-animal", "limited-stamina"],
    } as never);

    const res = await PATCH(
      makePatchRequest({ mobility: ["service-animal", "limited-stamina"] })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.mobility).toEqual([
      "service-animal",
      "limited-stamina",
    ]);
  });

  it("accepts all valid budgetComfort enum values", async () => {
    const validValues = ["budget", "mid-range", "splurge", "mix"];

    for (const value of validValues) {
      vi.clearAllMocks();
      mockGetServerSession.mockResolvedValueOnce(authedSession as never);
      mockPrisma.userPreference.upsert.mockResolvedValueOnce({
        budgetComfort: value,
      } as never);

      const res = await PATCH(makePatchRequest({ budgetComfort: value }));
      expect(res.status).toBe(200);
    }
  });

  it("accepts all valid transitModes enum values", async () => {
    const validModes = [
      "walking",
      "public-transit",
      "rideshare",
      "rental-car",
      "biking",
      "scooter",
    ];

    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      transitModes: validModes,
    } as never);

    const res = await PATCH(makePatchRequest({ transitModes: validModes }));
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.transitModes).toEqual(validModes);
  });

  it("accepts all valid accommodationTypes enum values", async () => {
    const validTypes = [
      "hostel",
      "boutique-hotel",
      "chain-hotel",
      "airbnb",
      "camping",
    ];

    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.userPreference.upsert.mockResolvedValueOnce({
      accommodationTypes: validTypes,
    } as never);

    const res = await PATCH(
      makePatchRequest({ accommodationTypes: validTypes })
    );
    expect(res.status).toBe(200);

    const upsertCall = mockPrisma.userPreference.upsert.mock.calls[0][0];
    expect(upsertCall.update.accommodationTypes).toEqual(validTypes);
  });
});
