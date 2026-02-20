/**
 * POST /api/trips/[id]/join?token=xxx
 *
 * Next.js API route that proxies the join request to FastAPI,
 * injecting X-User-Id from the authenticated session.
 * This keeps the user ID out of the browser entirely.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth/config";

const API_BASE =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);

  if (!session?.user?.id) {
    return NextResponse.json(
      { success: false, error: { code: "UNAUTHORIZED", message: "Sign in required." } },
      { status: 401 }
    );
  }

  const token = request.nextUrl.searchParams.get("token");
  if (!token) {
    return NextResponse.json(
      { success: false, error: { code: "VALIDATION_ERROR", message: "token query param is required." } },
      { status: 422 }
    );
  }

  // Strip non-base64url chars to prevent header injection
  const safeToken = token.replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 64);
  const safeTripId = params.id.replace(/[^A-Za-z0-9\-]/g, "").slice(0, 36);

  const upstreamUrl = new URL(
    `/trips/${encodeURIComponent(safeTripId)}/join`,
    API_BASE
  );
  upstreamUrl.searchParams.set("token", safeToken);

  try {
    const res = await fetch(upstreamUrl.toString(), {
      method: "POST",
      headers: {
        "X-User-Id": session.user.id,
        "Content-Type": "application/json",
      },
    });

    const body = await res.json();
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        success: false,
        error: { code: "UPSTREAM_ERROR", message: "Unable to reach API." },
      },
      { status: 502 }
    );
  }
}
