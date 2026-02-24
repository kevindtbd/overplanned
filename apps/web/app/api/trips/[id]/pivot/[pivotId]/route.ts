/**
 * PATCH /api/trips/[id]/pivot/[pivotId]
 *
 * Resolves a pivot event: accepted (swap slot activity) or rejected (no-op).
 *
 * Auth-gated — user must be a joined member of the trip.
 * If accepted with selectedNodeId, validates it exists in PivotEvent.alternativeIds.
 * Resets voteState on slot if pivot is accepted (voted slot -> reset votes).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { pivotResolveSchema } from "@/lib/validations/pivot";

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; pivotId: string } },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId, pivotId } = params;

  // Parse + validate body
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = pivotResolveSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const { outcome, selectedNodeId } = parsed.data;

  // Verify trip membership
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { status: true },
  });

  if (!membership || membership.status !== "joined") {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Fetch pivot event
  const pivotEvent = await prisma.pivotEvent.findUnique({
    where: { id: pivotId },
  });

  if (!pivotEvent || pivotEvent.tripId !== tripId) {
    return NextResponse.json({ error: "Pivot not found" }, { status: 404 });
  }

  if (pivotEvent.status !== "proposed") {
    return NextResponse.json(
      { error: "Pivot already resolved" },
      { status: 409 },
    );
  }

  // Validate selectedNodeId if accepted
  if (outcome === "accepted") {
    if (!selectedNodeId) {
      return NextResponse.json(
        { error: "selectedNodeId required for accepted outcome" },
        { status: 400 },
      );
    }

    if (!pivotEvent.alternativeIds.includes(selectedNodeId)) {
      return NextResponse.json(
        { error: "selectedNodeId not in alternatives" },
        { status: 400 },
      );
    }
  }

  const responseTimeMs = Date.now() - pivotEvent.createdAt.getTime();

  try {
    const signalType = outcome === "accepted" ? "pivot_accepted" : "pivot_rejected";

    if (outcome === "accepted") {
      // Accepted: update pivot + swap slot + reset voteState + log signal
      const [updatedPivot, updatedSlot] = await prisma.$transaction([
        prisma.pivotEvent.update({
          where: { id: pivotId },
          data: {
            status: "accepted",
            resolvedAt: new Date(),
            responseTimeMs,
            selectedNodeId,
          },
        }),
        prisma.itinerarySlot.update({
          where: { id: pivotEvent.slotId },
          data: {
            activityNodeId: selectedNodeId,
            wasSwapped: true,
            swappedFromId: pivotEvent.originalNodeId,
            pivotEventId: pivotEvent.id,
            voteState: Prisma.JsonNull,
            isContested: false,
            updatedAt: new Date(),
          },
        }),
        prisma.behavioralSignal.create({
          data: {
            id: uuidv4(),
            userId,
            tripId,
            slotId: pivotEvent.slotId,
            activityNodeId: selectedNodeId,
            signalType: signalType,
            signalValue: 1.0,
            tripPhase: "active",
            rawAction: "pivot_accepted",
          },
        }),
      ]);

      return NextResponse.json({
        pivotEvent: updatedPivot,
        updatedSlot,
      });
    } else {
      // Rejected: update pivot + log signal (no slot change)
      const [updatedPivot] = await prisma.$transaction([
        prisma.pivotEvent.update({
          where: { id: pivotId },
          data: {
            status: "rejected",
            resolvedAt: new Date(),
            responseTimeMs,
          },
        }),
        prisma.behavioralSignal.create({
          data: {
            id: uuidv4(),
            userId,
            tripId,
            slotId: pivotEvent.slotId,
            activityNodeId: pivotEvent.originalNodeId,
            signalType: signalType,
            signalValue: -0.5,
            tripPhase: "active",
            rawAction: "pivot_rejected",
          },
        }),
      ]);

      return NextResponse.json({
        pivotEvent: updatedPivot,
      });
    }
  } catch (err) {
    console.error("Pivot resolution failed:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
