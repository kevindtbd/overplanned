/**
 * Unit tests for trip Zod validation schemas.
 * No Prisma mocking needed — pure schema validation only.
 */

import { describe, it, expect } from "vitest";
import { createTripSchema, updateTripSchema } from "@/lib/validations/trip";

const validCreatePayload = {
  destination: "Kyoto, Japan",
  city: "Kyoto",
  country: "Japan",
  timezone: "Asia/Tokyo",
  startDate: "2026-04-01T00:00:00.000Z",
  endDate: "2026-04-07T00:00:00.000Z",
  mode: "solo" as const,
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

  it("rejects when destination is missing", () => {
    const { destination, ...payload } = validCreatePayload;
    void destination;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.destination).toBeDefined();
    }
  });

  it("rejects when city is missing", () => {
    const { city, ...payload } = validCreatePayload;
    void city;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.city).toBeDefined();
    }
  });

  it("rejects when country is missing", () => {
    const { country, ...payload } = validCreatePayload;
    void country;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.country).toBeDefined();
    }
  });

  it("rejects when timezone is missing", () => {
    const { timezone, ...payload } = validCreatePayload;
    void timezone;
    const result = createTripSchema.safeParse(payload);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.timezone).toBeDefined();
    }
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
    const result = updateTripSchema.safeParse({ status: "archived" });
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
    const statuses = ["draft", "active", "completed", "cancelled"] as const;
    for (const status of statuses) {
      const result = updateTripSchema.safeParse({ status });
      expect(result.success, `status '${status}' should be valid`).toBe(true);
    }
  });
});
