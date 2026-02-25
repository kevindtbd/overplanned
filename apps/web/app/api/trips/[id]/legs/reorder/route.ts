/**
 * POST /api/trips/[id]/legs/reorder — Reorder all legs for a trip (organizer only)
 *
 * Body: { legOrder: string[] } — full ordered array of all leg IDs.
 * All existing leg IDs must be present — no subset reorders, no extras.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { legReorderSchema } from "@/lib/validations/trip";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  // ---------------------------------------------------------------------------
  // 1. Auth check
  // ---------------------------------------------------------------------------
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  // ---------------------------------------------------------------------------
  // 2. IDOR + organizer guard
  // ---------------------------------------------------------------------------
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { role: true, status: true },
  });

  if (!membership || membership.status !== "joined") {
    return NextResponse.json({ error: "Trip not found" }, { status: 404 });
  }

  if (membership.role !== "organizer") {
    return NextResponse.json(
      { error: "Only the trip organizer can modify legs" },
      { status: 403 }
    );
  }

  // ---------------------------------------------------------------------------
  // 3. Status gate
  // ---------------------------------------------------------------------------
  const trip = await prisma.trip.findUnique({
    where: { id: tripId },
    select: { status: true },
  });

  if (!trip || !["draft", "planning"].includes(trip.status)) {
    return NextResponse.json(
      { error: "Legs can only be modified on draft or planning trips" },
      { status: 409 }
    );
  }

  // ---------------------------------------------------------------------------
  // 4. Parse + validate body
  // ---------------------------------------------------------------------------
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = legReorderSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const { legOrder } = parsed.data;

  try {
    // -------------------------------------------------------------------------
    // 5. Fetch existing leg IDs for this trip
    // -------------------------------------------------------------------------
    const existingLegs = await prisma.tripLeg.findMany({
      where: { tripId },
      select: { id: true },
    });

    const existingIds = new Set(existingLegs.map((l: (typeof existingLegs)[number]) => l.id));

    // -------------------------------------------------------------------------
    // 6. Three-part validation
    // -------------------------------------------------------------------------

    // 6a. No duplicates in legOrder
    if (new Set(legOrder).size !== legOrder.length) {
      return NextResponse.json(
        { error: "legOrder contains duplicate IDs" },
        { status: 400 }
      );
    }

    // 6b. No missing IDs — every existing leg must appear in legOrder
    const legOrderSet = new Set(legOrder);
    const missingIds = [...existingIds].filter((id) => !legOrderSet.has(id));
    if (missingIds.length > 0) {
      return NextResponse.json(
        { error: "legOrder is missing existing leg IDs", missing: missingIds },
        { status: 400 }
      );
    }

    // 6c. No foreign IDs — every ID in legOrder must exist in the trip
    const foreignIds = legOrder.filter((id) => !existingIds.has(id));
    if (foreignIds.length > 0) {
      return NextResponse.json(
        { error: "legOrder contains IDs that do not belong to this trip", foreign: foreignIds },
        { status: 400 }
      );
    }

    // -------------------------------------------------------------------------
    // 7. Atomic position update
    // -------------------------------------------------------------------------
    await prisma.$transaction(
      legOrder.map((legId, position) =>
        prisma.tripLeg.update({
          where: { id: legId },
          data: { position },
        })
      )
    );

    return NextResponse.json({ reordered: true }, { status: 200 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/legs/reorder] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
