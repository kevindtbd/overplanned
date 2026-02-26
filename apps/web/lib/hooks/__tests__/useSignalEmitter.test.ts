/**
 * Tests for useSignalEmitter hook.
 *
 * Verifies:
 * - Dual-write: both BehavioralSignal endpoint and eventEmitter are called
 * - Auto signal value derivation from SIGNAL_HIERARCHY
 * - Fire-and-forget: fetch errors do not throw
 * - tripPhase is attached to both writes
 * - Only explicit signals go to /api/signals/behavioral immediately
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSignalEmitter } from "../useSignalEmitter";

// Mock eventEmitter
const mockEmit = vi.fn();
vi.mock("@/lib/events/event-emitter", () => ({
  eventEmitter: {
    emit: (...args: unknown[]) => mockEmit(...args),
  },
}));

// Mock fetch
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Suppress console.warn for fire-and-forget error tests
const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

const TRIP_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

describe("useSignalEmitter", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockFetch.mockResolvedValue({ ok: true });
  });

  it("dual-writes to both BehavioralSignal endpoint and eventEmitter for explicit signals", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_confirm",
        slotId: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        activityNodeId: "c3d4e5f6-a7b8-9012-cdef-123456789012",
        rawAction: "confirm_button_tap",
      });
    });

    // BehavioralSignal: immediate fetch call
    expect(mockFetch).toHaveBeenCalledOnce();
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/signals/behavioral",
      expect.objectContaining({
        method: "POST",
        keepalive: true,
      })
    );

    const fetchBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(fetchBody).toMatchObject({
      tripId: TRIP_ID,
      slotId: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      activityNodeId: "c3d4e5f6-a7b8-9012-cdef-123456789012",
      signalType: "slot_confirm",
      signalValue: 1.0,
      tripPhase: "active",
      rawAction: "confirm_button_tap",
    });

    // RawEvent: buffered via eventEmitter
    expect(mockEmit).toHaveBeenCalledOnce();
    expect(mockEmit).toHaveBeenCalledWith(
      expect.objectContaining({
        eventType: "slot_confirm",
        intentClass: "explicit",
        tripId: TRIP_ID,
        slotId: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        activityNodeId: "c3d4e5f6-a7b8-9012-cdef-123456789012",
      })
    );
  });

  it("auto-derives signalValue from SIGNAL_HIERARCHY when not provided", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "pre_trip" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_skip",
        slotId: "d4e5f6a7-b8c9-0123-defa-234567890123",
        rawAction: "skip_button_tap",
      });
    });

    const fetchBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    // slot_skip in SIGNAL_HIERARCHY = -0.7
    expect(fetchBody.signalValue).toBe(-0.7);
  });

  it("uses explicit signalValue when provided, overriding hierarchy", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_confirm",
        rawAction: "confirm_button_tap",
        signalValue: 0.5,
      });
    });

    const fetchBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(fetchBody.signalValue).toBe(0.5);
  });

  it("fire-and-forget: fetch rejection does not throw", () => {
    mockFetch.mockRejectedValueOnce(new Error("Network down"));

    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    // Should not throw
    expect(() => {
      act(() => {
        result.current.emitSignal({
          signalType: "slot_confirm",
          rawAction: "confirm_button_tap",
        });
      });
    }).not.toThrow();

    expect(mockFetch).toHaveBeenCalledOnce();
  });

  it("attaches tripPhase to both writes", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "post_trip" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "post_loved",
        rawAction: "loved_button_tap",
      });
    });

    // BehavioralSignal write
    const fetchBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(fetchBody.tripPhase).toBe("post_trip");

    // RawEvent write
    const emitPayload = mockEmit.mock.calls[0][0].payload;
    expect(emitPayload.tripPhase).toBe("post_trip");
  });

  it("does NOT call /api/signals/behavioral for non-immediate signal types", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_view",
        rawAction: "card_visible",
      });
    });

    // No fetch call for implicit signals
    expect(mockFetch).not.toHaveBeenCalled();

    // But eventEmitter still gets it
    expect(mockEmit).toHaveBeenCalledOnce();
  });

  it("defaults signalValue to 0 for unknown signal types", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_view",
        rawAction: "card_visible",
      });
    });

    // slot_view is in hierarchy (0.1), but "unknown_type" would be 0
    const emitPayload = mockEmit.mock.calls[0][0].payload;
    expect(emitPayload.signalValue).toBe(0.1);
  });

  it("includes custom payload in RawEvent write", () => {
    const { result } = renderHook(() =>
      useSignalEmitter({ tripId: TRIP_ID, tripPhase: "active" })
    );

    act(() => {
      result.current.emitSignal({
        signalType: "slot_confirm",
        rawAction: "confirm_button_tap",
        payload: {
          original_activity_id: "e5f6a7b8-c9d0-1234-efab-345678901234",
          slot_index: 2,
          day_number: 3,
        },
      });
    });

    const emitPayload = mockEmit.mock.calls[0][0].payload;
    expect(emitPayload.original_activity_id).toBe("e5f6a7b8-c9d0-1234-efab-345678901234");
    expect(emitPayload.slot_index).toBe(2);
    expect(emitPayload.day_number).toBe(3);
  });

  // Cleanup check
  afterAll(() => {
    warnSpy.mockRestore();
  });
});
