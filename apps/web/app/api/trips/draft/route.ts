/**
 * POST /api/trips/draft — Save a draft trip idea + add creator as organizer TripMember.
 * Does NOT trigger itinerary generation.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { createDraftSchema } from "@/lib/validations/trip";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";

const DRAFT_CAP = 10;

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = createDraftSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const { legs, startDate, endDate } = parsed.data;

  try {
    const draftCount = await prisma.trip.count({
      where: { userId, status: "draft" },
    });

    if (draftCount >= DRAFT_CAP) {
      return NextResponse.json(
        { error: "Too many saved drafts. Delete some before creating new ones." },
        { status: 429 }
      );
    }

    const tripId = uuidv4();
    const memberId = uuidv4();

    const trip = await prisma.trip.create({
      data: {
        id: tripId,
        userId,
        startDate: new Date(startDate),
        endDate: new Date(endDate),
        mode: "solo",
        status: "draft",
        members: {
          create: {
            id: memberId,
            userId,
            role: "organizer",
            status: "joined",
          },
        },
      },
      include: {
        members: {
          select: {
            id: true,
            userId: true,
            role: true,
            status: true,
          },
        },
      },
    });

    // Create TripLeg records
    await prisma.tripLeg.createMany({
      data: legs.map((leg, i) => ({
        tripId,
        position: i,
        city: leg.city,
        country: leg.country,
        timezone: leg.timezone ?? null,
        destination: leg.destination,
        startDate: new Date(leg.startDate),
        endDate: new Date(leg.endDate),
        arrivalTime: leg.arrivalTime ?? null,
        departureTime: leg.departureTime ?? null,
        transitMode: leg.transitMode ?? null,
        transitDurationMin: leg.transitDurationMin ?? null,
        transitCostHint: leg.transitCostHint ?? null,
      })),
    });

    // Re-fetch to include legs created via createMany
    const tripWithLegs = await prisma.trip.findUnique({
      where: { id: tripId },
      include: {
        members: {
          select: { id: true, userId: true, role: true, status: true },
        },
        legs: {
          orderBy: { position: "asc" },
        },
      },
    });

    return NextResponse.json({ trip: tripWithLegs }, { status: 201 });
  } catch (err) {
    console.error("[POST /api/trips/draft] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
