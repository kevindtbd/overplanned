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

  // ---- Different length codes (timingSafeEqual requires same length) ----

  it("returns 401 when submitted code is shorter than BETA_CODE", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "SEC" }));
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Invalid beta code");
  });

  it("returns 401 when submitted code is longer than BETA_CODE", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "SECRET123EXTRACHARACTERS" }));
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Invalid beta code");
  });

  it("returns 401 for single-character mismatch (same length)", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "SECRET124" }));
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error).toBe("Invalid beta code");
  });

  // ---- Rate limiting ----

  it("returns 429 when rate limiter blocks the request", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();

    const { rateLimit } = await import("@/lib/rate-limit");
    const { NextResponse } = await import("next/server");
    vi.mocked(rateLimit).mockReturnValueOnce(
      NextResponse.json(
        { error: "Too many requests, please try again later" },
        { status: 429 }
      )
    );

    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const res = await POST(makeRequest({ code: "SECRET123" }));
    expect(res.status).toBe(429);
    const json = await res.json();
    expect(json.error).toBe("Too many requests, please try again later");
  });

  it("calls rateLimit with the request and authenticated preset", async () => {
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const { rateLimit } = await import("@/lib/rate-limit");
    vi.mocked(rateLimit).mockReturnValue(null);

    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const req = makeRequest({ code: "SECRET123" });
    await POST(req);

    expect(rateLimit).toHaveBeenCalledTimes(1);
    expect(rateLimit).toHaveBeenCalledWith(req, {
      limit: 10,
      windowMs: 60 * 1000,
    });
  });

  // ---- Structural: timing-safe comparison ----

  it("uses crypto.timingSafeEqual in source (not naive ===)", async () => {
    // Structural verification: read the route source and confirm it calls
    // crypto.timingSafeEqual. This guards against someone replacing the
    // timing-safe comparison with a naive string === check.
    const fs = await import("fs");
    const path = await import("path");
    const routePath = path.resolve(
      __dirname,
      "../../app/api/auth/beta-validate/route.ts"
    );
    const source = fs.readFileSync(routePath, "utf-8");

    expect(source).toContain("crypto.timingSafeEqual");
    expect(source).toContain("codeBuffer.length !== betaBuffer.length");
  });

  it("rejects different-length codes without leaking timing info", async () => {
    // When code lengths differ the route short-circuits with a length check
    // BEFORE calling timingSafeEqual (which throws on mismatched lengths).
    // We verify the short code and long code both get the same 401 response.
    process.env = { ...originalEnv, BETA_CODE: "SECRET123" };

    vi.resetModules();
    const mod = await import("../../app/api/auth/beta-validate/route");
    POST = mod.POST;

    const shortRes = await POST(makeRequest({ code: "S" }));
    const longRes = await POST(
      makeRequest({ code: "SECRET123_PLUS_EXTRA_STUFF" })
    );

    expect(shortRes.status).toBe(401);
    expect(longRes.status).toBe(401);

    const shortJson = await shortRes.json();
    const longJson = await longRes.json();
    expect(shortJson.error).toBe("Invalid beta code");
    expect(longJson.error).toBe("Invalid beta code");
  });
});
