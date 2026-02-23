/**
 * GET /api/settings/export
 * Auth: session required
 * Returns all user data as JSON download (GDPR right to portability).
 * Rate limit: 1 request per 10 minutes per user (in-memory).
 * Strips internal ML fields: signalValue, confidenceTier, payload.
 */

import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

const RATE_LIMIT_MS = 10 * 60 * 1000; // 10 minutes
const rateLimitMap = new Map<string, number>();

// Exposed for test reset only
export function _resetRateLimitForTest() {
  rateLimitMap.clear();
}

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // Rate limit check
  const lastExport = rateLimitMap.get(userId);
  if (lastExport && Date.now() - lastExport < RATE_LIMIT_MS) {
    return NextResponse.json(
      { error: "Please wait before requesting another export." },
      { status: 429 }
    );
  }

  const [
    user,
    preferences,
    notifications,
    consent,
    tripMembers,
    behavioralSignals,
    intentionSignals,
    rawEvents,
    personaDimensions,
    rankingEvents,
    backfillTrips,
  ] = await prisma.$transaction([
    prisma.user.findUniqueOrThrow({
      where: { id: userId },
      select: { name: true, email: true, createdAt: true, subscriptionTier: true },
    }),
    prisma.userPreference.findUnique({
      where: { userId },
      select: {
        dietary: true, mobility: true, languages: true, travelFrequency: true,
        vibePreferences: true, travelStyleNote: true,
        budgetComfort: true, spendingPriorities: true, accommodationTypes: true,
        transitModes: true, preferencesNote: true,
      },
    }),
    prisma.notificationPreference.findUnique({
      where: { userId },
      select: {
        tripReminders: true, morningBriefing: true, groupActivity: true,
        postTripPrompt: true, citySeeded: true, inspirationNudges: true, productUpdates: true,
        checkinReminder: true, preTripDaysBefore: true,
      },
    }),
    prisma.dataConsent.findUnique({
      where: { userId },
      select: { modelTraining: true, anonymizedResearch: true },
    }),
    prisma.tripMember.findMany({
      where: { userId, status: "joined" },
      select: {
        trip: {
          select: {
            name: true, destination: true, city: true, country: true,
            startDate: true, endDate: true, status: true, mode: true, createdAt: true,
            slots: {
              select: {
                dayNumber: true, slotType: true, status: true,
                activityNode: { select: { name: true, category: true } },
              },
            },
          },
        },
      },
    }),
    prisma.behavioralSignal.findMany({
      where: { userId },
      select: { signalType: true, rawAction: true, tripPhase: true, createdAt: true },
    }),
    prisma.intentionSignal.findMany({
      where: { userId },
      select: { intentionType: true, confidence: true, source: true, createdAt: true },
    }),
    prisma.rawEvent.findMany({
      where: { userId },
      select: { eventType: true, intentClass: true, createdAt: true },
    }),
    prisma.personaDimension.findMany({
      where: { userId },
      select: { dimension: true, value: true, confidence: true, createdAt: true },
    }),
    prisma.rankingEvent.findMany({
      where: { userId },
      select: {
        surface: true, selectedIds: true, createdAt: true,
      },
    }),
    prisma.backfillTrip.findMany({
      where: { userId },
      select: {
        city: true, country: true, startDate: true,
        venues: {
          select: { extractedName: true, extractedCategory: true },
        },
      },
    }),
  ]);

  // Record rate limit timestamp
  rateLimitMap.set(userId, Date.now());

  /* eslint-disable @typescript-eslint/no-explicit-any */
  const exportData = {
    exportedAt: new Date().toISOString(),
    profile: {
      name: user.name,
      email: user.email,
      createdAt: user.createdAt,
      subscriptionTier: user.subscriptionTier,
    },
    preferences: preferences ?? {
      dietary: [], mobility: [], languages: [], travelFrequency: null,
      vibePreferences: [], travelStyleNote: null,
      budgetComfort: null, spendingPriorities: [], accommodationTypes: [],
      transitModes: [], preferencesNote: null,
    },
    notifications: notifications ?? {
      tripReminders: true, morningBriefing: true, groupActivity: true,
      postTripPrompt: true, citySeeded: true, inspirationNudges: false, productUpdates: false,
      checkinReminder: false, preTripDaysBefore: 3,
    },
    consent: consent ?? { modelTraining: false, anonymizedResearch: false },
    trips: tripMembers.map((tm: any) => tm.trip),
    behavioralSignals,
    intentionSignals,
    rawEvents,
    personaDimensions: personaDimensions.map((pd: any) => ({
      dimensionName: pd.dimension,
      score: pd.value,
      confidence: pd.confidence,
      createdAt: pd.createdAt,
    })),
    rankingEvents: rankingEvents.map((re: any) => ({
      context: re.surface,
      selectedId: re.selectedIds[0] ?? null,
      alternativesCount: re.selectedIds.length,
      createdAt: re.createdAt,
    })),
    backfillTrips: backfillTrips.map((bt: any) => ({
      city: bt.city,
      country: bt.country,
      traveledAt: bt.startDate,
      venues: bt.venues.map((v: any) => ({
        name: v.extractedName,
        category: v.extractedCategory,
      })),
    })),
  };
  /* eslint-enable @typescript-eslint/no-explicit-any */

  const today = new Date().toISOString().split("T")[0];

  return new NextResponse(JSON.stringify(exportData, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="overplanned-export-${today}.json"`,
    },
  });
}
