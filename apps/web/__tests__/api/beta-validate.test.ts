/**
 * Tests for the beta code gate endpoint:
 *   POST /api/auth/beta-validate
 *
 * Uses Vitest. No Prisma or auth mocks needed — this route is stateless.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";

// ---- Mock rate limiter so it never blocks tests ----

vi.mock("@/lib/rate-limit", () => ({
  rateLimit: vi.fn().mockReturnValue(null),
  rateLimitPresets: {
    authenticated: { limit: 10, windowMs: 60 * 1000 },
  },
}));

// ---- Helpers ----

function makeRequest(body: unknown) {
  return new NextRequest("http://localhost:3000/api/auth/beta-validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function makeMalformedRequest() {
  return new NextRequest("http://localhost:3000/api/auth/beta-validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "not-json{{{",
  });
}

// ================================================================
// POST /api/auth/beta-validate
// ================================================================

describe("POST /api/auth/beta-validate", () => {
  let POST: typeof import("../../app/api/auth/beta-validate/route").POST;
  const originalEnv = process.env;

  beforeEach(async () => {
    vi.resetAllMocks();
    // Re-mock rate limiter after reset
    const { rateLimit } = await import("@/lib/rate-limit");
    vi.mocked(rateLimit).mockReturnValue(null);

    // Re-import the route fresh so env changes take effect
    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  // ---- No gate configured ----

  it("returns 200 + { valid: true } when BETA_CODE env var is not set", async () => {
    process.env = { ...originalEnv };
    delete process.env.BETA_CODE;

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "anything" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ valid: true });
  });

  it("returns 200 + { valid: true } when BETA_CODE is empty string", async () => {
    process.env = { ...originalEnv, BETA_CODE: "" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ valid: true });
  });

  // ---- Valid code ----

  it("returns 200 + { valid: true } for correct beta code", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "SECRET123" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ valid: true });
  });

  it("trims whitespace from submitted code before comparing", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "  SECRET123  " }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ valid: true });
  });

  // ---- Invalid code ----

  it("returns 401 for wrong beta code", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "WRONGCODE" }));
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Invalid beta code");
  });

  it("returns 401 for code with different casing", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "secret123" }));
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Invalid beta code");
  });

  // ---- Missing / empty code ----

  it("returns 400 when code field is missing from body", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Code required");
  });

  it("returns 400 when code is an empty string", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "" }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Code required");
  });

  it("returns 400 when code is whitespace only", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "   " }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Code required");
  });

  // ---- Malformed request body ----

  it("returns 400 for malformed JSON body", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeMalformedRequest());
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe("Invalid JSON");
  });
});
