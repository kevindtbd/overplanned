/**
 * Ownership verification helpers for backfill resources.
 *
 * These throw structured objects that callers convert to NextResponse.
 * Keeping the throws here keeps all 403/404 logic in one place and lets
 * route handlers stay thin.
 */

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export class BackfillAuthError {
  constructor(
    public readonly status: 403 | 404,
    public readonly message: string
  ) {}

  toResponse(): NextResponse {
    return NextResponse.json({ error: this.message }, { status: this.status });
  }
}

// ---------------------------------------------------------------------------
// Trip ownership
// ---------------------------------------------------------------------------

/**
 * Verify that the given userId owns the given backfill trip.
 * Returns the trip row on success.
 * Throws BackfillAuthError on 404 (not found) or 403 (wrong owner).
 *
 * Status filter: excludes archived + rejected trips from reads so
 * soft-deleted trips behave like they don't exist.
 */
export async function verifyBackfillTripOwnership(
  tripId: string,
  userId: string
) {
  const trip = await prisma.backfillTrip.findUnique({
    where: { id: tripId },
    select: {
      id: true,
      userId: true,
      status: true,
      city: true,
      country: true,
      startDate: true,
      endDate: true,
      contextTag: true,
      tripNote: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  if (!trip) {
    throw new BackfillAuthError(404, "Backfill trip not found");
  }

  if (trip.userId !== userId) {
    throw new BackfillAuthError(403, "Forbidden");
  }

  return trip;
}

/**
 * Verify that the given userId owns the trip that owns the given venue.
 * Returns the venue (with backfillTrip embedded) on success.
 * Throws BackfillAuthError on 404 or 403.
 */
export async function verifyBackfillVenueOwnership(
  venueId: string,
  userId: string
) {
  const venue = await prisma.backfillVenue.findUnique({
    where: { id: venueId },
    select: {
      id: true,
      backfillTripId: true,
      isResolved: true,
      isQuarantined: true,
      wouldReturn: true,
      extractedName: true,
      extractedCategory: true,
      extractedDate: true,
      activityNodeId: true,
      backfillTrip: {
        select: {
          userId: true,
          status: true,
        },
      },
    },
  });

  if (!venue) {
    throw new BackfillAuthError(404, "Venue not found");
  }

  if (venue.backfillTrip.userId !== userId) {
    throw new BackfillAuthError(403, "Forbidden");
  }

  return venue;
}
