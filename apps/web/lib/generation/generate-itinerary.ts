import { prisma } from "@/lib/prisma";
import { v4 as uuidv4 } from "uuid";
import { scoreNodes, selectNodes } from "./scoring";
import { placeSlots } from "./slot-placement";
import { enrichWithLLM } from "./llm-enrichment";
import { getPersonaSnapshot } from "./persona-snapshot";
import { getWeatherContext } from "./weather-context";
import type { PersonaSeed, PlacedSlot } from "./types";
import { PACE_SLOTS_PER_DAY, TEMPLATE_WEIGHTS } from "./types";

interface GenerationResult {
  slotsCreated: number;
  source: "seeded" | "empty";
}

/**
 * Generate an itinerary for a single trip leg. Called per-leg by generateTripItinerary.
 * Returns the count of slots created.
 *
 * The LLM enrichment fires async (non-blocking) after slots are persisted.
 */
export async function generateLegItinerary(
  tripId: string,
  tripLegId: string,
  userId: string,
  city: string,
  country: string,
  startDate: Date,
  endDate: Date,
  personaSeed: PersonaSeed,
): Promise<GenerationResult> {
  // Calculate trip duration
  const totalDays = Math.max(
    Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)),
    1
  );

  // Check if we have ActivityNodes for this city
  const nodeCount = await prisma.activityNode.count({
    where: { city, status: { not: "archived" } },
  });

  if (nodeCount === 0) {
    // Unseeded city — log the request for scraping queue
    console.log(`[generation] Unseeded city: ${city}, ${country} — requested by ${userId}`);
    // TODO: Write to CityRequest table when it exists
    // For now, return empty — LLM fallback will be added at launch
    return { slotsCreated: 0, source: "empty" };
  }

  // Fetch all non-archived nodes for the city with vibe tags
  const nodes = await prisma.activityNode.findMany({
    where: { city, status: { not: "archived" } },
    select: {
      id: true,
      name: true,
      category: true,
      latitude: true,
      longitude: true,
      neighborhood: true,
      descriptionShort: true,
      priceLevel: true,
      authorityScore: true,
      vibeTags: {
        where: { vibeTag: { isActive: true } },
        select: {
          vibeTag: { select: { slug: true, name: true } },
          score: true,
        },
      },
    },
  });

  // Calculate how many slots we need
  const templateConfig = personaSeed.template
    ? TEMPLATE_WEIGHTS[personaSeed.template] ?? null
    : null;
  const baseSlotsPerDay = PACE_SLOTS_PER_DAY[personaSeed.pace];
  const paceModifier = templateConfig?.paceModifier ?? 0;
  const slotsPerDay = Math.max(2, Math.min(7, baseSlotsPerDay + paceModifier));

  // Long trip adjustment
  let effectiveSlotsPerDay = slotsPerDay;
  if (totalDays > 7 && personaSeed.pace !== "packed") {
    effectiveSlotsPerDay = Math.max(2, slotsPerDay - 1);
  }

  const totalSlotsNeeded = effectiveSlotsPerDay * totalDays;

  // Step 1: Score nodes
  const scoredNodes = scoreNodes(nodes, personaSeed);

  // Step 2: Select with diversity constraints
  const selectedNodes = selectNodes(scoredNodes, totalSlotsNeeded);

  if (selectedNodes.length === 0) {
    return { slotsCreated: 0, source: "empty" };
  }

  // Step 3: Place into day/time slots
  const placedSlots = placeSlots(selectedNodes, totalDays, personaSeed, startDate);

  // Step 4: Create all slots + RankingEvent in one transaction
  const generationStartMs = performance.now();

  const slotRows = placedSlots.map((s) => ({
    id: uuidv4(),
    tripId,
    tripLegId,
    activityNodeId: s.nodeId,
    dayNumber: s.dayNumber,
    sortOrder: s.sortOrder,
    slotType: s.slotType as any,
    status: "proposed" as any,
    startTime: s.startTime,
    endTime: s.endTime,
    durationMinutes: s.durationMinutes,
    isLocked: false,
  }));

  // Gather context for RankingEvent denormalization
  const [persona, weatherCtx] = await Promise.all([
    getPersonaSnapshot(prisma, userId),
    Promise.resolve(getWeatherContext(city, startDate)),
  ]);

  // Build candidate pool: all node IDs that were scored (the full candidate set)
  const allCandidateIds = scoredNodes.map((n) => n.nodeId);
  // Ranked IDs: the selected nodes in score order (model output)
  const rankedIds = selectedNodes.map((n) => n.nodeId);
  // Selected IDs: what was actually placed into slots
  const selectedSlotNodeIds = placedSlots.map((s) => s.nodeId);

  const latencyMs = Math.round(performance.now() - generationStartMs);

  // Build per-day RankingEvent creates — one event per day in this generation batch.
  // Each event captures the full candidate set (for BPR negative sampling) and the
  // day-specific ranked/selected subsets.
  const dayNumbers = [...new Set(placedSlots.map((s) => s.dayNumber))];
  const rankingEventCreates = dayNumbers.map((dayNum) => {
    const daySlots = placedSlots.filter((s) => s.dayNumber === dayNum);
    const daySelectedIds = daySlots.map((s) => s.nodeId);
    // Day-specific ranking: nodes selected for this day in placement order
    const dayRankedIds = daySlots.map((s) => s.nodeId);

    return prisma.rankingEvent.create({
      data: {
        id: uuidv4(),
        userId,
        tripId,
        dayNumber: dayNum,
        modelName: "deterministic_scorer",
        modelVersion: "1.0.0",
        candidateIds: allCandidateIds,
        rankedIds: dayRankedIds,
        selectedIds: daySelectedIds,
        surface: "itinerary",
        latencyMs,
      },
    });
  });

  await prisma.$transaction([
    prisma.itinerarySlot.createMany({ data: slotRows }),
    prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId,
        signalType: "soft_positive" as any,
        signalValue: 1.0,
        tripPhase: "pre_trip" as any,
        rawAction: `itinerary_generated:${slotRows.length}_slots:${personaSeed.template ?? "no_template"}`,
      },
    }),
    ...rankingEventCreates,
  ]);

  // Step 5: Fire async LLM enrichment (non-blocking)
  // Build slot data for LLM
  const slotsForLLM = slotRows.map((row, i) => ({
    id: row.id,
    name: placedSlots[i].name,
    category: placedSlots[i].category,
    dayNumber: placedSlots[i].dayNumber,
    sortOrder: placedSlots[i].sortOrder,
    latitude: selectedNodes.find(n => n.nodeId === row.activityNodeId)?.latitude,
    longitude: selectedNodes.find(n => n.nodeId === row.activityNodeId)?.longitude,
  }));

  // Fire and forget — don't await
  enrichWithLLM(tripId, slotsForLLM, personaSeed, city).catch((err) => {
    console.error("[generation] LLM enrichment failed:", err);
  });

  return { slotsCreated: slotRows.length, source: "seeded" };
}

/**
 * Orchestrate itinerary generation across all legs of a trip.
 * Processes legs sequentially in position order.
 */
export async function generateTripItinerary(
  tripId: string,
  userId: string,
  personaSeed: PersonaSeed,
): Promise<{ totalSlotsCreated: number; legResults: { legId: string; city: string; slotsCreated: number; source: "seeded" | "empty" }[] }> {
  const legs = await prisma.tripLeg.findMany({
    where: { tripId },
    orderBy: { position: "asc" },
  });

  const legResults: { legId: string; city: string; slotsCreated: number; source: "seeded" | "empty" }[] = [];
  let totalSlotsCreated = 0;

  for (const leg of legs) {
    try {
      const result = await generateLegItinerary(
        tripId,
        leg.id,
        userId,
        leg.city,
        leg.country,
        new Date(leg.startDate),
        new Date(leg.endDate),
        personaSeed,
      );
      legResults.push({ legId: leg.id, city: leg.city, slotsCreated: result.slotsCreated, source: result.source });
      totalSlotsCreated += result.slotsCreated;
    } catch (err) {
      console.error(`[generateTripItinerary] Leg ${leg.id} (${leg.city}) failed:`, err);
      legResults.push({ legId: leg.id, city: leg.city, slotsCreated: 0, source: "empty" });
    }
  }

  return { totalSlotsCreated, legResults };
}
