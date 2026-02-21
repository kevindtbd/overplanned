import { prisma } from "@/lib/prisma";
import { v4 as uuidv4 } from "uuid";
import { scoreNodes, selectNodes } from "./scoring";
import { placeSlots } from "./slot-placement";
import { enrichWithLLM } from "./llm-enrichment";
import type { PersonaSeed, PlacedSlot } from "./types";
import { PACE_SLOTS_PER_DAY, TEMPLATE_WEIGHTS } from "./types";

interface GenerationResult {
  slotsCreated: number;
  source: "seeded" | "empty";
}

/**
 * Generate an itinerary for a trip. Called synchronously after trip creation.
 * Returns the count of slots created.
 *
 * The LLM enrichment fires async (non-blocking) after slots are persisted.
 */
export async function generateItinerary(
  tripId: string,
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

  // Step 4: Create all slots in one transaction
  const slotRows = placedSlots.map((s) => ({
    id: uuidv4(),
    tripId,
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
