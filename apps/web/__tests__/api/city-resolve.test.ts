/**
 * Route handler tests for POST /api/cities/resolve
 * Tests auth guards, validation, rate limiting, resolver delegation, and error handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/auth/config", () => ({ authOptions: {} }));

vi.mock("@/lib/city-resolver", () => ({
  resolveCity: vi.fn(),
  checkRateLimit: vi.fn(),
}));

const { getServerSession } = await import("next-auth");
const { resolveCity, checkRateLimit } = await import("@/lib/city-resolver");
const { POST } = await import("../../app/api/cities/resolve/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockResolveCity = vi.mocked(resolveCity);
const mockCheckRateLimit = vi.mocked(checkRateLimit);

const USER_ID = "33333333-3333-3333-3333-333333333333";

function makeRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/cities/resolve", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("POST /api/cities/resolve", () => {
  // ---- Auth ----

  it("returns 401 without a session", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const res = await POST(makeRequest({ city: "Hanoi" }));
    expect(res.status).toBe(401);

    const json = await res.json();
    expect(json.error).toBe("Unauthorized");
  });

  // ---- Validation ----

  it("returns 400 for missing city field", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });

    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);

    const json = await res.json();
    expect(json.error).toBe("Validation failed");
    expect(json.details).toBeDefined();
  });

  it("returns 400 for empty city string", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });

    const res = await POST(makeRequest({ city: "" }));
    expect(res.status).toBe(400);

    const json = await res.json();
    expect(json.error).toBe("Validation failed");
  });

  it("returns 400 for invalid JSON body", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });

    const req = new NextRequest("http://localhost:3000/api/cities/resolve", {
      method: "POST",
      body: "not-json{{",
      headers: { "Content-Type": "application/json" },
    });

    const res = await POST(req);
    expect(res.status).toBe(400);

    const json = await res.json();
    expect(json.error).toBe("Invalid JSON");
  });

  // ---- Rate limiting ----

  it("returns 429 when rate limited", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });
    mockCheckRateLimit.mockReturnValue(false);

    const res = await POST(makeRequest({ city: "Hanoi" }));
    expect(res.status).toBe(429);

    const json = await res.json();
    expect(json.error).toMatch(/rate limit/i);
  });

  it("calls checkRateLimit with the userId", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });
    mockCheckRateLimit.mockReturnValue(true);
    mockResolveCity.mockResolvedValue({
      city: "Hanoi",
      country: "Vietnam",
      timezone: "Asia/Ho_Chi_Minh",
      destination: "Hanoi, Vietnam",
    });

    await POST(makeRequest({ city: "Hanoi" }));

    expect(mockCheckRateLimit).toHaveBeenCalledWith(USER_ID);
  });

  // ---- Success ----

  it("returns 200 with resolved city data on success", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });
    mockCheckRateLimit.mockReturnValue(true);

    const resolved = {
      city: "Hanoi",
      country: "Vietnam",
      timezone: "Asia/Ho_Chi_Minh",
      destination: "Hanoi, Vietnam",
    };
    mockResolveCity.mockResolvedValue(resolved);

    const res = await POST(makeRequest({ city: "Hanoi" }));
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual(resolved);
  });

  it("calls resolveCity with the parsed city name", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });
    mockCheckRateLimit.mockReturnValue(true);
    mockResolveCity.mockResolvedValue({
      city: "Hanoi",
      country: "Vietnam",
      timezone: "Asia/Ho_Chi_Minh",
      destination: "Hanoi, Vietnam",
    });

    await POST(makeRequest({ city: "Hanoi" }));

    expect(mockResolveCity).toHaveBeenCalledWith("Hanoi");
  });

  // ---- Error handling ----

  it("returns 500 when resolveCity throws", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: USER_ID } });
    mockCheckRateLimit.mockReturnValue(true);
    mockResolveCity.mockRejectedValue(new Error("LLM unavailable"));

    const res = await POST(makeRequest({ city: "Hanoi" }));
    expect(res.status).toBe(500);

    const json = await res.json();
    expect(json.error).toBe("Internal server error");
  });
});
