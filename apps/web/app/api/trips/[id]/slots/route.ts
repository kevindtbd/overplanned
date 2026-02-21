/**
 * POST /api/trips/[id]/slots
 *
 * Adds an ActivityNode to a trip as a flex slot on day 1.
 *
 * Auth: requires an active session.
 * IDOR: caller must be a TripMember with status "joined".
 * Validates: activityNodeId is a UUID, node exists, not archived,
 *            and node.city matches trip.city.
 * Atomic: slot creation + behavioral signal written in one $transaction.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";

const addSlotSchema = z.object({
  activityNodeId: z.string().uuid(),
});

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  // -------------------------------------------------------------------------
  // 1. Auth check
  // -------------------------------------------------------------------------
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  // -------------------------------------------------------------------------
  // 2. IDOR prevention — caller must be a joined TripMember
  // -------------------------------------------------------------------------
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { status: true },
  });

  if (!membership || membership.status !== "joined") {
    // Return 404 regardless of whether the trip exists to avoid ID enumeration
    return NextResponse.json({ error: "Trip not found" }, { status: 404 });
  }

  // -------------------------------------------------------------------------
  // 3. Parse + validate request body
  // -------------------------------------------------------------------------
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = addSlotSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "Validation failed",
        details: parsed.error.flatten().fieldErrors,
      },
      { status: 400 }
    );
  }

  const { activityNodeId } = parsed.data;

  try {
    // -------------------------------------------------------------------------
    // 4. Validate ActivityNode: must exist, not archived, city must match trip
    // -------------------------------------------------------------------------
    const [activityNode, trip] = await Promise.all([
      prisma.activityNode.findUnique({
        where: { id: activityNodeId },
        select: { id: true, status: true, city: true },
      }),
      prisma.trip.findUnique({
        where: { id: tripId },
        select: { city: true },
      }),
    ]);

    if (!activityNode) {
      return NextResponse.json(
        { error: "Activity not found" },
        { status: 404 }
      );
    }

    if (activityNode.status === "archived") {
      return NextResponse.json(
        { error: "Activity is no longer available" },
        { status: 422 }
      );
    }

    if (!trip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (activityNode.city.toLowerCase() !== trip.city.toLowerCase()) {
      return NextResponse.json(
        { error: "Activity city does not match trip destination" },
        { status: 422 }
      );
    }

    // -------------------------------------------------------------------------
    // 5. Atomic transaction: compute sortOrder, create slot + behavioral signal
    // -------------------------------------------------------------------------
    const slotId = uuidv4();
    const signalId = uuidv4();

    const [slot] = await prisma.$transaction(async (tx) => {
      // Max sortOrder for existing day-1 slots in this trip
      const agg = await tx.itinerarySlot.aggregate({
        where: { tripId, dayNumber: 1 },
        _max: { sortOrder: true },
      });

      const nextSortOrder = (agg._max.sortOrder ?? 0) + 1;

      const createdSlot = await tx.itinerarySlot.create({
        data: {
          id: slotId,
          tripId,
          activityNodeId,
          dayNumber: 1,
          sortOrder: nextSortOrder,
          slotType: "flex",
          status: "proposed",
          isLocked: false,
          isContested: false,
          wasSwapped: false,
        },
        select: {
          id: true,
          tripId: true,
          activityNodeId: true,
          dayNumber: true,
          sortOrder: true,
          slotType: true,
          status: true,
          isLocked: true,
          createdAt: true,
          activityNode: {
            select: {
              id: true,
              name: true,
              category: true,
              city: true,
              primaryImageUrl: true,
              priceLevel: true,
            },
          },
        },
      });

      await tx.behavioralSignal.create({
        data: {
          id: signalId,
          userId,
          tripId,
          slotId,
          activityNodeId,
          signalType: "discover_shortlist",
          signalValue: 1.0,
          tripPhase: "pre_trip",
          rawAction: "add_to_trip_from_shortlist",
        },
      });

      return [createdSlot];
    });

    return NextResponse.json({ slot }, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/slots] DB error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
