import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  ImpressionTracker,
  DWELL_THRESHOLD_MS,
  IMPRESSION_THRESHOLD_MS,
  MIN_DWELL_MS,
  MAX_DWELL_MS,
} from "@/lib/events/impressions";
import type { ImpressionMeta } from "@/lib/events/impressions";
import { eventEmitter } from "@/lib/events/event-emitter";

vi.mock("@/lib/events/event-emitter", () => ({
  eventEmitter: {
    emit: vi.fn(),
  },
}));

// -- IntersectionObserver mock --

type IOCallback = (entries: IntersectionObserverEntry[]) => void;
let ioCallback: IOCallback;

const mockObserve = vi.fn();
const mockUnobserve = vi.fn();
const mockDisconnect = vi.fn();

class MockIntersectionObserver {
  constructor(cb: IOCallback) {
    ioCallback = cb;
  }
  observe = mockObserve;
  unobserve = mockUnobserve;
  disconnect = mockDisconnect;
}

vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

function triggerIntersection(target: Element, isIntersecting: boolean) {
  ioCallback([
    {
      target,
      isIntersecting,
      intersectionRatio: isIntersecting ? 0.6 : 0,
    } as unknown as IntersectionObserverEntry,
  ]);
}

function makeMeta(overrides?: Partial<ImpressionMeta>): ImpressionMeta {
  return {
    activityNodeId: "activity-1",
    position: 0,
    tripId: "trip-1",
    ...overrides,
  };
}

describe("ImpressionTracker", () => {
  let tracker: ImpressionTracker;
  const emitMock = vi.mocked(eventEmitter.emit);

  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetAllMocks();
    tracker = new ImpressionTracker();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ---------------------------------------------------------------
  // Dual threshold tests
  // ---------------------------------------------------------------

  describe("dual thresholds", () => {
    it("emits card_dwell but NOT card_impression for 500ms visibility", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(500);
      triggerIntersection(el, false);

      const dwellCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell"
      );
      const impressionCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_impression"
      );

      expect(dwellCalls).toHaveLength(1);
      expect(dwellCalls[0][0].payload.dwellMs).toBe(500);
      expect(impressionCalls).toHaveLength(0);
    });

    it("emits BOTH card_dwell and card_impression for 1500ms visibility", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(1500);
      triggerIntersection(el, false);

      const dwellCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell"
      );
      const impressionCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_impression"
      );

      expect(dwellCalls).toHaveLength(1);
      expect(dwellCalls[0][0].payload.dwellMs).toBe(1500);
      expect(impressionCalls).toHaveLength(1);
      expect(impressionCalls[0][0].payload.viewportDurationMs).toBe(1500);
    });

    it("does not emit any events for sub-100ms visibility (noise)", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(50);
      triggerIntersection(el, false);

      expect(emitMock).not.toHaveBeenCalled();
    });

    it("does not double-emit events on unobserve after already emitted", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(1500);
      triggerIntersection(el, false);

      const callCountAfterExit = emitMock.mock.calls.length;

      tracker.unobserve(el);
      expect(emitMock.mock.calls.length).toBe(callCountAfterExit);
    });

    it("emits dwell and impression on unobserve while still visible", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(2000);
      // Card is still visible when unobserve is called
      tracker.unobserve(el);

      const dwellCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell"
      );
      const impressionCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_impression"
      );

      expect(dwellCalls).toHaveLength(1);
      expect(impressionCalls).toHaveLength(1);
    });
  });

  // ---------------------------------------------------------------
  // getDwellData tests
  // ---------------------------------------------------------------

  describe("getDwellData()", () => {
    it("returns correct accumulated time after card exits viewport", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-a" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(2000);
      triggerIntersection(el, false);

      const data = tracker.getDwellData();
      expect(data.get("node-a")).toBe(2000);
    });

    it("includes in-flight time for currently visible elements", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-a" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(800);

      const data = tracker.getDwellData();
      expect(data.get("node-a")).toBe(800);
    });

    it("accumulates across multiple visibility periods", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-b" }));

      // First period: 400ms
      triggerIntersection(el, true);
      vi.advanceTimersByTime(400);
      triggerIntersection(el, false);

      // Second period: 600ms
      triggerIntersection(el, true);
      vi.advanceTimersByTime(600);
      triggerIntersection(el, false);

      const data = tracker.getDwellData();
      expect(data.get("node-b")).toBe(1000);
    });

    it("does not mutate accumulator (read-only snapshot)", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-c" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(500);
      triggerIntersection(el, false);

      const data1 = tracker.getDwellData();
      const data2 = tracker.getDwellData();
      expect(data1.get("node-c")).toBe(500);
      expect(data2.get("node-c")).toBe(500);
    });
  });

  // ---------------------------------------------------------------
  // getDwellDataForElement tests
  // ---------------------------------------------------------------

  describe("getDwellDataForElement()", () => {
    it("returns null for untracked elements", () => {
      const el = document.createElement("div");
      expect(tracker.getDwellDataForElement(el)).toBeNull();
    });

    it("returns accumulated dwell time including in-flight", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      triggerIntersection(el, true);
      vi.advanceTimersByTime(750);

      expect(tracker.getDwellDataForElement(el)).toBe(750);
    });

    it("returns dwell including prior completed + in-flight periods", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta());

      // First period: 300ms
      triggerIntersection(el, true);
      vi.advanceTimersByTime(300);
      triggerIntersection(el, false);

      // Second period: currently in-flight at 200ms
      triggerIntersection(el, true);
      vi.advanceTimersByTime(200);

      expect(tracker.getDwellDataForElement(el)).toBe(500);
    });
  });

  // ---------------------------------------------------------------
  // flushDwellData tests
  // ---------------------------------------------------------------

  describe("flushDwellData()", () => {
    it("returns accumulated data and resets the accumulator", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-x" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(2000);
      triggerIntersection(el, false);

      const flushed = tracker.flushDwellData();
      expect(flushed["node-x"]).toBe(2000);

      // After flush, accumulator is cleared for completed entries
      const dataAfter = tracker.getDwellData();
      expect(dataAfter.get("node-x")).toBeUndefined();
    });

    it("returns a plain object, not a Map", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-y" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(500);
      triggerIntersection(el, false);

      const flushed = tracker.flushDwellData();
      expect(typeof flushed).toBe("object");
      expect(flushed).not.toBeInstanceOf(Map);
      expect(flushed["node-y"]).toBe(500);
    });

    it("includes in-flight data at flush time", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-z" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(1000);
      // Card still visible at flush time

      const flushed = tracker.flushDwellData();
      expect(flushed["node-z"]).toBe(1000);
    });
  });

  // ---------------------------------------------------------------
  // Safety caps
  // ---------------------------------------------------------------

  describe("safety caps", () => {
    it("caps dwell at MAX_DWELL_MS (60s) for very long visibility", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-long" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(90_000);
      triggerIntersection(el, false);

      const data = tracker.getDwellData();
      expect(data.get("node-long")).toBe(MAX_DWELL_MS);
    });

    it("discards sub-MIN_DWELL_MS increments (noise)", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-noise" }));

      triggerIntersection(el, true);
      vi.advanceTimersByTime(50);
      triggerIntersection(el, false);

      const data = tracker.getDwellData();
      expect(data.get("node-noise")).toBeUndefined();
    });

    it("caps accumulated total across multiple periods", () => {
      const el = document.createElement("div");
      tracker.observe(el, makeMeta({ activityNodeId: "node-multi" }));

      // Three 25-second periods = 75s total, should cap at 60s
      for (let i = 0; i < 3; i++) {
        triggerIntersection(el, true);
        vi.advanceTimersByTime(25_000);
        triggerIntersection(el, false);
      }

      const data = tracker.getDwellData();
      expect(data.get("node-multi")).toBe(MAX_DWELL_MS);
    });
  });

  // ---------------------------------------------------------------
  // Multiple elements
  // ---------------------------------------------------------------

  describe("multiple elements tracked simultaneously", () => {
    it("tracks and emits events independently per element", () => {
      const el1 = document.createElement("div");
      const el2 = document.createElement("div");

      tracker.observe(el1, makeMeta({ activityNodeId: "a-1", position: 0 }));
      tracker.observe(el2, makeMeta({ activityNodeId: "a-2", position: 1 }));

      // el1 visible for 500ms (dwell only)
      triggerIntersection(el1, true);
      vi.advanceTimersByTime(500);
      triggerIntersection(el1, false);

      // el2 visible for 1500ms (both dwell and impression)
      triggerIntersection(el2, true);
      vi.advanceTimersByTime(1500);
      triggerIntersection(el2, false);

      // el1: 1 dwell, 0 impressions
      const el1Dwell = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell" && c[0].activityNodeId === "a-1"
      );
      expect(el1Dwell).toHaveLength(1);

      const el1Impression = emitMock.mock.calls.filter(
        (c) =>
          c[0].eventType === "card_impression" &&
          c[0].activityNodeId === "a-1"
      );
      expect(el1Impression).toHaveLength(0);

      // el2: 1 dwell + 1 impression
      const el2Dwell = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell" && c[0].activityNodeId === "a-2"
      );
      const el2Impression = emitMock.mock.calls.filter(
        (c) =>
          c[0].eventType === "card_impression" &&
          c[0].activityNodeId === "a-2"
      );
      expect(el2Dwell).toHaveLength(1);
      expect(el2Impression).toHaveLength(1);
    });

    it("getDwellData returns all tracked elements", () => {
      const el1 = document.createElement("div");
      const el2 = document.createElement("div");

      tracker.observe(el1, makeMeta({ activityNodeId: "x-1" }));
      tracker.observe(el2, makeMeta({ activityNodeId: "x-2" }));

      triggerIntersection(el1, true);
      vi.advanceTimersByTime(300);
      triggerIntersection(el1, false);

      triggerIntersection(el2, true);
      vi.advanceTimersByTime(700);
      triggerIntersection(el2, false);

      const data = tracker.getDwellData();
      expect(data.get("x-1")).toBe(300);
      expect(data.get("x-2")).toBe(700);
    });
  });

  // ---------------------------------------------------------------
  // destroy()
  // ---------------------------------------------------------------

  describe("destroy()", () => {
    it("finalizes all tracked entries and disconnects observer", () => {
      const el1 = document.createElement("div");
      const el2 = document.createElement("div");

      tracker.observe(el1, makeMeta({ activityNodeId: "d-1" }));
      tracker.observe(el2, makeMeta({ activityNodeId: "d-2" }));

      triggerIntersection(el1, true);
      triggerIntersection(el2, true);
      vi.advanceTimersByTime(2000);

      tracker.destroy();

      const dwellCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_dwell"
      );
      const impressionCalls = emitMock.mock.calls.filter(
        (c) => c[0].eventType === "card_impression"
      );
      expect(dwellCalls).toHaveLength(2);
      expect(impressionCalls).toHaveLength(2);
      expect(mockDisconnect).toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------
  // Threshold constant verification
  // ---------------------------------------------------------------

  describe("threshold constants", () => {
    it("has correct threshold values", () => {
      expect(DWELL_THRESHOLD_MS).toBe(300);
      expect(IMPRESSION_THRESHOLD_MS).toBe(1000);
      expect(MIN_DWELL_MS).toBe(100);
      expect(MAX_DWELL_MS).toBe(60_000);
    });
  });
});
