/**
 * POST /api/trips/[id]/slots
 *
 * Adds an ActivityNode to a trip as a flex slot on day 1.
 *
 * Auth: requires an active session.
 * IDOR: caller must be a TripMember with status "joined".
 * Validates: activityNodeId is a UUID, node exists, not archived,
 *            and node.city matches the trip's primary leg city.
 * Atomic: slot creation + behavioral signal written in one $transaction.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma, TransactionClient } from "@/lib/prisma";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";
import { getTripPhase } from "@/lib/trip-status";

const addSlotSchema = z.object({
  activityNodeId: z.string().uuid(),
  dayNumber: z.number().int().min(1).optional(),
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
        select: {
          startDate: true,
          endDate: true,
          legs: {
            select: { city: true },
            orderBy: { position: "asc" },
            take: 1,
          },
        },
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

    const tripCity = trip.legs[0]?.city ?? "";
    if (activityNode.city.toLowerCase() !== tripCity.toLowerCase()) {
      return NextResponse.json(
        { error: "Activity city does not match trip destination" },
        { status: 422 }
      );
    }

    // -------------------------------------------------------------------------
    // 5. Validate dayNumber bounds
    // -------------------------------------------------------------------------
    const requestedDay = parsed.data.dayNumber ?? 1;
    const totalDays = Math.max(
      Math.ceil(
        (new Date(trip.endDate).getTime() - new Date(trip.startDate).getTime()) /
          (1000 * 60 * 60 * 24)
      ),
      1
    );
    if (requestedDay < 1 || requestedDay > totalDays) {
      return NextResponse.json(
        { error: `Day must be between 1 and ${totalDays}` },
        { status: 400 }
      );
    }

    // -------------------------------------------------------------------------
    // 6. Atomic transaction: compute sortOrder, create slot + behavioral signal
    // -------------------------------------------------------------------------
    const slotId = uuidv4();
    const signalId = uuidv4();

    const [slot] = await prisma.$transaction(async (tx: TransactionClient) => {
      // Max sortOrder for existing slots on the requested day
      const agg = await tx.itinerarySlot.aggregate({
        where: { tripId, dayNumber: requestedDay },
        _max: { sortOrder: true },
      });

      const nextSortOrder = (agg._max.sortOrder ?? 0) + 1;

      const createdSlot = await tx.itinerarySlot.create({
        data: {
          id: slotId,
          tripId,
          activityNodeId,
          dayNumber: requestedDay,
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

      const tripPhase = getTripPhase(trip);
      const isPreTrip = tripPhase === "pre_trip";

      await tx.behavioralSignal.create({
        data: {
          id: signalId,
          userId,
          tripId,
          slotId,
          activityNodeId,
          signalType: isPreTrip ? "pre_trip_slot_added" : "discover_shortlist",
          signalValue: isPreTrip ? 0.8 : 1.0,
          tripPhase,
          rawAction: "add_to_trip_from_shortlist",
          metadata: isPreTrip
            ? {
                day_number: requestedDay,
                trip_phase: "pre_trip",
              }
            : undefined,
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
