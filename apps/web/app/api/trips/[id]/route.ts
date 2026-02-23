/**
 * GET   /api/trips/[id] — Fetch trip detail (must be a TripMember)
 * PATCH /api/trips/[id] — Update trip fields (must be organizer)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateTripSchema } from "@/lib/validations/trip";
import { prisma } from "@/lib/prisma";
import { shouldAutoTransition, validateTransition, getWritableFields } from "@/lib/trip-status";
import { promoteDraftToPlanning } from "@/lib/generation/promote-draft";

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
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.status !== "joined") {
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

    // Auto-transition: planning -> active when start date has arrived
    // Only organizer role triggers the write to prevent guest-initiated mutations
    if (
      membership.role === "organizer" &&
      shouldAutoTransition(trip.status, new Date(trip.startDate))
    ) {
      await prisma.trip.update({
        where: { id: trip.id },
        data: { status: "active" },
      });
      trip.status = "active";
      console.info(`[auto-transition] Trip ${trip.id} planning -> active (organizer: ${userId})`);
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
      select: { role: true, status: true },
    });

    if (!membership) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.role !== "organizer") {
      return NextResponse.json(
        { error: "Only the trip organizer can update this trip" },
        { status: 403 }
      );
    }

    // Fetch current trip status for state machine validation
    const currentTrip = await prisma.trip.findUnique({
      where: { id: tripId },
      select: { status: true },
    });

    if (!currentTrip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    const currentStatus = currentTrip.status;

    // Validate status transition if a status change is requested
    if (parsed.data.status !== undefined && parsed.data.status !== currentStatus) {
      const requestedStatus = parsed.data.status;
      if (!validateTransition(currentStatus, requestedStatus)) {
        return NextResponse.json(
          {
            error: "Invalid status transition",
            detail: `Cannot transition from '${currentStatus}' to '${requestedStatus}'`,
          },
          { status: 409 }
        );
      }
    }

    // Apply field-level write guards: silently drop fields not writable in current status
    const writable = getWritableFields(currentStatus);
    const filteredData = Object.fromEntries(
      Object.entries(parsed.data).filter(([key]) => writable.has(key))
    );

    const {
      name,
      status,
      planningProgress,
      startDate,
      endDate,
      mode,
      presetTemplate,
      personaSeed,
    } = filteredData as typeof parsed.data;

    const isDraftPromotion = currentStatus === "draft" && status === "planning";

    const updated = await prisma.trip.update({
      where: { id: tripId },
      data: {
        ...(name !== undefined && { name }),
        ...(status !== undefined && { status }),
        ...(planningProgress !== undefined && { planningProgress }),
        ...(startDate !== undefined && { startDate: new Date(startDate) }),
        ...(endDate !== undefined && { endDate: new Date(endDate) }),
        ...(mode !== undefined && { mode }),
        ...(presetTemplate !== undefined && { presetTemplate }),
        ...(personaSeed !== undefined && { personaSeed: personaSeed as any }),
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

    if (isDraftPromotion) {
      try {
        const { trip: generatedTrip, generated } = await promoteDraftToPlanning(tripId, userId);
        return NextResponse.json({ trip: generatedTrip, generated }, { status: 200 });
      } catch (err) {
        console.error(`[PATCH /api/trips/${tripId}] Generation error after promotion:`, err);
        return NextResponse.json({ trip: updated, generated: { slotsCreated: 0, source: "empty" } }, { status: 200 });
      }
    }

    return NextResponse.json({ trip: updated }, { status: 200 });
  } catch (err) {
    console.error(`[PATCH /api/trips/${tripId}] DB error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
