import Anthropic from "@anthropic-ai/sdk";
import { prisma } from "@/lib/prisma";
import type { PlacedSlot, PersonaSeed } from "./types";

const client = new Anthropic();

interface EnrichmentResult {
  reorder: { slotId: string; newSortOrder: number }[];
  hints: { slotId: string; hint: string }[];
}

/**
 * Async LLM enrichment — call after trip creation response is sent.
 * If this fails, the deterministic itinerary stands on its own.
 */
export async function enrichWithLLM(
  tripId: string,
  slots: { id: string; name: string; category: string; dayNumber: number; sortOrder: number; latitude?: number; longitude?: number }[],
  personaSeed: PersonaSeed,
  city: string,
): Promise<void> {
  try {
    const startTime = Date.now();

    // Build a compact slot summary for the prompt
    const slotSummary = slots.map(s => ({
      id: s.id,
      name: s.name,
      category: s.category,
      day: s.dayNumber,
      order: s.sortOrder,
      lat: s.latitude,
      lng: s.longitude,
    }));

    const prefsText = [
      `Pace: ${personaSeed.pace}`,
      `Morning: ${personaSeed.morningPreference}`,
      personaSeed.foodPreferences.length > 0 ? `Food: ${personaSeed.foodPreferences.join(", ")}` : null,
      personaSeed.freeformVibes ? `Vibes: ${personaSeed.freeformVibes}` : null,
      personaSeed.template ? `Template: ${personaSeed.template}` : null,
    ].filter(Boolean).join("\n");

    const response = await client.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 1500,
      temperature: 0.3,
      system: `You are a local travel expert for ${city}. Given a generated itinerary and traveler preferences, provide:
1. Reordering suggestions ONLY if a day's sequence involves unnecessary backtracking (check lat/lng proximity). Most of the time the order is fine — only suggest changes when clearly suboptimal.
2. A short narrative hint per slot (1 sentence, max 80 characters) explaining why this activity fits at this time or what makes it special.

Respond ONLY with valid JSON matching this schema:
{
  "reorder": [{"slotId": "...", "newSortOrder": 1}],
  "hints": [{"slotId": "...", "hint": "..."}]
}

If no reordering needed, return empty reorder array.`,
      messages: [
        {
          role: "user",
          content: `Traveler preferences:\n${prefsText}\n\nGenerated itinerary:\n${JSON.stringify(slotSummary, null, 2)}`,
        },
      ],
    });

    const latencyMs = Date.now() - startTime;
    const textContent = response.content.find(c => c.type === "text");
    if (!textContent || textContent.type !== "text") return;

    // Parse the JSON response
    let result: EnrichmentResult;
    try {
      result = JSON.parse(textContent.text);
    } catch {
      console.error("[llm-enrichment] Failed to parse LLM response");
      return;
    }

    // Apply reordering if any
    if (result.reorder && result.reorder.length > 0) {
      const updates = result.reorder.map(r =>
        prisma.itinerarySlot.update({
          where: { id: r.slotId },
          data: { sortOrder: r.newSortOrder },
        })
      );
      await prisma.$transaction(updates);
    }

    // Apply narrative hints — store in voteState JSON field
    if (result.hints && result.hints.length > 0) {
      const hintUpdates = result.hints.map(h =>
        prisma.itinerarySlot.update({
          where: { id: h.slotId },
          data: {
            voteState: { narrativeHint: h.hint.slice(0, 100) },
          },
        })
      );
      await prisma.$transaction(hintUpdates);
    }

    // Log the LLM call
    console.log(`[llm-enrichment] tripId=${tripId} latency=${latencyMs}ms hints=${result.hints?.length ?? 0} reorders=${result.reorder?.length ?? 0}`);

  } catch (err) {
    // Non-fatal — deterministic itinerary stands on its own
    console.error("[llm-enrichment] Failed:", err);
  }
}
