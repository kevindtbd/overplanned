/**
 * POST /api/backfill/submit
 *
 * Accepts a freeform travel diary text from the authed user.
 *
 * Production: proxies to FastAPI ML service for entity extraction + enrichment.
 * Local dev (no API_URL): writes directly to Prisma with status "processing".
 *   The ML pipeline can pick it up later via a backfill job.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { backfillSubmitSchema } from "@/lib/validations/backfill";
import { prisma } from "@/lib/prisma";
import * as crypto from "crypto";

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
  const serviceToken = process.env.SERVICE_TOKEN;

  // ── Production path: proxy to FastAPI ──
  if (apiUrl && serviceToken) {
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

      if (!upstream.ok) {
        const errBody = await upstream.json().catch(() => ({ error: "Upstream error" }));
        console.error(`[POST /api/backfill/submit] Upstream ${upstream.status}:`, errBody);
        return NextResponse.json(errBody, { status: upstream.status });
      }

      const data = await upstream.json();
      return NextResponse.json(data, { status: 202 });
    } catch (err) {
      console.error("[POST /api/backfill/submit] Fetch error:", err);
      return NextResponse.json({ error: "Internal server error" }, { status: 500 });
    }
  }

  // ── Local dev fallback: write directly to Prisma ──
  console.info("[POST /api/backfill/submit] No API_URL — using direct Prisma write (dev mode)");

  try {
    const { text, cityHint, dateRangeHint, contextTag } = parsed.data;

    // Idempotency: hash of userId + text
    const dedupHash = crypto
      .createHash("sha256")
      .update(`${userId}:${text}`)
      .digest("hex");

    // Check for duplicate submission
    const existing = await prisma.backfillTrip.findFirst({
      where: { userId, tripNote: dedupHash },
      select: { id: true, status: true },
    });

    if (existing) {
      return NextResponse.json(
        { backfill_trip_id: existing.id, status: existing.status },
        { status: 200 }
      );
    }

    const trip = await prisma.backfillTrip.create({
      data: {
        userId,
        rawSubmission: text,
        confidenceTier: "tier_4",
        source: "freeform",
        tripNote: dedupHash,
        contextTag: contextTag || null,
        status: "processing",
      },
      select: { id: true, status: true },
    });

    // Create initial leg from city hint
    if (cityHint?.trim()) {
      await prisma.backfillLeg.create({
        data: {
          backfillTripId: trip.id,
          position: 0,
          city: cityHint.trim(),
          country: "unknown",
        },
      });
    }

    return NextResponse.json(
      { backfill_trip_id: trip.id, status: trip.status },
      { status: 202 }
    );
  } catch (err) {
    console.error("[POST /api/backfill/submit] Prisma error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
