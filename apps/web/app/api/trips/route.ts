/**
 * POST /api/trips — Create a new trip + add creator as organizer TripMember
 * GET  /api/trips — List all trips where the authed user is a TripMember
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { createTripSchema } from "@/lib/validations/trip";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";
import { generateTripItinerary } from "@/lib/generation/generate-itinerary";
import { buildRouteString } from "@/lib/trip-legs";

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

  const parsed = createTripSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const {
    name,
    legs,
    startDate,
    endDate,
    mode,
    presetTemplate,
    personaSeed,
  } = parsed.data;

  try {
    const tripId = uuidv4();
    const memberId = uuidv4();

    const trip = await prisma.trip.create({
      data: {
        id: tripId,
        userId,
        name: name ?? null,
        startDate: new Date(startDate),
        endDate: new Date(endDate),
        mode,
        status: "planning",
        presetTemplate: presetTemplate ?? null,
        personaSeed: (personaSeed ?? undefined) as any,
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
        legs: {
          orderBy: { position: "asc" },
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

    // Generate itinerary slots per leg
    let generationResult: { slotsCreated: number; source: "seeded" | "empty" } = { slotsCreated: 0, source: "empty" };
    try {
      const userPrefs = await prisma.userPreference.findUnique({
        where: { userId },
        select: { vibePreferences: true },
      });

      const seed = {
        pace: (personaSeed as any)?.pace ?? "moderate",
        morningPreference: (personaSeed as any)?.morningPreference ?? "mid",
        foodPreferences: (personaSeed as any)?.foodPreferences ?? [],
        vibePreferences: [
          ...((personaSeed as any)?.vibePreferences ?? []),
          ...(userPrefs?.vibePreferences ?? []),
        ],
        freeformVibes: (personaSeed as any)?.freeformVibes,
        template: presetTemplate ?? (personaSeed as any)?.template,
      };
      const genResult = await generateTripItinerary(tripId, userId, seed);
      generationResult = {
        slotsCreated: genResult.totalSlotsCreated,
        source: genResult.totalSlotsCreated > 0 ? "seeded" : "empty",
      };
    } catch (err) {
      // Generation failure should not block trip creation
      console.error("[POST /api/trips] Generation error:", err);
    }

    // Re-fetch trip with slots included if generation produced results
    if (generationResult.slotsCreated > 0) {
      const fullTrip = await prisma.trip.findUnique({
        where: { id: tripId },
        include: {
          members: {
            select: { id: true, userId: true, role: true, status: true },
          },
          legs: {
            orderBy: { position: "asc" },
          },
          slots: {
            orderBy: [{ dayNumber: "asc" }, { sortOrder: "asc" }],
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
          },
        },
      });
      return NextResponse.json({ trip: fullTrip, generated: generationResult }, { status: 201 });
    }

    // Re-fetch to include legs that were created via createMany
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

    return NextResponse.json({ trip: tripWithLegs, generated: generationResult }, { status: 201 });
  } catch (err) {
    console.error("[POST /api/trips] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function GET(_req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  try {
    const memberships = await prisma.tripMember.findMany({
      where: { userId, status: "joined" },
      select: {
        role: true,
        status: true,
        joinedAt: true,
        trip: {
          select: {
            id: true,
            name: true,
            mode: true,
            status: true,
            startDate: true,
            endDate: true,
            planningProgress: true,
            createdAt: true,
            legs: {
              select: {
                id: true,
                city: true,
                country: true,
                destination: true,
                position: true,
              },
              orderBy: { position: "asc" as const },
            },
            _count: {
              select: { members: true, legs: true },
            },
          },
        },
      },
      orderBy: {
        trip: {
          createdAt: "desc",
        },
      },
    });

    const trips = memberships.map(({ role, status, joinedAt, trip }) => ({
      ...trip,
      memberCount: trip._count.members,
      legCount: trip._count.legs,
      primaryCity: trip.legs[0]?.city ?? null,
      primaryCountry: trip.legs[0]?.country ?? null,
      primaryDestination: trip.legs[0]?.destination ?? null,
      routeString: trip.legs.length > 1 ? buildRouteString(trip.legs) : null,
      myRole: role,
      myStatus: status,
      joinedAt,
    }));

    return NextResponse.json({ trips }, { status: 200 });
  } catch (err) {
    console.error("[GET /api/trips] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
