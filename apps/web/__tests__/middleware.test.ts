/**
 * Tests for apps/web/middleware.ts
 *
 * Covers:
 *  - Public path pass-through (no session required)
 *  - /s/, /invite/, /api/auth/ prefix pass-through
 *  - Redirect to /auth/signin with callbackUrl for protected paths
 *  - Session cookie acceptance (both HTTP and HTTPS variants)
 *  - /dev/* 404 in production
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { middleware } from "@/middleware";

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

// ---------------------------------------------------------------------------
// Public paths — no session required
// ---------------------------------------------------------------------------

describe("middleware — public paths", () => {
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
});

// ---------------------------------------------------------------------------
// Prefix-matched public paths
// ---------------------------------------------------------------------------

describe("middleware — prefix-matched public paths", () => {
  it("allows /s/<token> (shared trip) without a session cookie", () => {
    const res = middleware(createRequest("/s/abc123")) as NextResponse;
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
    const location = res.headers.get("location");
    expect(location).toBeTruthy();
    expect(new URL(location!, "http://localhost:3000").pathname).toBe("/auth/signin");
  });

  it("preserves callbackUrl in redirect query param", () => {
    const res = middleware(createRequest("/trips/abc/itinerary")) as NextResponse;
    const location = res.headers.get("location");
    expect(location).toBeTruthy();
    const locationUrl = new URL(location!, "http://localhost:3000");
    expect(locationUrl.searchParams.get("callbackUrl")).toBe("/trips/abc/itinerary");
  });
});

// ---------------------------------------------------------------------------
// Session cookie acceptance
// ---------------------------------------------------------------------------

describe("middleware — session cookie", () => {
  it("allows a protected path with next-auth.session-token cookie", () => {
    const res = middleware(
      createRequest("/trips/abc", { "next-auth.session-token": "tok_abc" })
    ) as NextResponse;
    expect(res.status).toBe(200);
  });

  it("allows a protected path with __Secure-next-auth.session-token cookie", () => {
    const res = middleware(
      createRequest("/trips/abc", {
        "__Secure-next-auth.session-token": "tok_secure",
      })
    ) as NextResponse;
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

  it("returns 404 with no body for /dev/* (no information leakage)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = middleware(createRequest("/dev/tokens")) as NextResponse;
    expect(res.status).toBe(404);
    const text = await res.text();
    expect(text).toBe("");
  });
});
