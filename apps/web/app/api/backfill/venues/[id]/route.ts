/**
 * PATCH /api/backfill/venues/[id]
 *
 * Updates user-editable fields on a BackfillVenue.
 * Currently supports: wouldReturn (boolean)
 *
 * Constraints:
 *   - Only resolved venues can be updated (isResolved === true).
 *     Unresolved venues haven't been matched to ActivityNodes yet, so
 *     a wouldReturn signal would have no ML target to attach to.
 *   - Ownership chain: venue.backfillTrip.userId === session.user.id
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { backfillVenuePatchSchema } from "@/lib/validations/backfill";
import { BackfillAuthError, verifyBackfillVenueOwnership } from "@/lib/backfill-auth";

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: venueId } = params;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = backfillVenuePatchSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    const venue = await verifyBackfillVenueOwnership(venueId, userId);

    if (!venue.isResolved) {
      return NextResponse.json(
        {
          error: "Cannot update an unresolved venue",
          detail:
            "wouldReturn is only valid after the venue has been matched to a known place",
        },
        { status: 409 }
      );
    }

    const updated = await prisma.backfillVenue.update({
      where: { id: venueId },
      data: { wouldReturn: parsed.data.wouldReturn },
      select: {
        id: true,
        wouldReturn: true,
        updatedAt: true,
      },
    });

    return NextResponse.json({ venue: updated }, { status: 200 });
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[PATCH /api/backfill/venues/${venueId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
