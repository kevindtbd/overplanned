/**
 * Trip status utilities: auto-transition detection and state machine enforcement.
 */

export function shouldAutoTransition(status: string, startDate: Date): boolean {
  return status === "planning" && startDate <= new Date();
}

export const DELETABLE_STATUSES = ["draft", "planning"];

export const VALID_TRANSITIONS: Record<string, string[]> = {
  draft: ["planning", "archived"],
  planning: ["active", "archived"],
  active: ["completed", "archived"],
  completed: ["archived"],
  archived: [],
};

export function validateTransition(
  currentStatus: string,
  requestedStatus: string
): boolean {
  const allowed = VALID_TRANSITIONS[currentStatus];
  if (!allowed) return false;
  return allowed.includes(requestedStatus);
}

export const WRITABLE_BY_STATUS: Record<string, string[]> = {
  draft: ["name", "startDate", "endDate", "mode", "presetTemplate", "personaSeed", "status"],
  planning: ["name", "mode", "status", "planningProgress", "startDate", "endDate"],
  active: ["name", "status", "planningProgress"],
  completed: ["status"],
  archived: [],
};

export function getWritableFields(status: string): Set<string> {
  return new Set(WRITABLE_BY_STATUS[status] ?? []);
}

/**
 * Determine the current phase of a trip based on date boundaries.
 * Used to decide which signal types to emit (pre_trip_* vs active-phase signals).
 */
export function getTripPhase(trip: {
  startDate: Date | string | null;
  endDate: Date | string | null;
}): "pre_trip" | "active" | "post_trip" {
  const now = new Date();
  if (!trip.startDate || now < new Date(trip.startDate)) return "pre_trip";
  if (!trip.endDate || now <= new Date(trip.endDate)) return "active";
  return "post_trip";
}
