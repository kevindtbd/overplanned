/**
 * POST /api/backfill/submit
 *
 * Accepts a freeform travel diary text from the authed user and proxies it
 * to the FastAPI ML service for entity extraction and enrichment.
 *
 * The FastAPI service is responsible for:
 *   - Parsing venue names, dates, and sentiment from the text
 *   - Creating the BackfillTrip + BackfillVenue rows
 *   - Queuing the resolution job against ActivityNode
 *
 * This route is a thin auth + validation proxy — it does not write to the
 * DB directly. All persistence happens in FastAPI.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { backfillSubmitSchema } from "@/lib/validations/backfill";

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

  const parsed = backfillSubmitSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const apiUrl = process.env.API_URL;
  if (!apiUrl) {
    console.error("[POST /api/backfill/submit] API_URL env var not set");
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  const serviceToken = process.env.SERVICE_TOKEN;
  if (!serviceToken) {
    console.error("[POST /api/backfill/submit] SERVICE_TOKEN env var not set");
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  try {
    const upstream = await fetch(`${apiUrl}/backfill/submit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Service-Token": serviceToken,
        "X-User-Id": userId,
      },
      body: JSON.stringify(parsed.data),
    });

    // Surface upstream errors verbatim so the client can react to 422 etc.
    if (!upstream.ok) {
      const errBody = await upstream.json().catch(() => ({ error: "Upstream error" }));
      console.error(`[POST /api/backfill/submit] Upstream ${upstream.status}:`, errBody);
      return NextResponse.json(errBody, { status: upstream.status });
    }

    const data = await upstream.json();
    // Expected shape: { backfill_trip_id: string, status: string }
    return NextResponse.json(data, { status: 202 });
  } catch (err) {
    console.error("[POST /api/backfill/submit] Fetch error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
