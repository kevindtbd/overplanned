/**
 * Trip leg utilities — pure functions for multi-city trip computations.
 * No database access, no side effects.
 */

interface LegDateRange {
  startDate: string | Date;
  endDate: string | Date;
}

interface LegForRoute {
  city: string;
  country: string;
  destination: string;
}

/**
 * Compute the number of activity days in a leg from its date range.
 * Returns at least 1 day.
 */
export function legDayCount(leg: LegDateRange): number {
  const start = new Date(leg.startDate);
  const end = new Date(leg.endDate);
  const diff = Math.ceil(
    (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
  );
  return Math.max(diff, 1);
}

/**
 * Convert a leg-relative day number to an absolute trip day number.
 * Legs must be sorted by position. legRelativeDay is 1-indexed.
 *
 * Example: 3 legs with 3, 2, 4 days respectively.
 * Leg 0 day 1 = absolute day 1
 * Leg 1 day 1 = absolute day 4
 * Leg 2 day 2 = absolute day 7
 */
export function computeAbsoluteDay(
  legs: (LegDateRange & { id: string })[],
  legId: string,
  legRelativeDay: number
): number {
  let absoluteDay = 0;
  for (const leg of legs) {
    if (leg.id === legId) {
      return absoluteDay + legRelativeDay;
    }
    absoluteDay += legDayCount(leg);
  }
  // Leg not found — return the relative day as-is
  return legRelativeDay;
}

/**
 * Build a route string for display: "Tokyo → Kyoto → Osaka"
 */
export function buildRouteString(legs: LegForRoute[]): string {
  if (legs.length === 0) return "";
  if (legs.length === 1) return legs[0].destination;
  return legs.map((l) => l.city).join(" → ");
}

/**
 * Auto-generate a trip name from legs and start date.
 *
 * Single city: "Tokyo Apr 2026"
 * Multi-city, same country: "Tokyo to Osaka Apr 2026"
 * Multi-country: "Japan & Thailand Apr 2026"
 */
export function autoTripName(
  legs: LegForRoute[],
  startDate: string | Date
): string {
  const date = new Date(startDate);
  const monthYear = date.toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  });

  if (legs.length === 0) return `Trip ${monthYear}`;

  if (legs.length === 1) {
    return `${legs[0].city} ${monthYear}`;
  }

  const countries = [...new Set(legs.map((l) => l.country))];
  if (countries.length === 1) {
    // Same country — use first and last city
    return `${legs[0].city} to ${legs[legs.length - 1].city} ${monthYear}`;
  }

  // Multiple countries
  if (countries.length === 2) {
    return `${countries[0]} & ${countries[1]} ${monthYear}`;
  }
  return `${countries[0]}, ${countries[1]} & more ${monthYear}`;
}
