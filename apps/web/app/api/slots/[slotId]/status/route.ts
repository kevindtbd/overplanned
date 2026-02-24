/**
 * PATCH /api/slots/[slotId]/status
 *
 * Updates an ItinerarySlot's status or lock state, and records a
 * BehavioralSignal atomically.
 *
 * Actions:
 *   confirm → status: "confirmed"  (state machine validated)
 *   skip    → status: "skipped"    (state machine validated)
 *   lock    → toggles isLocked     (no status change)
 *
 * Auth-gated — user must be a joined member of the trip that owns this slot.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import {
  updateSlotStatusSchema,
  VALID_TRANSITIONS,
} from "@/lib/validations/slot";

const ACTION_TO_STATUS = {
  confirm: "confirmed",
  skip: "skipped",
} as const;

const ACTION_TO_SIGNAL = {
  confirm: { signalType: "slot_confirm" as const, signalValue: 1.0 },
  skip: { signalType: "slot_skip" as const, signalValue: -0.5 },
};

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

  const parsed = updateSlotStatusSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const { action } = parsed.data;

  // Fetch slot and verify joined trip membership in one query
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    select: {
      id: true,
      tripId: true,
      status: true,
      isLocked: true,
      activityNodeId: true,
      trip: {
        select: {
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

  // --- lock action: toggle isLocked, no status transition needed ---
  if (action === "lock") {
    const nextLocked = !slot.isLocked;
    const signalValue = nextLocked ? 1.0 : 0;

    const [updatedSlot] = await prisma.$transaction([
      prisma.itinerarySlot.update({
        where: { id: slotId },
        data: { isLocked: nextLocked, updatedAt: new Date() },
      }),
      prisma.behavioralSignal.create({
        data: {
          id: uuidv4(),
          userId,
          tripId: slot.tripId,
          slotId,
          activityNodeId: slot.activityNodeId,
          signalType: "slot_complete",
          signalValue,
          tripPhase: "pre_trip",
          rawAction: `slot_lock_${nextLocked ? "on" : "off"}`,
        },
      }),
    ]);

    return NextResponse.json({ success: true, data: updatedSlot });
  }

  // --- confirm / skip actions: validate state machine transition ---
  const currentStatus = slot.status;
  const allowedTargets = VALID_TRANSITIONS[currentStatus] ?? [];
  const targetStatus = ACTION_TO_STATUS[action];

  if (!allowedTargets.includes(targetStatus)) {
    return NextResponse.json(
      {
        error: "Invalid transition",
        detail: `Cannot ${action} a slot with status "${currentStatus}"`,
      },
      { status: 409 },
    );
  }

  const { signalType, signalValue } = ACTION_TO_SIGNAL[action];

  const [updatedSlot] = await prisma.$transaction([
    prisma.itinerarySlot.update({
      where: { id: slotId },
      data: { status: targetStatus, updatedAt: new Date() },
    }),
    prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId: slot.tripId,
        slotId,
        activityNodeId: slot.activityNodeId,
        signalType: signalType as "slot_confirm" | "slot_skip",
        signalValue,
        tripPhase: "pre_trip",
        rawAction: `slot_${action}`,
      },
    }),
  ]);

  return NextResponse.json({ success: true, data: updatedSlot });
}
