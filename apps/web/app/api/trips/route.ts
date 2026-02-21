/**
 * POST /api/trips — Create a new trip + add creator as organizer TripMember
 * GET  /api/trips — List all trips where the authed user is a TripMember
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { PrismaClient } from "@prisma/client";
import { createTripSchema } from "@/lib/validations/trip";
import { v4 as uuidv4 } from "uuid";

const prisma = new PrismaClient();

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
    destination,
    city,
    country,
    timezone,
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
        destination,
        city,
        country,
        timezone,
        startDate: new Date(startDate),
        endDate: new Date(endDate),
        mode: mode as never,
        presetTemplate: presetTemplate ?? null,
        personaSeed: personaSeed ?? undefined,
        members: {
          create: {
            id: memberId,
            userId,
            role: "organizer" as never,
            status: "active" as never,
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

    return NextResponse.json({ trip }, { status: 201 });
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
      where: { userId },
      select: {
        role: true,
        status: true,
        joinedAt: true,
        trip: {
          select: {
            id: true,
            name: true,
            destination: true,
            city: true,
            country: true,
            mode: true,
            status: true,
            startDate: true,
            endDate: true,
            planningProgress: true,
            createdAt: true,
            _count: {
              select: { members: true },
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
