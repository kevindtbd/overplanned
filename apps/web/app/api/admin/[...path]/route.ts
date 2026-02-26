/**
 * Admin proxy catch-all route.
 *
 * Browser -> Next.js /api/admin/[...path] -> HMAC-signed -> FastAPI /admin/*
 *
 * Security layers:
 *   1. JWT session check (getServerSession)
 *   2. DB re-verify systemRole=admin (prevents stale JWT escalation)
 *   3. Rate limiting (userId key, 60 reads/min, 10 mutations/min)
 *   4. Path security (traversal, scope, SSRF guards)
 *   5. Body size limit (1MB)
 *   6. Content-Type validation for mutations
 *   7. HMAC signing (proxy -> FastAPI)
 *   8. Header stripping (Cookie, Authorization out; Set-Cookie back)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { signAdminRequest } from "@/lib/admin/sign-request";
import { checkRateLimit } from "@/lib/admin/rate-limit";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_BODY_SIZE = 1024 * 1024; // 1MB
const ALLOWED_METHODS = new Set(["GET", "POST", "PATCH", "DELETE"]);
const FORBIDDEN_PATH_CHARS = /[@#\\]/;

function getInternalApiUrl(): string {
  const url = process.env.INTERNAL_API_URL;
  if (!url) {
    throw new Error("INTERNAL_API_URL is not configured");
  }
  return url;
}

// ---------------------------------------------------------------------------
// Path security
// ---------------------------------------------------------------------------

function validatePath(segments: string[]): string {
  // Reject empty segments (double slashes or leading/trailing)
  if (segments.some((s) => s === "")) {
    throw new ProxyError(400, "Invalid path: empty segments");
  }

  // Reject path traversal
  if (segments.some((s) => s === "..")) {
    throw new ProxyError(400, "Invalid path: traversal not allowed");
  }

  const path = "/admin/" + segments.join("/");

  // Scope enforcement: must start with /admin/
  if (!path.startsWith("/admin/") && path !== "/admin") {
    throw new ProxyError(400, "Invalid path: outside admin scope");
  }

  // SSRF character guard
  if (FORBIDDEN_PATH_CHARS.test(path)) {
    throw new ProxyError(400, "Invalid path: forbidden characters");
  }

  return path;
}

// ---------------------------------------------------------------------------
// Error helper
// ---------------------------------------------------------------------------

class ProxyError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Shared handler
// ---------------------------------------------------------------------------

async function handleAdminProxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  try {
    // 0. Method allowlist
    if (!ALLOWED_METHODS.has(request.method)) {
      return NextResponse.json(
        { error: "Method not allowed" },
        { status: 405 }
      );
    }

    // 1. Session check
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 }
      );
    }

    const userId = session.user.id;

    // 2. DB re-verify systemRole (prevents stale JWT privilege escalation)
    const dbUser = await prisma.user.findUnique({
      where: { id: userId },
      select: { systemRole: true },
    });

    if (!dbUser || dbUser.systemRole !== "admin") {
      return NextResponse.json(
        { error: "Admin access required" },
        { status: 403 }
      );
    }

    // 3. Rate limit check
    const rateResult = checkRateLimit(userId, request.method);
    if (!rateResult.allowed) {
      return NextResponse.json(
        { error: "Rate limit exceeded" },
        {
          status: 429,
          headers: {
            "Retry-After": String(rateResult.retryAfter ?? 60),
          },
        }
      );
    }

    // 4. Path security
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path;
    const safePath = validatePath(pathSegments);

    // 5. Body handling
    let bodyStr = "";
    if (request.method !== "GET") {
      const contentType = request.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) {
        return NextResponse.json(
          { error: "Content-Type must be application/json" },
          { status: 415 }
        );
      }

      const rawBody = await request.arrayBuffer();
      if (rawBody.byteLength > MAX_BODY_SIZE) {
        return NextResponse.json(
          { error: "Request body too large" },
          { status: 413 }
        );
      }
      bodyStr = new TextDecoder().decode(rawBody);
    }

    // 6. Sign request
    const queryString = request.nextUrl.searchParams.toString();
    const signedHeaders = signAdminRequest(
      request.method,
      safePath,
      queryString,
      userId,
      bodyStr
    );

    // 7. Forward to FastAPI
    const internalUrl = getInternalApiUrl();
    const targetUrl = new URL(safePath, internalUrl);
    // Forward query params
    request.nextUrl.searchParams.forEach((value, key) => {
      targetUrl.searchParams.set(key, value);
    });

    // Validate target URL hostname matches expected (SSRF guard)
    const expectedHost = new URL(internalUrl).hostname;
    if (targetUrl.hostname !== expectedHost) {
      return NextResponse.json(
        { error: "Invalid target URL" },
        { status: 400 }
      );
    }

    const outboundHeaders: Record<string, string> = {
      ...signedHeaders,
      "Content-Type": "application/json",
      "X-Admin-Client-IP":
        request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
        request.headers.get("x-real-ip") ??
        "unknown",
      "User-Agent": request.headers.get("user-agent") ?? "admin-proxy",
    };
    // Explicitly DO NOT forward Cookie or Authorization headers

    const fetchOptions: RequestInit = {
      method: request.method,
      headers: outboundHeaders,
    };
    if (request.method !== "GET" && bodyStr) {
      fetchOptions.body = bodyStr;
    }

    let upstreamResponse: Response;
    try {
      upstreamResponse = await fetch(targetUrl.toString(), fetchOptions);
    } catch {
      return NextResponse.json(
        { error: "Upstream service unavailable" },
        { status: 502 }
      );
    }

    // 8. Return response (strip Set-Cookie from upstream)
    const responseBody = await upstreamResponse.text();
    const responseHeaders = new Headers();
    upstreamResponse.headers.forEach((value, key) => {
      const lowerKey = key.toLowerCase();
      if (lowerKey !== "set-cookie") {
        responseHeaders.set(key, value);
      }
    });

    return new NextResponse(responseBody, {
      status: upstreamResponse.status,
      headers: responseHeaders,
    });
  } catch (err) {
    if (err instanceof ProxyError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    // Unexpected error -- don't leak details
    console.error("[admin-proxy] Unexpected error:", err);
    return NextResponse.json(
      { error: "Internal proxy error" },
      { status: 500 }
    );
  }
}

// ---------------------------------------------------------------------------
// Export handlers
// ---------------------------------------------------------------------------

export const GET = handleAdminProxy;
export const POST = handleAdminProxy;
export const PATCH = handleAdminProxy;
export const DELETE = handleAdminProxy;
