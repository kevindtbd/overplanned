/**
 * GET /api/backfill/trips/[id]/status
 *
 * Lightweight poll endpoint for the client to check processing status.
 * Does NOT return venue details or PII — only counts and the status string.
 *
 * Intended for polling from the submission confirmation screen until
 * status transitions from "processing" to "complete" or "rejected".
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { BackfillAuthError, verifyBackfillTripOwnership } from "@/lib/backfill-auth";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  try {
    await verifyBackfillTripOwnership(tripId, userId);

    const trip = await prisma.backfillTrip.findUnique({
      where: { id: tripId },
      select: {
        status: true,
        _count: {
          select: { venues: true },
        },
        venues: {
          where: { isResolved: true },
          select: { id: true },
        },
      },
    });

    if (!trip) {
      return NextResponse.json({ error: "Backfill trip not found" }, { status: 404 });
    }

    return NextResponse.json(
      {
        status: trip.status,
        venueCount: trip._count.venues,
        resolvedCount: trip.venues.length,
      },
      { status: 200 }
    );
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[GET /api/backfill/trips/${tripId}/status] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
