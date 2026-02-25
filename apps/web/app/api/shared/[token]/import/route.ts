/**
 * POST /api/shared/[token]/import — Import a shared trip as a new solo trip
 *
 * Auth required. Creates new Trip + TripLegs + ItinerarySlots with fresh UUIDs.
 * Import limit: 1 per user per shared token.
 */

import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma, TransactionClient, PrismaJsonNull } from "@/lib/prisma";
import { rateLimit, rateLimitPresets } from "@/lib/rate-limit";
import { sanitizeToken } from "@/lib/validations/share";

export async function POST(
  req: NextRequest,
  { params }: { params: { token: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // Rate limit: authenticated tier
  const limited = rateLimit(req, rateLimitPresets.authenticated, userId);
  if (limited) return limited;

  const safeToken = sanitizeToken(params.token);
  if (!safeToken) {
    return NextResponse.json({ error: "Invalid token" }, { status: 400 });
  }

  try {
    // Fetch token + full trip data for cloning
    const tokenRecord = await prisma.sharedTripToken.findUnique({
      where: { token: safeToken },
      include: {
        trip: {
          include: {
            legs: {
              orderBy: { position: "asc" },
            },
            slots: {
              include: { activityNode: true },
              orderBy: [{ dayNumber: "asc" }, { sortOrder: "asc" }],
            },
          },
        },
      },
    });

    if (!tokenRecord) {
      return NextResponse.json({ error: "Shared trip not found" }, { status: 404 });
    }

    // Check expiry + revoked
    if (tokenRecord.revokedAt || tokenRecord.expiresAt < new Date()) {
      return NextResponse.json({ error: "Share link has expired" }, { status: 410 });
    }

    // V9: Import limit — 1 per user per shared token
    // Store sourceSharedTokenId in logisticsState to track provenance
    const existingImport = await prisma.trip.findFirst({
      where: {
        userId,
        logisticsState: {
          path: ["sourceSharedTokenId"],
          equals: tokenRecord.id,
        },
      },
      select: { id: true },
    });

    if (existingImport) {
      return NextResponse.json(
        { error: "You have already imported this trip", tripId: existingImport.id },
        { status: 409 }
      );
    }

    const sourceTrip = tokenRecord.trip;

    // Clone in a transaction — fresh UUIDs for everything
    const result = await prisma.$transaction(async (tx: TransactionClient) => {
      // 1. Create new Trip (solo mode, planning status)
      const newTripId = crypto.randomUUID();
      const newTrip = await tx.trip.create({
        data: {
          id: newTripId,
          userId,
          name: sourceTrip.name ? `${sourceTrip.name} (imported)` : "Imported trip",
          mode: "solo",
          status: "planning",
          startDate: sourceTrip.startDate,
          endDate: sourceTrip.endDate,
          presetTemplate: sourceTrip.presetTemplate,
          personaSeed: sourceTrip.personaSeed ?? undefined,
          logisticsState: { sourceSharedTokenId: tokenRecord.id },
        },
      });

      // 2. Create organizer membership
      await tx.tripMember.create({
        data: {
          tripId: newTripId,
          userId,
          role: "organizer",
          status: "joined",
          joinedAt: new Date(),
        },
      });

      // 3. Clone TripLegs — build old->new ID map for slot assignment
      const legIdMap = new Map<string, string>();
      for (const leg of sourceTrip.legs) {
        const newLegId = crypto.randomUUID();
        legIdMap.set(leg.id, newLegId);

        await tx.tripLeg.create({
          data: {
            id: newLegId,
            tripId: newTripId,
            position: leg.position,
            city: leg.city,
            country: leg.country,
            timezone: leg.timezone,
            destination: leg.destination,
            startDate: leg.startDate,
            endDate: leg.endDate,
            arrivalTime: leg.arrivalTime,
            departureTime: leg.departureTime,
            transitMode: leg.transitMode,
            transitDurationMin: leg.transitDurationMin,
            transitCostHint: leg.transitCostHint,
          },
        });
      }

      // 4. Clone ItinerarySlots — new IDs, reset status, clear voteState
      for (const slot of sourceTrip.slots) {
        await tx.itinerarySlot.create({
          data: {
            id: crypto.randomUUID(),
            tripId: newTripId,
            tripLegId: slot.tripLegId ? legIdMap.get(slot.tripLegId) ?? null : null,
            activityNodeId: slot.activityNodeId,
            dayNumber: slot.dayNumber,
            sortOrder: slot.sortOrder,
            slotType: slot.slotType,
            status: "proposed", // Reset — importer starts fresh
            startTime: slot.startTime,
            endTime: slot.endTime,
            durationMinutes: slot.durationMinutes,
            isLocked: false,
            voteState: PrismaJsonNull, // Clear voting data
            isContested: false,
            wasSwapped: false,
          },
        });
      }

      // 5. Log behavioral signal
      await tx.behavioralSignal.create({
        data: {
          userId,
          tripId: newTripId,
          signalType: "share_action",
          signalValue: 1.0,
          tripPhase: "pre_trip",
          rawAction: "trip_imported",
        },
      });

      return newTrip;
    });

    // Increment importCount (fire-and-forget, outside transaction)
    prisma.sharedTripToken
      .update({
        where: { id: tokenRecord.id },
        data: { importCount: { increment: 1 } },
      })
      .catch(() => {});

    return NextResponse.json({ tripId: result.id }, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/shared/${params.token}/import] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
