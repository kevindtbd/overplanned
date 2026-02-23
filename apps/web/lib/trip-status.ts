/**
 * Trip status utilities: auto-transition detection and state machine enforcement.
 */

export function shouldAutoTransition(status: string, startDate: Date): boolean {
  return status === "planning" && startDate <= new Date();
}

export const DELETABLE_STATUSES = ["draft"];

export const VALID_TRANSITIONS: Record<string, string[]> = {
  draft: ["planning"],
  planning: ["active"],
  active: ["completed"],
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
  planning: ["name", "status", "planningProgress", "startDate", "endDate"],
  active: ["name", "status", "planningProgress"],
  completed: ["status"],
  archived: [],
};

export function getWritableFields(status: string): Set<string> {
  return new Set(WRITABLE_BY_STATUS[status] ?? []);
}
