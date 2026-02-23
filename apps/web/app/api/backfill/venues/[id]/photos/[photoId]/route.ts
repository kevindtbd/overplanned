/**
 * DELETE /api/backfill/venues/[id]/photos/[photoId]
 *
 * Deletes a photo from both GCS and the database.
 * Ownership chain: photo.venue.backfillTrip.userId === session.user.id
 *
 * GCS deletion is attempted first. If GCS succeeds (or 404s), the DB row
 * is deleted. If GCS throws an unexpected error, the DB row is NOT deleted
 * to avoid orphaned DB entries pointing at missing objects.
 *
 * Returns 204 on success.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { BackfillAuthError } from "@/lib/backfill-auth";
import { deleteFromGCS } from "@/lib/gcs";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string; photoId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: venueId, photoId } = params;

  try {
    // Fetch photo with full ownership chain in a single query
    const photo = await prisma.backfillPhoto.findUnique({
      where: { id: photoId },
      select: {
        id: true,
        gcsPath: true,
        backfillVenueId: true,
        backfillVenue: {
          select: {
            id: true,
            backfillTripId: true,
            backfillTrip: {
              select: {
                userId: true,
              },
            },
          },
        },
      },
    });

    if (!photo) {
      return NextResponse.json({ error: "Photo not found" }, { status: 404 });
    }

    // Verify the photo belongs to the requested venue
    if (photo.backfillVenueId !== venueId) {
      return NextResponse.json({ error: "Photo not found" }, { status: 404 });
    }

    // Ownership chain verification
    if (photo.backfillVenue.backfillTrip.userId !== userId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    // Delete from GCS first. deleteFromGCS silently handles 404s.
    await deleteFromGCS(photo.gcsPath);

    // Delete DB row only after GCS confirms deletion (or object was already gone)
    await prisma.backfillPhoto.delete({ where: { id: photoId } });

    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[DELETE /api/backfill/venues/${venueId}/photos/${photoId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
