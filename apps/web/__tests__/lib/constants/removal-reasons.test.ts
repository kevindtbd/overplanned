/**
 * Tests for lib/constants/removal-reasons.ts
 *
 * Verifies:
 * - REMOVAL_REASONS exports all 4 reasons
 * - Each reason has the expected shape (id, label, signalWeight)
 * - RemovalReason type includes all valid ids
 * - DEFAULT_REMOVAL_REASON is 'not_interested'
 * - Signal weights match the taxonomy spec
 */

import { describe, it, expect } from "vitest";
import {
  REMOVAL_REASONS,
  DEFAULT_REMOVAL_REASON,
  type RemovalReason,
} from "@/lib/constants/removal-reasons";

describe("REMOVAL_REASONS", () => {
  it("exports exactly 4 reasons", () => {
    expect(REMOVAL_REASONS).toHaveLength(4);
  });

  it("includes not_interested with signalWeight -1.0", () => {
    const reason = REMOVAL_REASONS.find((r) => r.id === "not_interested");
    expect(reason).toBeDefined();
    expect(reason?.label).toBe("Not my thing");
    expect(reason?.signalWeight).toBe(-1.0);
  });

  it("includes wrong_vibe with signalWeight -0.6", () => {
    const reason = REMOVAL_REASONS.find((r) => r.id === "wrong_vibe");
    expect(reason).toBeDefined();
    expect(reason?.label).toBe("Doesn't match the vibe");
    expect(reason?.signalWeight).toBe(-0.6);
  });

  it("includes already_been with signalWeight 0.0 (informational only)", () => {
    const reason = REMOVAL_REASONS.find((r) => r.id === "already_been");
    expect(reason).toBeDefined();
    expect(reason?.label).toBe("I've been here before");
    expect(reason?.signalWeight).toBe(0.0);
  });

  it("includes too_far with signalWeight 0.0 (logistics, not preference)", () => {
    const reason = REMOVAL_REASONS.find((r) => r.id === "too_far");
    expect(reason).toBeDefined();
    expect(reason?.label).toBe("Too far away");
    expect(reason?.signalWeight).toBe(0.0);
  });

  it("all reasons have required fields (id, label, signalWeight)", () => {
    for (const reason of REMOVAL_REASONS) {
      expect(reason).toHaveProperty("id");
      expect(reason).toHaveProperty("label");
      expect(reason).toHaveProperty("signalWeight");
      expect(typeof reason.id).toBe("string");
      expect(typeof reason.label).toBe("string");
      expect(typeof reason.signalWeight).toBe("number");
    }
  });

  it("ids are unique", () => {
    const ids = REMOVAL_REASONS.map((r) => r.id);
    const unique = new Set(ids);
    expect(unique.size).toBe(ids.length);
  });

  it("signal weights are within valid range [-1.0, 0.0]", () => {
    for (const reason of REMOVAL_REASONS) {
      expect(reason.signalWeight).toBeGreaterThanOrEqual(-1.0);
      expect(reason.signalWeight).toBeLessThanOrEqual(0.0);
    }
  });
});

describe("DEFAULT_REMOVAL_REASON", () => {
  it("is not_interested", () => {
    expect(DEFAULT_REMOVAL_REASON).toBe("not_interested");
  });

  it("is a valid RemovalReason id", () => {
    const validIds = REMOVAL_REASONS.map((r) => r.id);
    expect(validIds).toContain(DEFAULT_REMOVAL_REASON);
  });
});

describe("RemovalReason type", () => {
  it("accepts all valid ids at compile time (runtime smoke check)", () => {
    // These assignments would fail TypeScript if RemovalReason type is wrong
    const ids: RemovalReason[] = [
      "not_interested",
      "wrong_vibe",
      "already_been",
      "too_far",
    ];
    expect(ids).toHaveLength(4);
  });
});
