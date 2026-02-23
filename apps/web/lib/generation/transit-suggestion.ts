import Anthropic from "@anthropic-ai/sdk";
import { prisma } from "@/lib/prisma";

const client = new Anthropic();

interface TransitSuggestion {
  mode: string;
  durationMin: number;
  costHint: string;
}

const VALID_MODES = ["flight", "train", "shinkansen", "bus", "car", "ferry"];

/**
 * Suggest transit for each multi-leg trip. Fire-and-forget after trip creation.
 * Only processes legs with position > 0 (they arrive from the previous leg).
 * Skips legs that already have transitConfirmed = true.
 */
export async function suggestTransitForLegs(tripId: string): Promise<void> {
  const legs = await prisma.tripLeg.findMany({
    where: { tripId },
    orderBy: { position: "asc" },
    select: { id: true, position: true, city: true, country: true, transitConfirmed: true },
  });

  if (legs.length < 2) return;

  for (let i = 1; i < legs.length; i++) {
    const prevLeg = legs[i - 1];
    const currentLeg = legs[i];

    if (currentLeg.transitConfirmed) continue;

    try {
      const response = await client.messages.create({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 200,
        temperature: 0.2,
        system: "You are a travel logistics expert. Given two cities, suggest the most common tourist transit between them. Respond ONLY with valid JSON: {\"mode\": \"train|flight|shinkansen|bus|car|ferry\", \"durationMin\": number, \"costHint\": \"~$X\"}",
        messages: [{
          role: "user",
          content: `From ${prevLeg.city}, ${prevLeg.country} to ${currentLeg.city}, ${currentLeg.country}`,
        }],
      });

      const textContent = response.content.find(c => c.type === "text");
      if (!textContent || textContent.type !== "text") continue;

      const suggestion: TransitSuggestion = JSON.parse(textContent.text);

      // Validate mode against enum
      const mode = VALID_MODES.includes(suggestion.mode) ? suggestion.mode : null;
      if (!mode) continue;

      await prisma.tripLeg.update({
        where: { id: currentLeg.id },
        data: {
          transitMode: mode,
          transitDurationMin: Math.min(Math.max(0, Math.round(suggestion.durationMin)), 10080),
          transitCostHint: (suggestion.costHint ?? "").slice(0, 100),
        },
      });

      console.log(`[transit-suggestion] ${prevLeg.city} -> ${currentLeg.city}: ${mode} (${suggestion.durationMin}min)`);
    } catch (err) {
      console.error(`[transit-suggestion] Failed for leg ${currentLeg.id}:`, err);
      // Non-fatal — transit suggestions are optional
    }
  }
}
