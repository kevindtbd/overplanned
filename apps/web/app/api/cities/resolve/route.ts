/**
 * POST /api/cities/resolve
 *
 * Resolves a freeform city name to structured city data (city, country, timezone, destination).
 * Checks LAUNCH_CITIES first, then falls back to LLM resolution via claude-haiku.
 *
 * Auth: session required
 * Rate limit: 20 requests per user per hour (in-memory)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { cityResolveSchema } from "@/lib/validations/trip";
import { resolveCity, checkRateLimit } from "@/lib/city-resolver";

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = cityResolveSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const allowed = checkRateLimit(userId);
  if (!allowed) {
    return NextResponse.json(
      { error: "Rate limit exceeded. Try again later." },
      { status: 429 }
    );
  }

  try {
    const result = await resolveCity(parsed.data.city);
    return NextResponse.json(result, { status: 200 });
  } catch (err) {
    console.error("[POST /api/cities/resolve] Error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
