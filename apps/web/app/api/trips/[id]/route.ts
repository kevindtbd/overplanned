/**
 * GET   /api/trips/[id] — Fetch trip detail (must be a TripMember)
 * PATCH /api/trips/[id] — Update trip fields (must be organizer)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateTripSchema } from "@/lib/validations/trip";
import { prisma } from "@/lib/prisma";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  try {
    // IDOR prevention: verify the caller is a TripMember before fetching data
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true, status: true },
    });

    if (!membership) {
      // Return 404 regardless of whether the trip exists, to avoid leaking IDs
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    const trip = await prisma.trip.findUnique({
      where: { id: tripId },
      include: {
        members: {
          select: {
            id: true,
            userId: true,
            role: true,
            status: true,
            joinedAt: true,
            user: {
              select: {
                id: true,
                name: true,
                avatarUrl: true,
              },
            },
          },
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

    if (!trip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    return NextResponse.json(
      { trip, myRole: membership.role, myStatus: membership.status },
      { status: 200 }
    );
  } catch (err) {
    console.error(`[GET /api/trips/${tripId}] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PATCH(
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

  const parsed = updateTripSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // IDOR prevention: require organizer role to mutate trip
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true },
    });

    if (!membership) {
      // Caller is not a member — return 404 to avoid leaking IDs
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.role !== "organizer") {
      return NextResponse.json(
        { error: "Only the trip organizer can update this trip" },
        { status: 403 }
      );
    }

    const { name, status, planningProgress } = parsed.data;

    const updated = await prisma.trip.update({
      where: { id: tripId },
      data: {
        ...(name !== undefined && { name }),
        ...(status !== undefined && { status }),
        ...(planningProgress !== undefined && { planningProgress }),
      },
      select: {
        id: true,
        name: true,
        destination: true,
        city: true,
        country: true,
        mode: true,
        status: true,
        planningProgress: true,
        startDate: true,
        endDate: true,
        updatedAt: true,
      },
    });

    return NextResponse.json({ trip: updated }, { status: 200 });
  } catch (err) {
    console.error(`[PATCH /api/trips/${tripId}] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
