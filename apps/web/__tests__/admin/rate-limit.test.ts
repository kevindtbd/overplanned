import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { checkRateLimit, resetRateLimits } from "@/lib/admin/rate-limit";

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers();
  resetRateLimits();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("rate-limit", () => {
  it("allows the first request", () => {
    const result = checkRateLimit("user-a", "GET");
    expect(result.allowed).toBe(true);
  });

  it("accumulates up to READ limit (60) then rejects", () => {
    for (let i = 0; i < 60; i++) {
      const r = checkRateLimit("user-a", "GET");
      expect(r.allowed).toBe(true);
    }
    const rejected = checkRateLimit("user-a", "GET");
    expect(rejected.allowed).toBe(false);
  });

  it("accumulates up to MUTATION limit (10) then rejects", () => {
    for (let i = 0; i < 10; i++) {
      const r = checkRateLimit("user-a", "POST");
      expect(r.allowed).toBe(true);
    }
    const rejected = checkRateLimit("user-a", "POST");
    expect(rejected.allowed).toBe(false);
  });

  it("keeps different userId keys independent", () => {
    // Exhaust user-a mutation limit
    for (let i = 0; i < 10; i++) {
      checkRateLimit("user-a", "POST");
    }
    expect(checkRateLimit("user-a", "POST").allowed).toBe(false);
    // user-b should still be allowed
    expect(checkRateLimit("user-b", "POST").allowed).toBe(true);
  });

  it("tracks read and mutation limits separately", () => {
    // Exhaust mutation limit for user-a
    for (let i = 0; i < 10; i++) {
      checkRateLimit("user-a", "POST");
    }
    expect(checkRateLimit("user-a", "POST").allowed).toBe(false);
    // Read should still be allowed
    expect(checkRateLimit("user-a", "GET").allowed).toBe(true);
  });

  it("allows requests again after window expires (60s)", () => {
    // Exhaust read limit
    for (let i = 0; i < 60; i++) {
      checkRateLimit("user-a", "GET");
    }
    expect(checkRateLimit("user-a", "GET").allowed).toBe(false);

    // Advance past the 60s window
    vi.advanceTimersByTime(61_000);

    const result = checkRateLimit("user-a", "GET");
    expect(result.allowed).toBe(true);
  });

  it("returns a retryAfter value between 1 and 60 when rejected", () => {
    for (let i = 0; i < 10; i++) {
      checkRateLimit("user-a", "DELETE");
    }
    const rejected = checkRateLimit("user-a", "DELETE");
    expect(rejected.allowed).toBe(false);
    expect(rejected.retryAfter).toBeGreaterThanOrEqual(1);
    expect(rejected.retryAfter).toBeLessThanOrEqual(60);
  });

  it("resetRateLimits() clears all state", () => {
    // Exhaust both limits
    for (let i = 0; i < 60; i++) {
      checkRateLimit("user-a", "GET");
    }
    for (let i = 0; i < 10; i++) {
      checkRateLimit("user-a", "POST");
    }
    expect(checkRateLimit("user-a", "GET").allowed).toBe(false);
    expect(checkRateLimit("user-a", "POST").allowed).toBe(false);

    resetRateLimits();

    expect(checkRateLimit("user-a", "GET").allowed).toBe(true);
    expect(checkRateLimit("user-a", "POST").allowed).toBe(true);
  });
});
