/**
 * Impression tracking via IntersectionObserver.
 *
 * Tracks when activity cards enter/exit the viewport and records:
 * - activityNodeId
 * - position in the list
 * - viewport duration (dwell time)
 *
 * Dual-threshold system:
 * - DWELL_THRESHOLD_MS (300ms): emits card_dwell for "actually looked at"
 * - IMPRESSION_THRESHOLD_MS (1000ms): emits card_impression for ML impression_count
 *
 * Safety caps on client-provided timing:
 * - MIN_DWELL_MS (100ms): below = noise, discarded at accumulation time
 * - MAX_DWELL_MS (60000ms): above = likely tab-in-background, capped
 *
 * Usage:
 *   import { impressionTracker } from "@/lib/events";
 *
 *   // In a component ref callback:
 *   impressionTracker.observe(element, {
 *     activityNodeId: "abc-123",
 *     position: 0,
 *     tripId: "trip-456",
 *   });
 *
 *   // At decision time (confirm/skip a slot):
 *   const dwellData = impressionTracker.flushDwellData();
 *   // => { "abc-123": 4200, "def-456": 1800 }
 *
 *   // Cleanup:
 *   impressionTracker.unobserve(element);
 */

import { eventEmitter } from "./event-emitter";

export interface ImpressionMeta {
  activityNodeId: string;
  position: number;
  tripId?: string;
}

interface TrackedEntry {
  meta: ImpressionMeta;
  /** Timestamp when the card entered the viewport */
  enterTime: number | null;
  /** Accumulated dwell time across multiple intersections */
  totalDwellMs: number;
  /** Whether the card_dwell event has already been emitted */
  dwellEmitted: boolean;
  /** Whether the card_impression event has already been emitted */
  impressionEmitted: boolean;
}

/** Minimum time in viewport (ms) before a dwell event fires */
export const DWELL_THRESHOLD_MS = 300;

/** Minimum time in viewport (ms) before an impression counts */
export const IMPRESSION_THRESHOLD_MS = 1_000;

/** Minimum intersection ratio to count as "visible" */
const INTERSECTION_THRESHOLD = 0.5;

/** Dwell increments below this are noise — discarded */
export const MIN_DWELL_MS = 100;

/** Dwell time capped at this per element — anything above is tab-in-background */
export const MAX_DWELL_MS = 60_000;

/** Exported for testing — consumers should use the singleton `impressionTracker` */
export class ImpressionTracker {
  private observer: IntersectionObserver | null = null;
  private tracked: Map<Element, TrackedEntry> = new Map();
  /**
   * Accumulates total dwell time per activityNodeId across all observe/unobserve
   * cycles. Consumed (and reset) by flushDwellData().
   */
  private dwellAccumulator: Map<string, number> = new Map();

  constructor() {
    if (typeof window !== "undefined" && "IntersectionObserver" in window) {
      this.observer = new IntersectionObserver(
        this.handleIntersections,
        {
          threshold: INTERSECTION_THRESHOLD,
        }
      );
    }
  }

  /** Start observing an element for viewport impressions. */
  observe(element: Element, meta: ImpressionMeta): void {
    if (!this.observer) return;

    this.tracked.set(element, {
      meta,
      enterTime: null,
      totalDwellMs: 0,
      dwellEmitted: false,
      impressionEmitted: false,
    });

    this.observer.observe(element);
  }

  /** Stop observing an element. Emits final dwell/impression events if thresholds met. */
  unobserve(element: Element): void {
    if (!this.observer) return;

    const entry = this.tracked.get(element);
    if (entry) {
      // If currently visible, finalize the dwell
      if (entry.enterTime !== null) {
        this.accumulateDwell(entry, Date.now() - entry.enterTime);
        entry.enterTime = null;
      }

      // Emit dwell event if threshold met and not yet emitted
      if (!entry.dwellEmitted && entry.totalDwellMs >= DWELL_THRESHOLD_MS) {
        entry.dwellEmitted = true;
        eventEmitter.emit({
          eventType: "card_dwell",
          intentClass: "implicit",
          activityNodeId: entry.meta.activityNodeId,
          tripId: entry.meta.tripId,
          payload: {
            activityNodeId: entry.meta.activityNodeId,
            position: entry.meta.position,
            dwellMs: entry.totalDwellMs,
          },
        });
      }

      // Emit impression if threshold met and not yet emitted
      if (
        !entry.impressionEmitted &&
        entry.totalDwellMs >= IMPRESSION_THRESHOLD_MS
      ) {
        entry.impressionEmitted = true;
        eventEmitter.emit({
          eventType: "card_impression",
          intentClass: "implicit",
          activityNodeId: entry.meta.activityNodeId,
          tripId: entry.meta.tripId,
          payload: {
            activityNodeId: entry.meta.activityNodeId,
            position: entry.meta.position,
            viewportDurationMs: entry.totalDwellMs,
          },
        });
      }

      this.tracked.delete(element);
    }

    this.observer.unobserve(element);
  }

  /** Disconnect the observer entirely and emit remaining dwell events. */
  destroy(): void {
    if (!this.observer) return;

    // Finalize all tracked entries — collect keys first to avoid mutation during iteration
    const elements = Array.from(this.tracked.keys());
    for (const element of elements) {
      this.unobserve(element);
    }

    this.observer.disconnect();
    this.observer = null;
  }

  /**
   * Returns accumulated dwell time per activityNodeId.
   * Does NOT reset the accumulator — use flushDwellData() for that.
   */
  getDwellData(): Map<string, number> {
    // Snapshot current in-flight entries into a temporary copy
    const snapshot = new Map(this.dwellAccumulator);

    for (const entry of this.tracked.values()) {
      if (entry.enterTime !== null) {
        const inflight = this.clampDwell(Date.now() - entry.enterTime);
        if (inflight >= MIN_DWELL_MS) {
          const id = entry.meta.activityNodeId;
          const current = snapshot.get(id) ?? 0;
          snapshot.set(id, Math.min(current + inflight, MAX_DWELL_MS));
        }
      }
    }

    return snapshot;
  }

  /**
   * Returns dwell time for a specific tracked element, or null if not tracked.
   * Includes in-flight time (currently visible but not yet exited).
   */
  getDwellDataForElement(element: HTMLElement): number | null {
    const entry = this.tracked.get(element);
    if (!entry) return null;

    let total = entry.totalDwellMs;
    if (entry.enterTime !== null) {
      total += this.clampDwell(Date.now() - entry.enterTime);
    }
    return Math.min(total, MAX_DWELL_MS);
  }

  /**
   * Returns all accumulated dwell data as a plain object and resets the accumulator.
   * Used at "decision time" to bundle view_durations_ms into RankingEvent payloads.
   */
  flushDwellData(): Record<string, number> {
    // Include in-flight entries in the flush
    const data = this.getDwellData();
    const result: Record<string, number> = {};
    for (const [id, ms] of data) {
      result[id] = ms;
    }

    // Reset the accumulator
    this.dwellAccumulator.clear();

    return result;
  }

  // -- Private --

  /**
   * Clamp a raw dwell increment to the valid range.
   * Returns 0 if below MIN_DWELL_MS (noise).
   */
  private clampDwell(rawMs: number): number {
    if (rawMs < MIN_DWELL_MS) return 0;
    return Math.min(rawMs, MAX_DWELL_MS);
  }

  /**
   * Accumulate a dwell increment onto a tracked entry, applying safety caps.
   * Also updates the dwellAccumulator for getDwellData/flushDwellData.
   */
  private accumulateDwell(entry: TrackedEntry, rawMs: number): void {
    const clamped = this.clampDwell(rawMs);
    if (clamped === 0) return;

    // Cap total per-element at MAX_DWELL_MS
    const headroom = MAX_DWELL_MS - entry.totalDwellMs;
    if (headroom <= 0) return;

    const added = Math.min(clamped, headroom);
    entry.totalDwellMs += added;

    // Update the accumulator
    const id = entry.meta.activityNodeId;
    const current = this.dwellAccumulator.get(id) ?? 0;
    this.dwellAccumulator.set(id, Math.min(current + added, MAX_DWELL_MS));
  }

  private handleIntersections = (entries: IntersectionObserverEntry[]): void => {
    const now = Date.now();

    for (const ioEntry of entries) {
      const tracked = this.tracked.get(ioEntry.target);
      if (!tracked) continue;

      if (ioEntry.isIntersecting) {
        // Card entered viewport
        tracked.enterTime = now;
      } else if (tracked.enterTime !== null) {
        // Card left viewport — accumulate dwell time
        const rawMs = now - tracked.enterTime;
        this.accumulateDwell(tracked, rawMs);
        tracked.enterTime = null;

        // Emit dwell event if threshold met and not yet emitted
        if (
          !tracked.dwellEmitted &&
          tracked.totalDwellMs >= DWELL_THRESHOLD_MS
        ) {
          tracked.dwellEmitted = true;

          eventEmitter.emit({
            eventType: "card_dwell",
            intentClass: "implicit",
            activityNodeId: tracked.meta.activityNodeId,
            tripId: tracked.meta.tripId,
            payload: {
              activityNodeId: tracked.meta.activityNodeId,
              position: tracked.meta.position,
              dwellMs: tracked.totalDwellMs,
            },
          });
        }

        // Emit impression if threshold met and not yet emitted
        if (
          !tracked.impressionEmitted &&
          tracked.totalDwellMs >= IMPRESSION_THRESHOLD_MS
        ) {
          tracked.impressionEmitted = true;

          eventEmitter.emit({
            eventType: "card_impression",
            intentClass: "implicit",
            activityNodeId: tracked.meta.activityNodeId,
            tripId: tracked.meta.tripId,
            payload: {
              activityNodeId: tracked.meta.activityNodeId,
              position: tracked.meta.position,
              viewportDurationMs: tracked.totalDwellMs,
            },
          });
        }
      }
    }
  };
}

/** Singleton instance */
export const impressionTracker = new ImpressionTracker();
