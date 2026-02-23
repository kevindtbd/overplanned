/**
 * POST /api/trips/[id]/reflection — Submit post-trip reflection ratings + feedback
 *
 * Auth: requires session + joined TripMember
 * Body: { ratings: [{ slotId, rating }], feedback?: string }
 * Merges into trip.reflectionData keyed by userId (V8: userId from session, never body)
 * Logs BehavioralSignals for each rating (server-side, atomic in $transaction)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { reflectionSchema, REFLECTION_SIGNAL_MAP } from "@/lib/validations/reflection";
import { prisma } from "@/lib/prisma";

export async function POST(
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

  const parsed = reflectionSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // Verify membership (IDOR prevention: must be joined member)
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Fetch trip with slots to validate status and resolve activityNodeIds
    const trip = await prisma.trip.findUnique({
      where: { id: tripId },
      select: {
        status: true,
        reflectionData: true,
        slots: {
          select: { id: true, activityNodeId: true },
        },
      },
    });

    if (!trip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Reflection only allowed on completed or active trips
    if (trip.status !== "completed" && trip.status !== "active") {
      return NextResponse.json(
        { error: "Reflection is only available for active or completed trips" },
        { status: 409 }
      );
    }

    // Build slot lookup for activityNodeId resolution
    const slotMap = new Map(trip.slots.map((s) => [s.id, s.activityNodeId]));

    // Validate all slotIds belong to this trip
    for (const r of parsed.data.ratings) {
      if (!slotMap.has(r.slotId)) {
        return NextResponse.json(
          { error: "Validation failed", details: { ratings: [`Slot ${r.slotId} not found in this trip`] } },
          { status: 400 }
        );
      }
    }

    // Read-merge-write: never blind overwrite (preserves other users' reflections)
    const existing = (trip.reflectionData as Record<string, unknown>) ?? {};
    const merged = {
      ...existing,
      [userId]: {
        ratings: parsed.data.ratings,
        feedback: parsed.data.feedback ?? null,
        submittedAt: new Date().toISOString(),
      },
    };

    // Build behavioral signals for each rating
    const signalCreates = parsed.data.ratings.map((r) => {
      const mapping = REFLECTION_SIGNAL_MAP[r.rating];
      return prisma.behavioralSignal.create({
        data: {
          userId,
          tripId,
          slotId: r.slotId,
          activityNodeId: slotMap.get(r.slotId) ?? null,
          signalType: mapping.signalType,
          signalValue: mapping.signalValue,
          tripPhase: "post_trip",
          rawAction: `reflection_${r.rating}`,
        },
      });
    });

    // Atomic: update reflectionData + log all signals in one transaction
    await prisma.$transaction([
      prisma.trip.update({
        where: { id: tripId },
        data: { reflectionData: merged },
      }),
      ...signalCreates,
    ]);

    return NextResponse.json({ submitted: true }, { status: 200 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/reflection] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
