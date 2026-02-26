/**
 * Signal hierarchy — maps signal types to their training value weights.
 *
 * Tier 1: Explicit actions (highest training value)
 * Tier 2: Strong implicit signals
 * Tier 3: Weak implicit signals
 *
 * Used by useSignalEmitter to auto-populate signalValue when not provided.
 */

export const SIGNAL_HIERARCHY: Record<string, number> = {
  // Tier 1: Explicit actions (highest training value)
  slot_confirm: 1.0,
  slot_complete: 1.0,
  post_loved: 1.0,
  post_disliked: -1.0,
  pivot_accepted: 0.9,
  pivot_rejected: -0.8,

  // Tier 2: Strong implicit
  discover_shortlist: 0.8,
  discover_swipe_right: 0.6,
  discover_swipe_left: -0.5,
  slot_skip: -0.7,
  slot_swap: -0.6,
  pre_trip_slot_removed: -0.7,
  pre_trip_slot_swap: -0.5,
  pre_trip_slot_added: 0.8,
  pre_trip_reorder: 0.3,
  slot_moved: 0.3,

  // Tier 3: Weak implicit
  slot_view: 0.1,
  slot_tap: 0.2,
  slot_dwell: 0.3,
  dwell_time: 0.2,
  return_visit: 0.4,
  considered_not_chosen: -0.2,
  soft_positive: 0.3,
};
