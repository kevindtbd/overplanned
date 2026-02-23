/**
 * PATCH  /api/trips/[id]/legs/[legId] — Edit leg city/dates (organizer only)
 * DELETE /api/trips/[id]/legs/[legId] — Remove a leg and its slots (organizer only)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { patchLegSchema } from "@/lib/validations/trip";

// ---------------------------------------------------------------------------
// Shared auth + status gate helper
// ---------------------------------------------------------------------------
async function resolveOrganizerAccess(
  tripId: string,
  userId: string
): Promise<
  | { ok: true }
  | { ok: false; response: NextResponse }
> {
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { role: true, status: true },
  });

  if (!membership || membership.status !== "joined") {
    return {
      ok: false,
      response: NextResponse.json({ error: "Trip not found" }, { status: 404 }),
    };
  }

  if (membership.role !== "organizer") {
    return {
      ok: false,
      response: NextResponse.json(
        { error: "Only the trip organizer can modify legs" },
        { status: 403 }
      ),
    };
  }

  const trip = await prisma.trip.findUnique({
    where: { id: tripId },
    select: { status: true },
  });

  if (!trip || !["draft", "planning"].includes(trip.status)) {
    return {
      ok: false,
      response: NextResponse.json(
        { error: "Legs can only be modified on draft or planning trips" },
        { status: 409 }
      ),
    };
  }

  return { ok: true };
}

// ---------------------------------------------------------------------------
// PATCH — Edit leg fields
// ---------------------------------------------------------------------------
export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; legId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId, legId } = params;

  // 1. Auth + status gate
  const access = await resolveOrganizerAccess(tripId, userId);
  if (!access.ok) return access.response;

  // 2. Parse body
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = patchLegSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // 3. Fetch the leg and IDOR guard
    const existing = await prisma.tripLeg.findUnique({
      where: { id: legId },
      select: { id: true, tripId: true },
    });

    if (!existing || existing.tripId !== tripId) {
      return NextResponse.json({ error: "Leg not found" }, { status: 404 });
    }

    // 4. Apply update
    const { city, country, timezone, destination, startDate, endDate } =
      parsed.data;

    const updated = await prisma.tripLeg.update({
      where: { id: legId },
      data: {
        ...(city !== undefined && { city }),
        ...(country !== undefined && { country }),
        ...(timezone !== undefined && { timezone: timezone ?? null }),
        ...(destination !== undefined && { destination }),
        ...(startDate !== undefined && { startDate: new Date(startDate) }),
        ...(endDate !== undefined && { endDate: new Date(endDate) }),
      },
    });

    return NextResponse.json({ leg: updated }, { status: 200 });
  } catch (err) {
    console.error(`[PATCH /api/trips/${tripId}/legs/${legId}] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

// ---------------------------------------------------------------------------
// DELETE — Remove a leg and cascade its slots; re-number remaining legs
// ---------------------------------------------------------------------------
export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string; legId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId, legId } = params;

  // 1. Auth + status gate
  const access = await resolveOrganizerAccess(tripId, userId);
  if (!access.ok) return access.response;

  try {
    // 2. Fetch the leg and IDOR guard
    const existing = await prisma.tripLeg.findUnique({
      where: { id: legId },
      select: { id: true, tripId: true },
    });

    if (!existing || existing.tripId !== tripId) {
      return NextResponse.json({ error: "Leg not found" }, { status: 404 });
    }

    // 3. Guard against deleting the last leg
    const legCount = await prisma.tripLeg.count({ where: { tripId } });
    if (legCount <= 1) {
      return NextResponse.json(
        { error: "Cannot delete the last leg" },
        { status: 409 }
      );
    }

    // 4. Count slots before deletion so we can report it
    const slotCount = await prisma.itinerarySlot.count({
      where: { tripLegId: legId },
    });

    // 5. Atomic transaction: delete slots -> delete leg -> re-number remaining
    await prisma.$transaction(async (tx) => {
      // 5a. Delete all slots belonging to this leg
      await tx.itinerarySlot.deleteMany({ where: { tripLegId: legId } });

      // 5b. Delete the leg itself
      await tx.tripLeg.delete({ where: { id: legId } });

      // 5c. Re-number surviving legs contiguously from 0
      const remaining = await tx.tripLeg.findMany({
        where: { tripId },
        orderBy: { position: "asc" },
        select: { id: true },
      });

      await Promise.all(
        remaining.map((leg, i) =>
          tx.tripLeg.update({ where: { id: leg.id }, data: { position: i } })
        )
      );
    });

    return NextResponse.json(
      { deleted: true, deletedSlotCount: slotCount },
      { status: 200 }
    );
  } catch (err) {
    console.error(`[DELETE /api/trips/${tripId}/legs/${legId}] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
