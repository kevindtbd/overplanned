/**
 * Tests for useCardViewTracker hook.
 *
 * Verifies:
 * - IntersectionObserver observe/unobserve lifecycle
 * - Cleanup on unmount
 * - Ref callback handles element swap (detach old, attach new)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCardViewTracker } from "../useCardViewTracker";

// Mock impressionTracker
const mockObserve = vi.fn();
const mockUnobserve = vi.fn();

vi.mock("@/lib/events/impressions", () => ({
  impressionTracker: {
    observe: (...args: unknown[]) => mockObserve(...args),
    unobserve: (...args: unknown[]) => mockUnobserve(...args),
  },
}));

const ACTIVITY_NODE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const TRIP_ID = "b2c3d4e5-f6a7-8901-bcde-f12345678901";

describe("useCardViewTracker", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("calls impressionTracker.observe when ref is attached to an element", () => {
    const { result } = renderHook(() =>
      useCardViewTracker({
        activityNodeId: ACTIVITY_NODE_ID,
        position: 3,
        tripId: TRIP_ID,
      })
    );

    const el = document.createElement("article");

    act(() => {
      result.current.ref(el);
    });

    expect(mockObserve).toHaveBeenCalledOnce();
    expect(mockObserve).toHaveBeenCalledWith(el, {
      activityNodeId: ACTIVITY_NODE_ID,
      position: 3,
      tripId: TRIP_ID,
    });
  });

  it("calls impressionTracker.unobserve when ref is detached (null)", () => {
    const { result } = renderHook(() =>
      useCardViewTracker({
        activityNodeId: ACTIVITY_NODE_ID,
        position: 0,
        tripId: TRIP_ID,
      })
    );

    const el = document.createElement("article");

    act(() => {
      result.current.ref(el);
    });

    act(() => {
      result.current.ref(null);
    });

    expect(mockUnobserve).toHaveBeenCalledOnce();
    expect(mockUnobserve).toHaveBeenCalledWith(el);
  });

  it("cleans up on unmount by calling unobserve", () => {
    const { result, unmount } = renderHook(() =>
      useCardViewTracker({
        activityNodeId: ACTIVITY_NODE_ID,
        position: 1,
        tripId: TRIP_ID,
      })
    );

    const el = document.createElement("article");

    act(() => {
      result.current.ref(el);
    });

    unmount();

    expect(mockUnobserve).toHaveBeenCalledOnce();
    expect(mockUnobserve).toHaveBeenCalledWith(el);
  });

  it("handles element swap: unobserves old, observes new", () => {
    const { result } = renderHook(() =>
      useCardViewTracker({
        activityNodeId: ACTIVITY_NODE_ID,
        position: 2,
        tripId: TRIP_ID,
      })
    );

    const el1 = document.createElement("article");
    const el2 = document.createElement("div");

    act(() => {
      result.current.ref(el1);
    });

    expect(mockObserve).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.ref(el2);
    });

    // Should have unobserved el1 and observed el2
    expect(mockUnobserve).toHaveBeenCalledWith(el1);
    expect(mockObserve).toHaveBeenCalledTimes(2);
    expect(mockObserve).toHaveBeenLastCalledWith(el2, {
      activityNodeId: ACTIVITY_NODE_ID,
      position: 2,
      tripId: TRIP_ID,
    });
  });

  it("does not call unobserve if no element was ever attached", () => {
    const { unmount } = renderHook(() =>
      useCardViewTracker({
        activityNodeId: ACTIVITY_NODE_ID,
        position: 0,
        tripId: TRIP_ID,
      })
    );

    unmount();

    expect(mockUnobserve).not.toHaveBeenCalled();
  });
});
