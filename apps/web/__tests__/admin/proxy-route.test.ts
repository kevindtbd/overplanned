import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";

// ---------------------------------------------------------------------------
// Mocks — must be before imports of the route module
// ---------------------------------------------------------------------------

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { findUnique: vi.fn() },
  },
}));

vi.mock("@/lib/admin/sign-request", () => ({
  signAdminRequest: vi.fn().mockReturnValue({
    "X-Admin-Signature": "mock-sig",
    "X-Admin-Timestamp": "1700000000",
    "X-Admin-User-Id": "admin-uuid",
    "X-Admin-Body-Hash": "mock-hash",
  }),
}));

vi.mock("@/lib/admin/rate-limit", () => ({
  checkRateLimit: vi.fn().mockReturnValue({ allowed: true }),
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import { getServerSession } from "next-auth";
import { prisma } from "@/lib/prisma";
import { signAdminRequest } from "@/lib/admin/sign-request";
import { checkRateLimit } from "@/lib/admin/rate-limit";
import { GET, POST, PATCH, DELETE } from "@/app/api/admin/[...path]/route";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ADMIN_USER_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

function makeRequest(
  method: string,
  path: string,
  options: { body?: string; contentType?: string; query?: string } = {}
): NextRequest {
  const base = "http://localhost:3000";
  const url = `${base}/api/admin/${path}${options.query ? `?${options.query}` : ""}`;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const init: any = { method };
  const headers: Record<string, string> = {};
  if (options.body !== undefined) {
    init.body = options.body;
    headers["content-type"] = options.contentType ?? "application/json";
  } else if (method !== "GET") {
    headers["content-type"] = options.contentType ?? "application/json";
  }
  init.headers = headers;
  return new NextRequest(url, init);
}

function makeParams(path: string): { params: Promise<{ path: string[] }> } {
  const segments = path.split("/").filter(Boolean);
  return { params: Promise.resolve({ path: segments }) };
}

function mockValidAdmin() {
  vi.mocked(getServerSession).mockResolvedValue({
    user: { id: ADMIN_USER_ID, name: "Admin", email: "admin@test.com" },
    expires: "2099-01-01",
  });
  vi.mocked(prisma.user.findUnique).mockResolvedValue({
    systemRole: "admin",
  } as never);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("INTERNAL_API_URL", "http://internal:8000");
  // Re-apply default mock returns after resetAllMocks
  vi.mocked(signAdminRequest).mockReturnValue({
    "X-Admin-Signature": "mock-sig",
    "X-Admin-Timestamp": "1700000000",
    "X-Admin-User-Id": ADMIN_USER_ID,
    "X-Admin-Body-Hash": "mock-hash",
  });
  vi.mocked(checkRateLimit).mockReturnValue({ allowed: true });
  // Default: upstream returns 200
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    })
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  globalThis.fetch = originalFetch;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("admin proxy route", () => {
  // -- Auth ----------------------------------------------------------------

  it("returns 401 when no session", async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toMatch(/authentication/i);
  });

  it("returns 403 when user is not admin in DB", async () => {
    vi.mocked(getServerSession).mockResolvedValue({
      user: { id: ADMIN_USER_ID, name: "User", email: "u@test.com" },
      expires: "2099-01-01",
    });
    vi.mocked(prisma.user.findUnique).mockResolvedValue({
      systemRole: "user",
    } as never);
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.error).toMatch(/admin/i);
  });

  it("returns 403 when session exists but DB returns null user", async () => {
    vi.mocked(getServerSession).mockResolvedValue({
      user: { id: ADMIN_USER_ID, name: "Ghost", email: "g@test.com" },
      expires: "2099-01-01",
    });
    vi.mocked(prisma.user.findUnique).mockResolvedValue(null);
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(403);
  });

  // -- Happy path ----------------------------------------------------------

  it("returns 200 when valid admin, upstream returns 200", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
  });

  // -- Rate limiting -------------------------------------------------------

  it("returns 429 when rate limit exceeded", async () => {
    mockValidAdmin();
    vi.mocked(checkRateLimit).mockReturnValue({
      allowed: false,
      retryAfter: 30,
    });
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe("30");
  });

  // -- Path security -------------------------------------------------------

  it("returns 400 when path contains '..'", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/../etc/passwd");
    const res = await GET(req, makeParams("admin/../etc/passwd"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/traversal/i);
  });

  it("returns 400 when path has empty segments", async () => {
    mockValidAdmin();
    // Empty segment between admin and users
    const req = makeRequest("GET", "admin//users");
    const res = await GET(
      req,
      { params: Promise.resolve({ path: ["admin", "", "users"] }) }
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/empty/i);
  });

  it("returns 400 for non-admin scope path", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "api/users");
    const res = await GET(req, makeParams("api/users"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/scope/i);
  });

  it("returns 400 for SSRF characters: @ in path", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/us@ers");
    const res = await GET(req, makeParams("admin/us@ers"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/forbidden/i);
  });

  it("returns 400 for SSRF characters: # in path", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/us#ers");
    const res = await GET(req, makeParams("admin/us#ers"));
    expect(res.status).toBe(400);
  });

  it("returns 400 for SSRF characters: backslash in path", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/us\\ers");
    const res = await GET(req, makeParams("admin/us\\ers"));
    expect(res.status).toBe(400);
  });

  // -- Body limits ---------------------------------------------------------

  it("returns 413 when body exceeds 1MB", async () => {
    mockValidAdmin();
    const largeBody = "x".repeat(1024 * 1024 + 1);
    const req = makeRequest("POST", "admin/nodes", {
      body: largeBody,
      contentType: "application/json",
    });
    const res = await POST(req, makeParams("admin/nodes"));
    expect(res.status).toBe(413);
  });

  it("returns 415 for POST without application/json Content-Type", async () => {
    mockValidAdmin();
    const req = makeRequest("POST", "admin/nodes", {
      body: "<xml>bad</xml>",
      contentType: "text/xml",
    });
    const res = await POST(req, makeParams("admin/nodes"));
    expect(res.status).toBe(415);
    const body = await res.json();
    expect(body.error).toMatch(/content-type/i);
  });

  // -- Method allowlist ----------------------------------------------------

  it("returns 405 for OPTIONS method", async () => {
    mockValidAdmin();
    // OPTIONS is not in the exported handlers, but we can call GET with a
    // request whose method is OPTIONS. The handler checks request.method.
    const req = new NextRequest("http://localhost:3000/api/admin/admin/users", {
      method: "OPTIONS",
    });
    // We need to call one of the exported handlers; GET will do since the
    // handler reads request.method directly.
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(405);
  });

  // -- Header stripping ----------------------------------------------------

  it("does NOT forward Cookie or Authorization headers in outbound fetch", async () => {
    mockValidAdmin();
    const req = new NextRequest(
      "http://localhost:3000/api/admin/admin/users",
      {
        method: "GET",
        headers: {
          Cookie: "session=secret",
          Authorization: "Bearer token123",
        },
      }
    );
    await GET(req, makeParams("admin/users"));
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0];
    const outboundHeaders = fetchCall[1]?.headers as Record<string, string>;
    expect(outboundHeaders).not.toHaveProperty("Cookie");
    expect(outboundHeaders).not.toHaveProperty("cookie");
    expect(outboundHeaders).not.toHaveProperty("Authorization");
    expect(outboundHeaders).not.toHaveProperty("authorization");
  });

  it("strips Set-Cookie header from upstream response", async () => {
    mockValidAdmin();
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: {
          "content-type": "application/json",
          "Set-Cookie": "session=hijacked; Path=/",
        },
      })
    );
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  // -- Upstream errors -----------------------------------------------------

  it("returns 502 when fetch throws (upstream unreachable)", async () => {
    mockValidAdmin();
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toMatch(/unavailable/i);
  });

  // -- Body forwarding -----------------------------------------------------

  it("forwards POST body to upstream", async () => {
    mockValidAdmin();
    const jsonBody = '{"target_stage":"production"}';
    const req = makeRequest("POST", "admin/models/promote", {
      body: jsonBody,
      contentType: "application/json",
    });
    await POST(req, makeParams("admin/models/promote"));
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(fetchCall[1]?.body).toBe(jsonBody);
  });

  // -- Query params --------------------------------------------------------

  it("forwards query params to upstream URL", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/users", { query: "page=1&limit=10" });
    await GET(req, makeParams("admin/users"));
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0];
    const targetUrl = fetchCall[0] as string;
    expect(targetUrl).toContain("page=1");
    expect(targetUrl).toContain("limit=10");
  });

  // -- HMAC headers --------------------------------------------------------

  it("calls signAdminRequest and attaches HMAC headers to outbound request", async () => {
    mockValidAdmin();
    const req = makeRequest("GET", "admin/users");
    await GET(req, makeParams("admin/users"));
    expect(signAdminRequest).toHaveBeenCalledOnce();
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0];
    const outboundHeaders = fetchCall[1]?.headers as Record<string, string>;
    expect(outboundHeaders["X-Admin-Signature"]).toBe("mock-sig");
    expect(outboundHeaders["X-Admin-Timestamp"]).toBe("1700000000");
  });

  // -- INTERNAL_API_URL ----------------------------------------------------

  it("returns 500 when INTERNAL_API_URL is missing", async () => {
    mockValidAdmin();
    vi.stubEnv("INTERNAL_API_URL", "");
    const req = makeRequest("GET", "admin/users");
    const res = await GET(req, makeParams("admin/users"));
    expect(res.status).toBe(500);
  });
});
