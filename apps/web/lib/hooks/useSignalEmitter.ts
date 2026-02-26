"use client";

/**
 * useSignalEmitter -- dual-write hook for behavioral signal capture.
 *
 * Every user interaction produces two writes:
 * 1. BehavioralSignal via POST /api/signals/behavioral (IMMEDIATE for explicit signals)
 * 2. RawEvent via eventEmitter.emit() (BUFFERED, batched every 5s)
 *
 * The hook auto-populates signalValue from SIGNAL_HIERARCHY if not provided,
 * and auto-attaches tripId + tripPhase from the options.
 *
 * Usage:
 *   const { emitSignal } = useSignalEmitter({ tripId, tripPhase: "active" });
 *   emitSignal({
 *     signalType: "slot_confirm",
 *     slotId: "abc-123",
 *     activityNodeId: "def-456",
 *     rawAction: "confirm_button_tap",
 *   });
 */

import { useCallback, useRef } from "react";
import { eventEmitter } from "@/lib/events/event-emitter";
import { SIGNAL_HIERARCHY } from "@/lib/events/signal-hierarchy";
import type { EventType, IntentClass } from "@/lib/events/types";

export type TripPhase = "pre_trip" | "active" | "post_trip";

export interface UseSignalEmitterOptions {
  tripId: string;
  tripPhase: TripPhase;
}

export interface EmitSignalParams {
  signalType: string;
  slotId?: string;
  activityNodeId?: string;
  rawAction: string;
  /** Auto-derived from SIGNAL_HIERARCHY if not provided */
  signalValue?: number;
  payload?: Record<string, unknown>;
}

/** Explicit signal types that write to /api/signals/behavioral immediately */
const IMMEDIATE_SIGNAL_TYPES = new Set([
  "slot_confirm",
  "slot_skip",
  "slot_swap",
  "slot_complete",
  "slot_moved",
  "pivot_accepted",
  "pivot_rejected",
  "post_loved",
  "post_disliked",
]);

/**
 * Maps signal types to their intent class for the RawEvent write.
 * Defaults to "explicit" for known action signals, "implicit" for observation signals.
 */
function deriveIntentClass(signalType: string): IntentClass {
  if (
    signalType.startsWith("slot_") ||
    signalType.startsWith("pivot_") ||
    signalType.startsWith("post_") ||
    signalType.startsWith("discover_")
  ) {
    return "explicit";
  }
  return "implicit";
}

/**
 * Maps known signal types to EventType values for the RawEvent.
 * Falls back to the signalType string directly for types not in the union.
 */
function toEventType(signalType: string): EventType {
  // These are the EventType union members that map directly
  const directMap: Record<string, EventType> = {
    slot_confirm: "slot_confirm",
    slot_skip: "slot_skip",
    slot_complete: "slot_lock",
    slot_view: "card_impression",
    slot_tap: "card_tap",
    slot_dwell: "card_dwell",
  };
  return directMap[signalType] ?? (signalType as EventType);
}

export function useSignalEmitter(options: UseSignalEmitterOptions) {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const emitSignal = useCallback((params: EmitSignalParams) => {
    const { tripId, tripPhase } = optionsRef.current;
    const {
      signalType,
      slotId,
      activityNodeId,
      rawAction,
      payload,
    } = params;

    // Resolve signal value: explicit param > hierarchy lookup > 0
    const signalValue =
      params.signalValue ?? SIGNAL_HIERARCHY[signalType] ?? 0;

    // --- Write 1: BehavioralSignal (immediate for explicit signals) ---
    if (IMMEDIATE_SIGNAL_TYPES.has(signalType)) {
      fetch("/api/signals/behavioral", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tripId,
          slotId: slotId ?? null,
          activityNodeId: activityNodeId ?? null,
          signalType,
          signalValue,
          tripPhase,
          rawAction,
        }),
        // keepalive so the request survives navigation
        keepalive: true,
      }).catch((err) => {
        console.warn("[useSignalEmitter] BehavioralSignal write failed:", err);
      });
    }

    // --- Write 2: RawEvent (buffered via eventEmitter) ---
    eventEmitter.emit({
      eventType: toEventType(signalType),
      intentClass: deriveIntentClass(signalType),
      tripId,
      slotId,
      activityNodeId,
      payload: {
        signalType,
        signalValue,
        tripPhase,
        rawAction,
        ...payload,
      },
    });
  }, []);

  return { emitSignal };
}
