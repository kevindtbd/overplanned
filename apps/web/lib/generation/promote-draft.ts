import { prisma } from "@/lib/prisma";
import { generateItinerary } from "./generate-itinerary";
import type { Pace, MorningPreference } from "./types";

interface PromotionResult {
  trip: unknown;
  generated: { slotsCreated: number; source: "seeded" | "empty" };
}

/**
 * Generates an itinerary after promoting a draft to planning.
 * Reads trip data, runs generation, re-fetches with slots if slots were created.
 * Returns the same { trip, generated } shape as POST /api/trips.
 */
export async function promoteDraftToPlanning(
  tripId: string,
  userId: string
): Promise<PromotionResult> {
  const trip = await prisma.trip.findUnique({
    where: { id: tripId },
    select: {
      city: true,
      country: true,
      startDate: true,
      endDate: true,
      presetTemplate: true,
      personaSeed: true,
    },
  });

  if (!trip) {
    throw new Error(`Trip ${tripId} not found`);
  }

  const personaSeed = trip.personaSeed as Record<string, unknown> | null;

  const seed = {
    pace: ((personaSeed?.pace as string) ?? "moderate") as Pace,
    morningPreference: ((personaSeed?.morningPreference as string) ?? "mid") as MorningPreference,
    foodPreferences: (personaSeed?.foodPreferences as string[]) ?? [],
    freeformVibes: personaSeed?.freeformVibes as string | undefined,
    template: trip.presetTemplate ?? (personaSeed?.template as string | undefined),
  };

  let generationResult: { slotsCreated: number; source: "seeded" | "empty" } = {
    slotsCreated: 0,
    source: "empty",
  };

  try {
    generationResult = await generateItinerary(
      tripId,
      userId,
      trip.city,
      trip.country,
      new Date(trip.startDate),
      new Date(trip.endDate),
      seed
    );
  } catch (err) {
    console.error("[promoteDraftToPlanning] Generation error:", err);
  }

  if (generationResult.slotsCreated > 0) {
    const fullTrip = await prisma.trip.findUnique({
      where: { id: tripId },
      include: {
        members: {
          select: { id: true, userId: true, role: true, status: true },
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
    return { trip: fullTrip, generated: generationResult };
  }

  const bareTrip = await prisma.trip.findUnique({
    where: { id: tripId },
    include: {
      members: {
        select: { id: true, userId: true, role: true, status: true },
      },
    },
  });

  return { trip: bareTrip, generated: generationResult };
}
