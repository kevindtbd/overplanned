/**
 * Impression tracking via IntersectionObserver.
 *
 * Tracks when activity cards enter/exit the viewport and records:
 * - activityNodeId
 * - position in the list
 * - viewport duration (dwell time)
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
 *   // Cleanup:
 *   impressionTracker.unobserve(element);
 */

import { eventEmitter } from "./event-emitter";

interface ImpressionMeta {
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
  /** Whether the card_impression event has already been emitted */
  impressionEmitted: boolean;
}

/** Minimum time in viewport (ms) before an impression counts */
const IMPRESSION_THRESHOLD_MS = 1_000;

/** Minimum intersection ratio to count as "visible" */
const INTERSECTION_THRESHOLD = 0.5;

class ImpressionTracker {
  private observer: IntersectionObserver | null = null;
  private tracked: Map<Element, TrackedEntry> = new Map();

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
      impressionEmitted: false,
    });

    this.observer.observe(element);
  }

  /** Stop observing an element. Emits a card_dwell event with total time. */
  unobserve(element: Element): void {
    if (!this.observer) return;

    const entry = this.tracked.get(element);
    if (entry) {
      // If currently visible, finalize the dwell
      if (entry.enterTime !== null) {
        entry.totalDwellMs += Date.now() - entry.enterTime;
        entry.enterTime = null;
      }

      // Emit dwell event if any meaningful time was accumulated
      if (entry.totalDwellMs > 0) {
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

      this.tracked.delete(element);
    }

    this.observer.unobserve(element);
  }

  /** Disconnect the observer entirely and emit remaining dwell events. */
  destroy(): void {
    if (!this.observer) return;

    // Finalize all tracked entries
    for (const [element] of this.tracked) {
      this.unobserve(element);
    }

    this.observer.disconnect();
    this.observer = null;
  }

  // -- Private --

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
        const dwellMs = now - tracked.enterTime;
        tracked.totalDwellMs += dwellMs;
        tracked.enterTime = null;

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
