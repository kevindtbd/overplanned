/**
 * GET /api/shared/[token] — Public read-only shared trip view
 *
 * No auth required. Rate limited (public tier).
 * Strips: member PII, internal IDs, voteState, behavioral data.
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { rateLimit, rateLimitPresets } from "@/lib/rate-limit";
import { sanitizeToken } from "@/lib/validations/share";

export async function GET(
  req: NextRequest,
  { params }: { params: { token: string } }
) {
  // Rate limit: public tier
  const limited = rateLimit(req, rateLimitPresets.public);
  if (limited) return limited;

  const safeToken = sanitizeToken(params.token);
  if (!safeToken) {
    return NextResponse.json({ error: "Invalid token" }, { status: 400 });
  }

  try {
    const tokenRecord = await prisma.sharedTripToken.findUnique({
      where: { token: safeToken },
      include: {
        trip: {
          include: {
            legs: {
              orderBy: { position: "asc" },
              select: {
                id: true,
                position: true,
                city: true,
                country: true,
                destination: true,
                timezone: true,
                startDate: true,
                endDate: true,
              },
            },
            slots: {
              include: {
                activityNode: {
                  select: {
                    name: true,
                    canonicalName: true,
                    category: true,
                    subcategory: true,
                    neighborhood: true,
                    priceLevel: true,
                    primaryImageUrl: true,
                    descriptionShort: true,
                    latitude: true,
                    longitude: true,
                  },
                },
              },
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

    // Increment viewCount (fire-and-forget)
    prisma.sharedTripToken
      .update({
        where: { id: tokenRecord.id },
        data: { viewCount: { increment: 1 } },
      })
      .catch(() => {});

    const trip = tokenRecord.trip;

    // Build response — strip PII/internal data
    const tripPreview = {
      id: trip.id,
      name: trip.name,
      mode: trip.mode,
      status: trip.status,
      startDate: trip.startDate.toISOString(),
      endDate: trip.endDate.toISOString(),
      presetTemplate: trip.presetTemplate,
      // Use first leg for destination display (multi-city trips show first leg)
      destination: trip.legs[0]?.destination ?? "",
      city: trip.legs[0]?.city ?? "",
      country: trip.legs[0]?.country ?? "",
      timezone: trip.legs[0]?.timezone ?? "UTC",
    };

    // Group slots by day
    const slotsByDay: Record<string, Array<{
      id: string;
      dayNumber: number;
      sortOrder: number;
      slotType: string;
      status: string;
      startTime: string | null;
      endTime: string | null;
      durationMinutes: number | null;
      activity: {
        name: string;
        canonicalName: string;
        category: string;
        subcategory: string | null;
        neighborhood: string | null;
        priceLevel: number | null;
        primaryImageUrl: string | null;
        descriptionShort: string | null;
        latitude: number;
        longitude: number;
      } | null;
    }>> = {};

    for (const slot of trip.slots) {
      const day = String(slot.dayNumber);
      if (!slotsByDay[day]) slotsByDay[day] = [];

      slotsByDay[day].push({
        id: slot.id,
        dayNumber: slot.dayNumber,
        sortOrder: slot.sortOrder,
        slotType: slot.slotType,
        status: slot.status,
        startTime: slot.startTime?.toISOString() ?? null,
        endTime: slot.endTime?.toISOString() ?? null,
        durationMinutes: slot.durationMinutes,
        activity: slot.activityNode
          ? {
              name: slot.activityNode.name,
              canonicalName: slot.activityNode.canonicalName,
              category: slot.activityNode.category,
              subcategory: slot.activityNode.subcategory ?? null,
              neighborhood: slot.activityNode.neighborhood ?? null,
              priceLevel: slot.activityNode.priceLevel ?? null,
              primaryImageUrl: slot.activityNode.primaryImageUrl ?? null,
              descriptionShort: slot.activityNode.descriptionShort ?? null,
              latitude: slot.activityNode.latitude,
              longitude: slot.activityNode.longitude,
            }
          : null,
      });
    }

    return NextResponse.json({
      trip: tripPreview,
      slotsByDay,
      legs: trip.legs.map((leg: (typeof trip.legs)[number]) => ({
        position: leg.position,
        city: leg.city,
        country: leg.country,
        destination: leg.destination,
        timezone: leg.timezone,
        startDate: leg.startDate.toISOString(),
        endDate: leg.endDate.toISOString(),
      })),
      sharedAt: tokenRecord.createdAt.toISOString(),
    });
  } catch (err) {
    console.error(`[GET /api/shared/${params.token}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
