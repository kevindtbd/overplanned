import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  shouldAutoTransition,
  validateTransition,
  getWritableFields,
  VALID_TRANSITIONS,
  WRITABLE_BY_STATUS,
} from "@/lib/trip-status";

describe("shouldAutoTransition", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns true when status is planning and startDate is in the past", () => {
    expect(
      shouldAutoTransition("planning", new Date("2026-06-14T00:00:00Z"))
    ).toBe(true);
  });

  it("returns true when status is planning and startDate equals exactly now", () => {
    expect(
      shouldAutoTransition("planning", new Date("2026-06-15T12:00:00Z"))
    ).toBe(true);
  });

  it("returns false when status is planning and startDate is in the future", () => {
    expect(
      shouldAutoTransition("planning", new Date("2026-06-16T00:00:00Z"))
    ).toBe(false);
  });

  it("returns false when status is active regardless of startDate", () => {
    expect(
      shouldAutoTransition("active", new Date("2026-06-01T00:00:00Z"))
    ).toBe(false);
  });

  it("returns false when status is completed regardless of startDate", () => {
    expect(
      shouldAutoTransition("completed", new Date("2026-06-01T00:00:00Z"))
    ).toBe(false);
  });

  it("returns false when status is archived regardless of startDate", () => {
    expect(
      shouldAutoTransition("archived", new Date("2026-06-01T00:00:00Z"))
    ).toBe(false);
  });


  it("returns false when status is draft", () => {
    expect(
      shouldAutoTransition("draft", new Date("2026-06-01T00:00:00Z"))
    ).toBe(false);
  });

  it("returns true when startDate is 1ms before now", () => {
    expect(
      shouldAutoTransition(
        "planning",
        new Date("2026-06-15T11:59:59.999Z")
      )
    ).toBe(true);
  });

  it("returns false when startDate is 1ms after now", () => {
    expect(
      shouldAutoTransition(
        "planning",
        new Date("2026-06-15T12:00:00.001Z")
      )
    ).toBe(false);
  });
});

describe("validateTransition", () => {
  it("allows draft -> planning", () => {
    expect(validateTransition("draft", "planning")).toBe(true);
  });

  it("allows planning -> active", () => {
    expect(validateTransition("planning", "active")).toBe(true);
  });

  it("allows active -> completed", () => {
    expect(validateTransition("active", "completed")).toBe(true);
  });

  it("allows completed -> archived", () => {
    expect(validateTransition("completed", "archived")).toBe(true);
  });

  it("rejects draft -> active (skips planning)", () => {
    expect(validateTransition("draft", "active")).toBe(false);
  });

  it("rejects draft -> completed", () => {
    expect(validateTransition("draft", "completed")).toBe(false);
  });

  it("allows draft -> archived", () => {
    expect(validateTransition("draft", "archived")).toBe(true);
  });

  it("rejects planning -> draft (backward transition)", () => {
    expect(validateTransition("planning", "draft")).toBe(false);
  });

  it("rejects planning -> completed (skips active)", () => {
    expect(validateTransition("planning", "completed")).toBe(false);
  });

  it("rejects active -> planning (backward transition)", () => {
    expect(validateTransition("active", "planning")).toBe(false);
  });

  it("rejects completed -> planning (backward transition)", () => {
    expect(validateTransition("completed", "planning")).toBe(false);
  });

  it("rejects completed -> active (backward transition)", () => {
    expect(validateTransition("completed", "active")).toBe(false);
  });

  it("rejects archived -> anything", () => {
    expect(validateTransition("archived", "completed")).toBe(false);
    expect(validateTransition("archived", "planning")).toBe(false);
    expect(validateTransition("archived", "draft")).toBe(false);
  });

  it("rejects unknown current status", () => {
    expect(validateTransition("nonexistent", "planning")).toBe(false);
  });

  it("returns false when requested status is same as current (not a transition)", () => {
    expect(validateTransition("planning", "planning")).toBe(false);
    expect(validateTransition("draft", "draft")).toBe(false);
  });
});

describe("getWritableFields", () => {
  it("returns correct writable fields for draft", () => {
    const fields = getWritableFields("draft");
    expect(fields.has("name")).toBe(true);
    expect(fields.has("startDate")).toBe(true);
    expect(fields.has("endDate")).toBe(true);
    expect(fields.has("mode")).toBe(true);
    expect(fields.has("presetTemplate")).toBe(true);
    expect(fields.has("personaSeed")).toBe(true);
    expect(fields.has("status")).toBe(true);
  });

  it("returns correct writable fields for planning", () => {
    const fields = getWritableFields("planning");
    expect(fields.has("name")).toBe(true);
    expect(fields.has("status")).toBe(true);
    expect(fields.has("planningProgress")).toBe(true);
    expect(fields.has("startDate")).toBe(true);
    expect(fields.has("endDate")).toBe(true);
    expect(fields.has("mode")).toBe(true);
    expect(fields.has("presetTemplate")).toBe(false);
    expect(fields.has("personaSeed")).toBe(false);
  });

  it("returns correct writable fields for active", () => {
    const fields = getWritableFields("active");
    expect(fields.has("name")).toBe(true);
    expect(fields.has("status")).toBe(true);
    expect(fields.has("planningProgress")).toBe(true);
    expect(fields.has("startDate")).toBe(false);
    expect(fields.has("mode")).toBe(false);
  });

  it("returns only status for completed", () => {
    const fields = getWritableFields("completed");
    expect(fields.has("status")).toBe(true);
    expect(fields.size).toBe(1);
  });

  it("returns empty set for archived (terminal state)", () => {
    const fields = getWritableFields("archived");
    expect(fields.size).toBe(0);
  });

  it("returns empty set for unknown status", () => {
    const fields = getWritableFields("nonexistent");
    expect(fields.size).toBe(0);
  });

  it("WRITABLE_BY_STATUS covers all statuses in VALID_TRANSITIONS", () => {
    const transitionStatuses = Object.keys(VALID_TRANSITIONS);
    const writableStatuses = Object.keys(WRITABLE_BY_STATUS);
    for (const status of transitionStatuses) {
      expect(writableStatuses).toContain(status);
    }
  });
});
