/**
 * POST /api/trips/[id]/legs — Add a new leg to a trip (organizer only)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { addLegSchema } from "@/lib/validations/trip";
import { MAX_LEGS } from "@/lib/constants/trip";
import { generateLegItinerary } from "@/lib/generation/generate-itinerary";

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
  // 3. Status gate — only draft or planning trips accept leg mutations
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

  const parsed = addLegSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // -------------------------------------------------------------------------
    // 5. Leg count gate
    // -------------------------------------------------------------------------
    const legCount = await prisma.tripLeg.count({ where: { tripId } });
    if (legCount >= MAX_LEGS) {
      return NextResponse.json(
        { error: "Maximum 8 legs per trip" },
        { status: 409 }
      );
    }

    // -------------------------------------------------------------------------
    // 6. Determine next position
    // -------------------------------------------------------------------------
    const maxPositionAgg = await prisma.tripLeg.aggregate({
      where: { tripId },
      _max: { position: true },
    });
    const nextPosition = (maxPositionAgg._max.position ?? -1) + 1;

    // -------------------------------------------------------------------------
    // 7. Create the leg
    // -------------------------------------------------------------------------
    const { city, country, timezone, destination, startDate, endDate } =
      parsed.data;

    const leg = await prisma.tripLeg.create({
      data: {
        tripId,
        position: nextPosition,
        city,
        country,
        timezone: timezone ?? null,
        destination,
        startDate: new Date(startDate),
        endDate: new Date(endDate),
      },
    });

    // -------------------------------------------------------------------------
    // 8. Fire-and-forget generation for the new leg
    // -------------------------------------------------------------------------
    try {
      const userPrefs = await prisma.userPreference.findUnique({
        where: { userId },
        select: { vibePreferences: true },
      });

      const seed = {
        pace: "moderate" as const,
        morningPreference: "mid" as const,
        foodPreferences: [] as string[],
        vibePreferences: userPrefs?.vibePreferences ?? [],
        freeformVibes: undefined,
        template: undefined,
      };

      // Non-blocking — generation failure must not block the response
      generateLegItinerary(
        tripId,
        leg.id,
        userId,
        city,
        country,
        new Date(startDate),
        new Date(endDate),
        seed,
      ).catch((err) => {
        console.error(
          `[POST /api/trips/${tripId}/legs] Background generation error for leg ${leg.id}:`,
          err
        );
      });
    } catch (err) {
      console.error(
        `[POST /api/trips/${tripId}/legs] Generation setup error for leg ${leg.id}:`,
        err
      );
    }

    return NextResponse.json({ leg }, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/legs] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
