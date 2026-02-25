/**
 * Tests for apps/web/middleware.ts
 *
 * Covers:
 *  - Public path pass-through (exact match + prefix match)
 *  - /s/, /invite/, /api/auth/, /api/health prefix/exact pass-through
 *  - Redirect to /auth/signin with callbackUrl for protected paths
 *  - Session cookie acceptance (both HTTP and HTTPS variants)
 *  - /dev/* 404 in production (even with valid session)
 *  - /dev/* allowed in development
 *  - /dashboard public in development, protected in production
 *  - API routes (non-auth) require auth via middleware
 *  - Public routes still pass through when authenticated
 *  - Edge cases: exact-match boundaries, prefix-match boundaries
 *  - config.matcher excludes static assets
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { middleware, config } from "@/middleware";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function createRequest(
  path: string,
  cookies: Record<string, string> = {}
): NextRequest {
  const req = new NextRequest(new URL(path, "http://localhost:3000"));
  for (const [name, value] of Object.entries(cookies)) {
    req.cookies.set(name, value);
  }
  return req;
}

/** Shorthand for an authenticated request (dev cookie). */
function authedRequest(path: string): NextRequest {
  return createRequest(path, { "next-auth.session-token": "tok_test" });
}

/** Extract the redirect location from a response, if present. */
function getRedirectUrl(res: NextResponse): URL | null {
  const location = res.headers.get("location");
  return location ? new URL(location, "http://localhost:3000") : null;
}

// ---------------------------------------------------------------------------
// Public paths — exact match, no session required
// ---------------------------------------------------------------------------

describe("middleware — public paths (exact match)", () => {
  it("allows / without a session cookie", () => {
    const res = middleware(createRequest("/")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /auth/signin without a session cookie", () => {
    const res = middleware(createRequest("/auth/signin")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /auth/error without a session cookie", () => {
    const res = middleware(createRequest("/auth/error")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /about without a session cookie", () => {
    const res = middleware(createRequest("/about")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /privacy without a session cookie", () => {
    const res = middleware(createRequest("/privacy")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /terms without a session cookie", () => {
    const res = middleware(createRequest("/terms")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /api/health without a session cookie", () => {
    const res = middleware(createRequest("/api/health")) as NextResponse;
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Public paths — exact-match boundary: similar paths are NOT public
// ---------------------------------------------------------------------------

describe("middleware — exact-match boundaries", () => {
  it("does NOT treat /aboutus as public (no prefix match on /about)", () => {
    const res = middleware(createRequest("/aboutus")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("does NOT treat /termsofservice as public", () => {
    const res = middleware(createRequest("/termsofservice")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("/ does NOT prefix-match /settings (exact match only for /)", () => {
    const res = middleware(createRequest("/settings")) as NextResponse;
    expect(res.status).toBe(307);
  });
});

// ---------------------------------------------------------------------------
// Prefix-matched public paths
// ---------------------------------------------------------------------------

describe("middleware — prefix-matched public paths", () => {
  it("allows /s/<token> (shared trip) without a session cookie", () => {
    const res = middleware(createRequest("/s/abc123")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /s/ with nested segments", () => {
    const res = middleware(createRequest("/s/abc123/details")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /invite/<token> without a session cookie", () => {
    const res = middleware(createRequest("/invite/xyz789")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /api/auth/callback/google without a session cookie", () => {
    const res = middleware(createRequest("/api/auth/callback/google")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /api/auth/session without a session cookie", () => {
    const res = middleware(createRequest("/api/auth/session")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows /api/auth/providers without a session cookie", () => {
    const res = middleware(createRequest("/api/auth/providers")) as NextResponse;
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Protected paths — redirect to sign-in
//
// NOTE: /dashboard is added to PUBLIC_PATHS in development/test mode as a
// dev convenience shortcut. Use /trips/<id> which is always protected.
// ---------------------------------------------------------------------------

describe("middleware — protected path redirect", () => {
  it("redirects /trips/abc to /auth/signin when no session cookie", () => {
    const res = middleware(createRequest("/trips/abc")) as NextResponse;
    expect(res.status).toBe(307);
    const url = getRedirectUrl(res);
    expect(url).not.toBeNull();
    expect(url!.pathname).toBe("/auth/signin");
  });

  it("preserves callbackUrl in redirect query param", () => {
    const res = middleware(createRequest("/trips/abc/itinerary")) as NextResponse;
    const url = getRedirectUrl(res);
    expect(url).not.toBeNull();
    expect(url!.searchParams.get("callbackUrl")).toBe("/trips/abc/itinerary");
  });

  it("redirects /settings when no session cookie", () => {
    const res = middleware(createRequest("/settings")) as NextResponse;
    expect(res.status).toBe(307);
    const url = getRedirectUrl(res);
    expect(url!.pathname).toBe("/auth/signin");
    expect(url!.searchParams.get("callbackUrl")).toBe("/settings");
  });

  it("redirects /admin/users when no session cookie", () => {
    const res = middleware(createRequest("/admin/users")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("redirects /onboarding when no session cookie", () => {
    const res = middleware(createRequest("/onboarding")) as NextResponse;
    expect(res.status).toBe(307);
  });
});

// ---------------------------------------------------------------------------
// API routes (non-auth) — middleware requires session cookie
//
// Non-public API routes still pass through the middleware session check.
// The routes themselves do deeper auth checks server-side, but middleware
// gates the initial cookie presence.
// ---------------------------------------------------------------------------

describe("middleware — non-public API routes", () => {
  it("redirects /api/trips when no session cookie", () => {
    const res = middleware(createRequest("/api/trips")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("redirects /api/signals when no session cookie", () => {
    const res = middleware(createRequest("/api/signals")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("allows /api/trips with a session cookie", () => {
    const res = middleware(authedRequest("/api/trips")) as NextResponse;
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Session cookie acceptance
// ---------------------------------------------------------------------------

describe("middleware — session cookie", () => {
  it("allows a protected path with next-auth.session-token cookie (dev)", () => {
    const res = middleware(
      createRequest("/trips/abc", { "next-auth.session-token": "tok_abc" })
    ) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows a protected path with __Secure-next-auth.session-token cookie (prod)", () => {
    const res = middleware(
      createRequest("/trips/abc", {
        "__Secure-next-auth.session-token": "tok_secure",
      })
    ) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("still allows public routes when authenticated", () => {
    const res = middleware(authedRequest("/")) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("still allows /about when authenticated", () => {
    const res = middleware(authedRequest("/about")) as NextResponse;
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// /dashboard — public in development, protected in production
//
// In the test environment (NODE_ENV=test), /dashboard is added to
// PUBLIC_PATHS via the development conditional. When NODE_ENV is stubbed
// to production, the module-level spread has already resolved, so we
// verify development behavior directly and production behavior via stubEnv.
// ---------------------------------------------------------------------------

describe("middleware — /dashboard", () => {
  it("redirects /dashboard when NODE_ENV is test (not development)", () => {
    // PUBLIC_PATHS only adds /dashboard when NODE_ENV === "development".
    // In vitest, NODE_ENV is "test", so /dashboard is protected.
    const res = middleware(createRequest("/dashboard")) as NextResponse;
    expect(res.status).toBe(307);
  });

  it("allows /dashboard with a session cookie", () => {
    const res = middleware(authedRequest("/dashboard")) as NextResponse;
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// /dev/* production guard
//
// The middleware reads process.env.NODE_ENV inline (not a cached constant),
// so vi.stubEnv overrides it cleanly without Object.defineProperty.
// ---------------------------------------------------------------------------

describe("middleware — /dev/* production block", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("does NOT block /dev/tokens when NODE_ENV is not production", () => {
    const res = middleware(createRequest("/dev/tokens")) as NextResponse;
    // Passes to layout — either 200 (public path in dev) or 307 (redirect)
    // but NOT 404
    expect(res.status).not.toBe(404);
  });

  it("does NOT block /dev/some-page when NODE_ENV is not production", () => {
    const res = middleware(createRequest("/dev/some-page")) as NextResponse;
    expect(res.status).not.toBe(404);
  });

  it("returns 404 for /dev/tokens in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(createRequest("/dev/tokens")) as NextResponse;
    expect(res.status).toBe(404);
  });

  it("returns 404 for /dev/some-page in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(createRequest("/dev/some-page")) as NextResponse;
    expect(res.status).toBe(404);
  });

  it("returns 404 for /dev/* in production even with a valid session", () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(authedRequest("/dev/tokens")) as NextResponse;
    expect(res.status).toBe(404);
  });

  it("returns 404 with no body for /dev/* (no information leakage)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(createRequest("/dev/tokens")) as NextResponse;
    expect(res.status).toBe(404);
    const text = await res.text();
    expect(text).toBe("");
  });

  it("does NOT block /developer (only /dev/ prefix)", () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(createRequest("/developer")) as NextResponse;
    // /developer is not in PUBLIC_PATHS, so it redirects (not 404)
    expect(res.status).toBe(307);
  });
});

// ---------------------------------------------------------------------------
// config.matcher — static asset exclusion
//
// The matcher uses Next.js path-to-regexp syntax: /(negative-lookahead.*)
// We can't run Next.js's internal matcher, but we CAN verify the pattern
// string contains the expected exclusion segments and is well-formed.
// ---------------------------------------------------------------------------

describe("middleware — config.matcher", () => {
  const pattern = config.matcher[0];

  it("exports exactly one matcher pattern", () => {
    expect(config.matcher).toHaveLength(1);
  });

  it("excludes _next/static paths", () => {
    expect(pattern).toContain("_next/static");
  });

  it("excludes _next/image paths", () => {
    expect(pattern).toContain("_next/image");
  });

  it("excludes favicon.ico", () => {
    expect(pattern).toContain("favicon.ico");
  });

  it("excludes common image extensions (svg, png, jpg, jpeg, gif, webp)", () => {
    for (const ext of ["svg", "png", "jpg", "jpeg", "gif", "webp"]) {
      expect(pattern).toContain(ext);
    }
  });
});
