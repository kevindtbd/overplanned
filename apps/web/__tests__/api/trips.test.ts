/**
 * Unit tests for trip Zod validation schemas.
 * No Prisma mocking needed — pure schema validation only.
 */

import { describe, it, expect } from "vitest";
import { createTripSchema, createDraftSchema, updateTripSchema } from "@/lib/validations/trip";

const validLeg = {
  city: "Kyoto",
  country: "Japan",
  timezone: "Asia/Tokyo",
  destination: "Kyoto, Japan",
  startDate: "2026-04-01T00:00:00.000Z",
  endDate: "2026-04-07T00:00:00.000Z",
};

const validCreatePayload = {
  startDate: "2026-04-01T00:00:00.000Z",
  endDate: "2026-04-07T00:00:00.000Z",
  mode: "solo" as const,
  legs: [validLeg],
};

describe("createTripSchema", () => {
  it("accepts a fully valid payload", () => {
    const result = createTripSchema.safeParse(validCreatePayload);
    expect(result.success).toBe(true);
  });

  it("accepts an optional name field", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      name: "Spring Cherry Blossom Trip",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBe("Spring Cherry Blossom Trip");
    }
  });

  it("accepts payload without name (name is optional)", () => {
    const { ...payload } = validCreatePayload;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBeUndefined();
    }
  });

  it("rejects when legs array is missing", () => {
    const { legs, ...payload } = validCreatePayload;
    void legs;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  it("rejects when legs array is empty", () => {
    const result = createTripSchema.safeParse({ ...validCreatePayload, legs: [] });
    expect(result.success).toBe(false);
  });

  it("rejects when leg destination is missing", () => {
    const { destination, ...legWithoutDest } = validLeg;
    void destination;
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      legs: [legWithoutDest],
    });
    expect(result.success).toBe(false);
  });

  it("rejects when leg city is missing", () => {
    const { city, ...legWithoutCity } = validLeg;
    void city;
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      legs: [legWithoutCity],
    });
    expect(result.success).toBe(false);
  });

  it("rejects when leg country is missing", () => {
    const { country, ...legWithoutCountry } = validLeg;
    void country;
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      legs: [legWithoutCountry],
    });
    expect(result.success).toBe(false);
  });

  it("accepts when leg timezone is missing (optional)", () => {
    const { timezone, ...legWithoutTz } = validLeg;
    void timezone;
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      legs: [legWithoutTz],
    });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid mode value", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      mode: "family",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.mode).toBeDefined();
    }
  });

  it("rejects a name that exceeds 200 characters", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      name: "A".repeat(201),
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.name).toBeDefined();
    }
  });

  it("rejects an empty string name", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      name: "",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.name).toBeDefined();
    }
  });

  it("rejects an invalid startDate format", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: "April 1, 2026",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.startDate).toBeDefined();
    }
  });

  it("accepts optional personaSeed as a record", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      personaSeed: { pace: "slow", focus: "food" },
    });
    expect(result.success).toBe(true);
  });

  it("accepts group mode", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      mode: "group",
    });
    expect(result.success).toBe(true);
  });

  it("rejects endDate <= startDate (zero-night trip)", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: "2026-04-07T00:00:00.000Z",
      endDate: "2026-04-07T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("rejects endDate before startDate", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: "2026-04-07T00:00:00.000Z",
      endDate: "2026-04-01T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("rejects trip exceeding 14 nights", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-16T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("accepts exactly 14 nights", () => {
    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-15T00:00:00.000Z",
      legs: [{
        ...validLeg,
        startDate: "2026-04-01T00:00:00.000Z",
        endDate: "2026-04-15T00:00:00.000Z",
      }],
    });
    expect(result.success).toBe(true);
  });

  it("rejects startDate more than 2 years in the future", () => {
    const farFuture = new Date();
    farFuture.setFullYear(farFuture.getFullYear() + 3);
    const farEnd = new Date(farFuture);
    farEnd.setDate(farEnd.getDate() + 3);

    const result = createTripSchema.safeParse({
      ...validCreatePayload,
      startDate: farFuture.toISOString(),
      endDate: farEnd.toISOString(),
    });
    expect(result.success).toBe(false);
  });
});

describe("createDraftSchema — date range validation", () => {
  const validDraftLeg = {
    city: "Tokyo",
    country: "Japan",
    timezone: "Asia/Tokyo",
    destination: "Tokyo, Japan",
    startDate: "2026-06-01T00:00:00.000Z",
    endDate: "2026-06-07T00:00:00.000Z",
  };

  const validDraft = {
    startDate: "2026-06-01T00:00:00.000Z",
    endDate: "2026-06-07T00:00:00.000Z",
    legs: [validDraftLeg],
  };

  it("accepts a valid draft payload", () => {
    const result = createDraftSchema.safeParse(validDraft);
    expect(result.success).toBe(true);
  });

  it("rejects endDate <= startDate", () => {
    const result = createDraftSchema.safeParse({
      ...validDraft,
      endDate: validDraft.startDate,
    });
    expect(result.success).toBe(false);
  });

  it("rejects trip exceeding 14 nights", () => {
    const result = createDraftSchema.safeParse({
      ...validDraft,
      endDate: "2026-06-16T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("accepts exactly 14 nights", () => {
    const result = createDraftSchema.safeParse({
      ...validDraft,
      endDate: "2026-06-15T00:00:00.000Z",
      legs: [{
        ...validDraftLeg,
        endDate: "2026-06-15T00:00:00.000Z",
      }],
    });
    expect(result.success).toBe(true);
  });
});

describe("updateTripSchema", () => {
  it("accepts an empty object (all fields optional)", () => {
    const result = updateTripSchema.safeParse({});
    expect(result.success).toBe(true);
  });

  it("accepts name-only update", () => {
    const result = updateTripSchema.safeParse({ name: "Renamed Trip" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBe("Renamed Trip");
    }
  });

  it("accepts status-only update", () => {
    const result = updateTripSchema.safeParse({ status: "active" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.status).toBe("active");
    }
  });

  it("accepts planningProgress-only update", () => {
    const result = updateTripSchema.safeParse({ planningProgress: 0.5 });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.planningProgress).toBe(0.5);
    }
  });

  it("accepts a full partial update combining all fields", () => {
    const result = updateTripSchema.safeParse({
      name: "Updated Trip",
      status: "completed",
      planningProgress: 1,
    });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid status value", () => {
    const result = updateTripSchema.safeParse({ status: "cancelled" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.status).toBeDefined();
    }
  });

  it("rejects planningProgress below 0", () => {
    const result = updateTripSchema.safeParse({ planningProgress: -0.1 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.planningProgress).toBeDefined();
    }
  });

  it("rejects planningProgress above 1", () => {
    const result = updateTripSchema.safeParse({ planningProgress: 1.1 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.planningProgress).toBeDefined();
    }
  });

  it("rejects an empty string name", () => {
    const result = updateTripSchema.safeParse({ name: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.name).toBeDefined();
    }
  });

  it("rejects a name over 200 characters", () => {
    const result = updateTripSchema.safeParse({ name: "B".repeat(201) });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.name).toBeDefined();
    }
  });

  it("accepts all valid status values", () => {
    const statuses = ["draft", "planning", "active", "completed", "archived"] as const;
    for (const status of statuses) {
      const result = updateTripSchema.safeParse({ status });
      expect(result.success, `status '${status}' should be valid`).toBe(true);
    }
  });

  it("rejects when both dates present and endDate <= startDate", () => {
    const result = updateTripSchema.safeParse({
      startDate: "2026-04-07T00:00:00.000Z",
      endDate: "2026-04-01T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("rejects when both dates present and exceeds 14 nights", () => {
    const result = updateTripSchema.safeParse({
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-16T00:00:00.000Z",
    });
    expect(result.success).toBe(false);
  });

  it("accepts single date update (no cross-field check)", () => {
    const result = updateTripSchema.safeParse({
      startDate: "2026-04-01T00:00:00.000Z",
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid date range when both present", () => {
    const result = updateTripSchema.safeParse({
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-15T00:00:00.000Z",
    });
    expect(result.success).toBe(true);
  });
});
