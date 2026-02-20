/**
 * EventEmitter service — buffers behavioral events in memory and
 * flushes them to the backend in batches.
 *
 * Usage:
 *   import { eventEmitter } from "@/lib/events";
 *   eventEmitter.emit({ eventType: "card_tap", ... });
 *
 * The emitter auto-flushes every 5 seconds and on page navigation.
 * Each event gets a clientEventId (UUID) for server-side dedup.
 */

import { v4 as uuidv4 } from "uuid";
import type { RawEvent, IntentClass, EventType, EventBatchRequest } from "./types";

const FLUSH_INTERVAL_MS = 5_000;
const BATCH_ENDPOINT = "/api/events/batch";

interface EmitParams {
  eventType: EventType;
  intentClass: IntentClass;
  tripId?: string;
  slotId?: string;
  activityNodeId?: string;
  payload?: Record<string, unknown>;
}

class EventEmitterService {
  private sessionId: string;
  private buffer: RawEvent[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private isFlushing = false;

  constructor() {
    this.sessionId = uuidv4();
  }

  /** Start the auto-flush interval and bind navigation listeners. */
  start(): void {
    if (this.flushTimer) return;

    this.flushTimer = setInterval(() => {
      this.flush();
    }, FLUSH_INTERVAL_MS);

    if (typeof window !== "undefined") {
      window.addEventListener("beforeunload", this.handleUnload);
      window.addEventListener("visibilitychange", this.handleVisibility);
    }
  }

  /** Stop the auto-flush and unbind listeners. */
  stop(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }

    if (typeof window !== "undefined") {
      window.removeEventListener("beforeunload", this.handleUnload);
      window.removeEventListener("visibilitychange", this.handleVisibility);
    }

    // Final flush on stop
    this.flush();
  }

  /** Get the current session ID. */
  getSessionId(): string {
    return this.sessionId;
  }

  /** Push a new event into the buffer. */
  emit(params: EmitParams): void {
    const event: RawEvent = {
      clientEventId: uuidv4(),
      sessionId: this.sessionId,
      timestamp: new Date().toISOString(),
      intentClass: params.intentClass,
      eventType: params.eventType,
      tripId: params.tripId,
      slotId: params.slotId,
      activityNodeId: params.activityNodeId,
      payload: params.payload ?? {},
    };

    this.buffer.push(event);
  }

  /** Flush buffered events to the backend. */
  async flush(): Promise<void> {
    if (this.isFlushing || this.buffer.length === 0) return;

    this.isFlushing = true;
    const batch = this.buffer.splice(0, this.buffer.length);

    const body: EventBatchRequest = {
      sessionId: this.sessionId,
      events: batch,
    };

    try {
      const res = await fetch(BATCH_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        // Use keepalive so the request survives page unload
        keepalive: true,
      });

      if (!res.ok) {
        // Put events back if the request failed
        this.buffer.unshift(...batch);
        console.error(`[EventEmitter] Flush failed: ${res.status}`);
      }
    } catch (err) {
      // Network error — put events back for retry
      this.buffer.unshift(...batch);
      console.error("[EventEmitter] Flush error:", err);
    } finally {
      this.isFlushing = false;
    }
  }

  /** Flush on navigation via the Navigation API or visibilitychange. */
  flushOnNavigation(): void {
    this.flush();
  }

  /** Return the current buffer size (useful for testing/debugging). */
  get bufferSize(): number {
    return this.buffer.length;
  }

  // -- Private handlers --

  private handleUnload = (): void => {
    // Use sendBeacon for reliability during page unload
    if (this.buffer.length === 0) return;

    const body: EventBatchRequest = {
      sessionId: this.sessionId,
      events: this.buffer.splice(0, this.buffer.length),
    };

    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(
        BATCH_ENDPOINT,
        new Blob([JSON.stringify(body)], { type: "application/json" })
      );
    }
  };

  private handleVisibility = (): void => {
    if (document.visibilityState === "hidden") {
      this.flush();
    }
  };
}

/** Singleton instance — import this from components */
export const eventEmitter = new EventEmitterService();
