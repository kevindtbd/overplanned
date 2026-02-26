/**
 * RawEvent type definitions for behavioral signal capture.
 *
 * intentClass determines how the signal was generated:
 * - explicit: user deliberately acted (tap, confirm, skip)
 * - implicit: passive behavior captured (scroll, dwell, impression)
 * - contextual: environment-derived (time of day, location, device)
 */

export type IntentClass = "explicit" | "implicit" | "contextual";

export type EventType =
  | "card_impression"
  | "card_tap"
  | "slot_confirm"
  | "slot_skip"
  | "slot_lock"
  | "slot_moved"
  | "slot_swap"
  | "slot_complete"
  | "screen_view"
  | "tab_switch"
  | "scroll_depth"
  | "card_dwell"
  | "discover_swipe_right"
  | "discover_swipe_left"
  | "discover_shortlist"
  | "pivot_accepted"
  | "pivot_rejected";

export interface RawEvent {
  /** UUID v4 — client-generated for deduplication */
  clientEventId: string;
  /** UUID v4 — stable for the app session lifetime */
  sessionId: string;
  /** ISO 8601 timestamp */
  timestamp: string;
  /** How the signal was generated */
  intentClass: IntentClass;
  /** Discriminated event type */
  eventType: EventType;
  /** Associated trip, if any */
  tripId?: string;
  /** Associated itinerary slot, if any */
  slotId?: string;
  /** Associated activity node, if any */
  activityNodeId?: string;
  /** Freeform payload — shape depends on eventType */
  payload: Record<string, unknown>;
}

/** Payload shape for card_impression events */
export interface CardImpressionPayload {
  activityNodeId: string;
  /** 0-indexed position in the list/feed */
  position: number;
  /** How long the card was in the viewport, in milliseconds */
  viewportDurationMs: number;
}

/** Payload shape for card_tap events */
export interface CardTapPayload {
  activityNodeId: string;
  position: number;
  /** Where the tap originated from */
  source: "feed" | "map" | "search" | "recommendation";
}

/** Payload shape for slot_confirm / slot_skip / slot_lock events */
export interface SlotActionPayload {
  slotId: string;
  activityNodeId: string;
  /** Day index within the trip */
  dayIndex: number;
  /** Time slot label, e.g. "morning", "14:00" */
  timeSlot: string;
}

/** Payload shape for screen_view events */
export interface ScreenViewPayload {
  screenName: string;
  /** Previous screen for navigation flow tracking */
  referrer?: string;
}

/** Payload shape for tab_switch events */
export interface TabSwitchPayload {
  fromTab: string;
  toTab: string;
}

/** Payload shape for scroll_depth events */
export interface ScrollDepthPayload {
  /** Percentage of scrollable area reached (0-100) */
  maxDepthPercent: number;
  screenName: string;
}

/** Payload shape for card_dwell events */
export interface CardDwellPayload {
  activityNodeId: string;
  position: number;
  /** Total dwell time in milliseconds */
  dwellMs: number;
}

/** Batch request shape for the /events/batch endpoint */
export interface EventBatchRequest {
  sessionId: string;
  events: RawEvent[];
}

/** Response from the batch endpoint */
export interface EventBatchResponse {
  accepted: number;
  duplicates: number;
}
