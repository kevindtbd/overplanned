import type { PrismaClient } from "@prisma/client";
import type { TransactionClient } from "@/lib/prisma";

/**
 * Signal categories used for persona dimension aggregation.
 * Maps rawAction prefixes / signalType values to persona dimensions.
 */
const DIMENSION_SIGNAL_PATTERNS: Record<string, RegExp[]> = {
  adventure_score: [
    /outdoor/i,
    /adventure/i,
    /hiking/i,
    /active/i,
    /sport/i,
    /trek/i,
  ],
  budget_sensitivity: [
    /price/i,
    /budget/i,
    /cheap/i,
    /expensive/i,
    /cost/i,
    /deal/i,
  ],
  food_focus: [
    /food/i,
    /dining/i,
    /restaurant/i,
    /eat/i,
    /meal/i,
    /ramen/i,
    /cafe/i,
    /brunch/i,
  ],
  culture_interest: [
    /culture/i,
    /museum/i,
    /temple/i,
    /shrine/i,
    /gallery/i,
    /heritage/i,
    /historic/i,
  ],
  nature_preference: [
    /nature/i,
    /park/i,
    /garden/i,
    /beach/i,
    /mountain/i,
    /forest/i,
    /lake/i,
  ],
};

/**
 * Query recent BehavioralSignals for a user and aggregate into persona dimensions.
 *
 * Each dimension is a fraction (0-1) representing how many of the user's recent
 * signals match that dimension's patterns. Returns {} for new users with no signal history.
 *
 * These dimensions are denormalized into RankingEvent.personaDimensions for ML training data,
 * so models can correlate persona state at generation time with ranking outcomes.
 */
export async function getPersonaSnapshot(
  db: PrismaClient | TransactionClient,
  userId: string,
): Promise<Record<string, number>> {
  const signals = await db.behavioralSignal.findMany({
    where: {
      userId,
      source: "user_behavioral",
    },
    select: {
      rawAction: true,
      signalType: true,
    },
    orderBy: { createdAt: "desc" },
    take: 200, // recent window — enough for meaningful aggregation
  });

  if (signals.length === 0) {
    return {};
  }

  const dimensions: Record<string, number> = {};

  for (const [dimension, patterns] of Object.entries(DIMENSION_SIGNAL_PATTERNS)) {
    let matchCount = 0;
    for (const signal of signals) {
      const text = `${signal.rawAction} ${signal.signalType}`;
      const matches = patterns.some((p) => p.test(text));
      if (matches) matchCount++;
    }
    dimensions[dimension] = Math.round((matchCount / signals.length) * 1000) / 1000;
  }

  // Only include non-zero dimensions
  const nonZero: Record<string, number> = {};
  for (const [key, value] of Object.entries(dimensions)) {
    if (value > 0) {
      nonZero[key] = value;
    }
  }

  return nonZero;
}
