/**
 * POST /api/trips/[id]/split-day -- Fork a day into subgroups
 *
 * Assigns subsets of slots to different member subgroups for a given day.
 * Organizer-only. Each subgroup gets its own set of slots via assignedTo.
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { splitDaySchema } from "@/lib/validations/split-day";
import { requireAuth, requireTripMember } from "@/lib/api/helpers";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const auth = await requireAuth();
  if (auth instanceof NextResponse) return auth;
  const { userId } = auth;

  const { id: tripId } = params;

  // Membership check
  const membership = await requireTripMember(tripId, userId);
  if (membership instanceof NextResponse) return membership;

  if (membership.role !== "organizer") {
    return NextResponse.json(
      { error: "Only the organizer can split days" },
      { status: 403 }
    );
  }

  // Parse and validate body
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = splitDaySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "Validation failed",
        details: parsed.error.flatten().fieldErrors,
      },
      { status: 400 }
    );
  }

  const { dayNumber, subgroups } = parsed.data;

  try {
    // Collect all slotIds from all subgroups
    const allSlotIds = subgroups.flatMap((sg) => sg.slotIds);

    // Verify all slots belong to this trip and dayNumber
    const foundSlots = await prisma.itinerarySlot.findMany({
      where: { id: { in: allSlotIds }, tripId, dayNumber },
      select: { id: true },
    });

    if (foundSlots.length !== allSlotIds.length) {
      return NextResponse.json(
        { error: "Some slots not found in this trip/day" },
        { status: 400 }
      );
    }

    // Update each subgroup's slots with their assigned members
    await prisma.$transaction(
      subgroups.map((sg) =>
        prisma.itinerarySlot.updateMany({
          where: { id: { in: sg.slotIds } },
          data: { assignedTo: sg.memberIds },
        })
      )
    );

    // Log behavioral signal
    await prisma.behavioralSignal.create({
      data: {
        userId,
        tripId,
        signalType: "share_action",
        signalValue: 1.0,
        tripPhase: "active",
        rawAction: `split_day:${dayNumber}`,
      },
    });

    return NextResponse.json({ success: true }, { status: 200 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/split-day] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
