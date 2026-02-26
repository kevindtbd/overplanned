/**
 * Removal reason taxonomy for pre-trip slot removal.
 *
 * When a user removes a slot from their itinerary during pre-trip planning,
 * these reasons capture WHY — giving signal quality context for BPR training.
 *
 * Signal weight semantics:
 *   -1.0  strong negative preference signal
 *   -0.6  moderate negative preference signal
 *    0.0  informational only — no negative preference implied
 */

export const REMOVAL_REASONS = [
  { id: "not_interested", label: "Not my thing", signalWeight: -1.0 },
  { id: "wrong_vibe", label: "Doesn't match the vibe", signalWeight: -0.6 },
  { id: "already_been", label: "I've been here before", signalWeight: 0.0 },
  { id: "too_far", label: "Too far away", signalWeight: 0.0 },
] as const;

export type RemovalReason = (typeof REMOVAL_REASONS)[number]["id"];

/** Default reason applied when the user dismisses without choosing. */
export const DEFAULT_REMOVAL_REASON: RemovalReason = "not_interested";
