/**
 * GET    /api/backfill/trips/[id]  — Trip detail + venues + photos with signed URLs
 * PATCH  /api/backfill/trips/[id]  — Update contextTag / tripNote
 * DELETE /api/backfill/trips/[id]  — Soft-delete (status -> archived)
 *
 * Ownership: trip.userId must equal session.user.id on every verb.
 *
 * Security omissions (never returned):
 *   - confidenceTier
 *   - resolutionScore
 *   - quarantineReason (quarantined venues return { flagged: true } instead)
 *   - rawSubmission
 *   - rejectionReason
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { backfillTripPatchSchema } from "@/lib/validations/backfill";
import { BackfillAuthError, verifyBackfillTripOwnership } from "@/lib/backfill-auth";
import { getSignedUrl } from "@/lib/gcs";

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
    // Ownership check — throws BackfillAuthError on failure
    await verifyBackfillTripOwnership(tripId, userId);

    const trip = await prisma.backfillTrip.findUnique({
      where: { id: tripId },
      select: {
        id: true,
        legs: {
          select: { id: true, city: true, country: true, timezone: true, position: true },
          orderBy: { position: "asc" },
        },
        startDate: true,
        endDate: true,
        contextTag: true,
        tripNote: true,
        status: true,
        source: true,
        createdAt: true,
        updatedAt: true,
        venues: {
          select: {
            id: true,
            extractedName: true,
            extractedCategory: true,
            extractedDate: true,
            isResolved: true,
            isQuarantined: true,
            wouldReturn: true,
            activityNode: {
              select: {
                name: true,
                neighborhood: true,
                priceLevel: true,
                category: true,
              },
            },
            photos: {
              select: {
                id: true,
                gcsPath: true,
                exifLat: true,
                exifLng: true,
                exifTimestamp: true,
              },
              orderBy: { createdAt: "asc" },
            },
          },
          orderBy: { createdAt: "asc" },
        },
      },
    });

    if (!trip) {
      return NextResponse.json({ error: "Backfill trip not found" }, { status: 404 });
    }

    // Generate signed URLs for all photos; build safe venue shape
    const tripVenues = trip.venues;
    const venues = await Promise.all(
      tripVenues.map(async (venue) => {
        if (venue.isQuarantined) {
          // Return minimal shape for quarantined venues — no reason exposed
          return {
            id: venue.id,
            flagged: true,
          };
        }

        const venuePhotos = venue.photos;
        const photos = await Promise.all(
          venuePhotos.map(async (photo) => {
            let signedUrl: string | null = null;
            try {
              signedUrl = await getSignedUrl(photo.gcsPath);
            } catch (err) {
              console.error(
                `[GET /api/backfill/trips/${tripId}] Failed to sign URL for photo ${photo.id}:`,
                err
              );
            }
            return {
              id: photo.id,
              signedUrl,
              exifLat: photo.exifLat,
              exifLng: photo.exifLng,
              exifTimestamp: photo.exifTimestamp,
            };
          })
        );

        return {
          id: venue.id,
          extractedName: venue.extractedName,
          extractedCategory: venue.extractedCategory,
          extractedDate: venue.extractedDate,
          isResolved: venue.isResolved,
          wouldReturn: venue.wouldReturn,
          activityNode: venue.isResolved ? venue.activityNode : null,
          photos,
        };
      })
    );

    return NextResponse.json(
      {
        trip: {
          id: trip.id,
          legs: trip.legs,
          city: trip.legs[0]?.city ?? null,
          country: trip.legs[0]?.country ?? null,
          startDate: trip.startDate,
          endDate: trip.endDate,
          contextTag: trip.contextTag,
          tripNote: trip.tripNote,
          status: trip.status,
          source: trip.source,
          createdAt: trip.createdAt,
          updatedAt: trip.updatedAt,
        },
        venues,
      },
      { status: 200 }
    );
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[GET /api/backfill/trips/${tripId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = backfillTripPatchSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    await verifyBackfillTripOwnership(tripId, userId);

    const updated = await prisma.backfillTrip.update({
      where: { id: tripId },
      data: {
        ...(parsed.data.contextTag !== undefined && { contextTag: parsed.data.contextTag }),
        ...(parsed.data.tripNote !== undefined && { tripNote: parsed.data.tripNote }),
      },
      select: {
        id: true,
        contextTag: true,
        tripNote: true,
        updatedAt: true,
      },
    });

    return NextResponse.json({ trip: updated }, { status: 200 });
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[PATCH /api/backfill/trips/${tripId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function DELETE(
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

    await prisma.backfillTrip.update({
      where: { id: tripId },
      data: { status: "archived" },
    });

    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[DELETE /api/backfill/trips/${tripId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
