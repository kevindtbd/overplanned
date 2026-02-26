/**
 * PATCH /api/slots/[slotId]/move
 *
 * Moves an ItinerarySlot to a different day and/or reorders it within a day.
 * Records a BehavioralSignal atomically.
 *
 * Body: { dayNumber?: number, sortOrder?: number }
 *   - dayNumber: move slot to this day (appends to end if sortOrder not given)
 *   - sortOrder: insert at this position within the day
 *   - At least one must be provided
 *
 * Auth-gated — user must be a joined member of the trip that owns this slot.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { prisma, TransactionClient } from "@/lib/prisma";
import { getTripPhase } from "@/lib/trip-status";

const moveSlotSchema = z
  .object({
    dayNumber: z.number().int().min(1).optional(),
    sortOrder: z.number().int().min(1).optional(),
  })
  .refine((data) => data.dayNumber !== undefined || data.sortOrder !== undefined, {
    message: "At least one of dayNumber or sortOrder must be provided",
  });

export async function PATCH(
  req: NextRequest,
  { params }: { params: { slotId: string } },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { slotId } = params;

  // Parse + validate body
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = moveSlotSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const { dayNumber: targetDay, sortOrder: targetSort } = parsed.data;

  // Fetch slot and verify joined trip membership
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    select: {
      id: true,
      tripId: true,
      dayNumber: true,
      sortOrder: true,
      isLocked: true,
      trip: {
        select: {
          startDate: true,
          endDate: true,
          members: {
            where: { userId, status: "joined" },
            select: { id: true },
          },
        },
      },
    },
  });

  if (!slot) {
    return NextResponse.json({ error: "Slot not found" }, { status: 404 });
  }

  if (slot.trip.members.length === 0) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (slot.isLocked) {
    return NextResponse.json(
      { error: "Cannot move a locked slot" },
      { status: 409 },
    );
  }

  // Validate dayNumber against trip date range
  if (targetDay !== undefined) {
    const totalDays = Math.max(
      Math.ceil(
        (new Date(slot.trip.endDate).getTime() -
          new Date(slot.trip.startDate).getTime()) /
          (1000 * 60 * 60 * 24),
      ),
      1,
    );
    if (targetDay > totalDays) {
      return NextResponse.json(
        { error: `dayNumber must be between 1 and ${totalDays}` },
        { status: 400 },
      );
    }
  }

  // Execute move inside a transaction
  const updatedSlot = await prisma.$transaction(async (tx: TransactionClient) => {
    const currentDay = slot.dayNumber;
    const currentSort = slot.sortOrder;

    if (targetDay !== undefined && targetSort !== undefined) {
      // Case 3: Move to different day + specific position
      // Shift slots in target day to make room
      await tx.itinerarySlot.updateMany({
        where: {
          tripId: slot.tripId,
          dayNumber: targetDay,
          sortOrder: { gte: targetSort },
        },
        data: { sortOrder: { increment: 1 } },
      });

      // Place slot at target position in target day
      const moved = await tx.itinerarySlot.update({
        where: { id: slotId },
        data: {
          dayNumber: targetDay,
          sortOrder: targetSort,
          updatedAt: new Date(),
        },
        include: {
          activityNode: {
            select: {
              id: true,
              name: true,
              category: true,
              latitude: true,
              longitude: true,
              priceLevel: true,
              primaryImageUrl: true,
            },
          },
        },
      });

      return moved;
    } else if (targetDay !== undefined) {
      // Case 1: Day move only — append to end of target day
      const agg = await tx.itinerarySlot.aggregate({
        where: { tripId: slot.tripId, dayNumber: targetDay },
        _max: { sortOrder: true },
      });
      const newSortOrder = (agg._max.sortOrder ?? 0) + 1;

      const moved = await tx.itinerarySlot.update({
        where: { id: slotId },
        data: {
          dayNumber: targetDay,
          sortOrder: newSortOrder,
          updatedAt: new Date(),
        },
        include: {
          activityNode: {
            select: {
              id: true,
              name: true,
              category: true,
              latitude: true,
              longitude: true,
              priceLevel: true,
              primaryImageUrl: true,
            },
          },
        },
      });

      return moved;
    } else {
      // Case 2: Reorder within current day (targetSort is defined)
      const finalTargetSort = targetSort!;

      if (finalTargetSort !== currentSort) {
        if (finalTargetSort < currentSort) {
          // Moving up: shift slots [targetSort, currentSort-1] down by 1
          await tx.itinerarySlot.updateMany({
            where: {
              tripId: slot.tripId,
              dayNumber: currentDay,
              sortOrder: { gte: finalTargetSort, lt: currentSort },
            },
            data: { sortOrder: { increment: 1 } },
          });
        } else {
          // Moving down: shift slots [currentSort+1, targetSort] up by 1
          await tx.itinerarySlot.updateMany({
            where: {
              tripId: slot.tripId,
              dayNumber: currentDay,
              sortOrder: { gt: currentSort, lte: finalTargetSort },
            },
            data: { sortOrder: { decrement: 1 } },
          });
        }
      }

      const moved = await tx.itinerarySlot.update({
        where: { id: slotId },
        data: {
          sortOrder: finalTargetSort,
          updatedAt: new Date(),
        },
        include: {
          activityNode: {
            select: {
              id: true,
              name: true,
              category: true,
              latitude: true,
              longitude: true,
              priceLevel: true,
              primaryImageUrl: true,
            },
          },
        },
      });

      return moved;
    }
  });

  // Log behavioral signal (fire-and-forget, outside transaction for perf)
  const tripPhase = getTripPhase(slot.trip);
  const isPreTrip = tripPhase === "pre_trip";

  try {
    await prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId: slot.tripId,
        slotId,
        signalType: isPreTrip ? "pre_trip_reorder" : "slot_moved",
        signalValue: isPreTrip ? 0.3 : 1.0,
        tripPhase,
        rawAction: targetDay
          ? `moved_to_day_${targetDay}`
          : `reordered_to_${targetSort}`,
        metadata: isPreTrip
          ? {
              day_number: targetDay ?? slot.dayNumber,
              slot_index: targetSort ?? slot.sortOrder,
              original_day: slot.dayNumber,
              original_sort: slot.sortOrder,
              trip_phase: "pre_trip",
            }
          : undefined,
      },
    });
  } catch {
    // Signal logging failure should not break the move
    console.error("Failed to log move behavioral signal");
  }

  return NextResponse.json({ success: true, data: updatedSlot });
}
