/**
 * PATCH /api/slots/[slotId]/swap
 *
 * Accepts a pivot swap: updates the ItinerarySlot to the selected ActivityNode,
 * marks wasSwapped=true, records pivotEventId, and updates the PivotEvent status.
 *
 * Auth-gated — user must be a member of the trip that owns this slot.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

interface SwapBody {
  pivotEventId: string;
  selectedNodeId: string;
}

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

  let body: SwapBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { pivotEventId, selectedNodeId } = body;

  if (!pivotEventId || !selectedNodeId) {
    return NextResponse.json(
      { error: "pivotEventId and selectedNodeId are required" },
      { status: 400 },
    );
  }

  // Fetch the slot and verify trip membership
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    select: {
      id: true,
      tripId: true,
      activityNodeId: true,
      isLocked: true,
      trip: {
        select: {
          members: {
            where: { userId },
            select: { id: true },
          },
        },
      },
    },
  });

  if (!slot) {
    return NextResponse.json({ error: "Slot not found" }, { status: 404 });
  }

  const isMember = slot.trip.members.length > 0;
  if (!isMember) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (slot.isLocked) {
    return NextResponse.json(
      { error: "Cannot swap a locked slot" },
      { status: 409 },
    );
  }

  // Verify the ActivityNode exists
  const activityNode = await prisma.activityNode.findUnique({
    where: { id: selectedNodeId },
    select: { id: true, status: true },
  });

  if (!activityNode || activityNode.status === "archived") {
    return NextResponse.json(
      { error: "Selected activity not available" },
      { status: 422 },
    );
  }

  // Verify the PivotEvent belongs to this slot
  const pivotEvent = await prisma.pivotEvent.findFirst({
    where: {
      id: pivotEventId,
      slotId,
      tripId: slot.tripId,
      status: "proposed",
    },
    select: { id: true, createdAt: true },
  });

  if (!pivotEvent) {
    return NextResponse.json(
      { error: "PivotEvent not found or already resolved" },
      { status: 409 },
    );
  }

  const responseTimeMs = Date.now() - new Date(pivotEvent.createdAt).getTime();

  // Atomic update: swap slot + resolve pivot event
  await prisma.$transaction([
    prisma.itinerarySlot.update({
      where: { id: slotId },
      data: {
        activityNodeId: selectedNodeId,
        wasSwapped: true,
        pivotEventId,
        updatedAt: new Date(),
      },
    }),
    prisma.pivotEvent.update({
      where: { id: pivotEventId },
      data: {
        status: "accepted",
        selectedNodeId,
        resolvedAt: new Date(),
        responseTimeMs,
      },
    }),
  ]);

  return NextResponse.json({
    success: true,
    data: {
      slotId,
      selectedNodeId,
      pivotEventId,
      responseTimeMs,
    },
  });
}
