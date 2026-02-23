/**
 * GET /api/backfill/trips
 *
 * Returns the authed user's backfill trips, excluding archived and rejected
 * entries (soft-deleted or admin-rejected).
 *
 * Response shape per trip:
 *   id, city, country, startDate, endDate, contextTag, status,
 *   createdAt, updatedAt, resolvedVenueCount, totalVenueCount
 *
 * Intentionally omitted: confidenceTier, rawSubmission, rejectionReason
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

export async function GET(_req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  try {
    const trips = await prisma.backfillTrip.findMany({
      where: {
        userId,
        status: {
          notIn: ["archived", "rejected"],
        },
      },
      select: {
        id: true,
        city: true,
        country: true,
        startDate: true,
        endDate: true,
        contextTag: true,
        status: true,
        createdAt: true,
        updatedAt: true,
        _count: {
          select: {
            venues: true,
          },
        },
        venues: {
          where: { isResolved: true },
          select: { id: true },
        },
      },
      orderBy: { createdAt: "desc" },
    });

    const result = trips.map((trip) => ({
      id: trip.id,
      city: trip.city,
      country: trip.country,
      startDate: trip.startDate,
      endDate: trip.endDate,
      contextTag: trip.contextTag,
      status: trip.status,
      createdAt: trip.createdAt,
      updatedAt: trip.updatedAt,
      resolvedVenueCount: trip.venues.length,
      totalVenueCount: trip._count.venues,
    }));

    return NextResponse.json({ trips: result }, { status: 200 });
  } catch (err) {
    console.error("[GET /api/backfill/trips] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
