/**
 * Tests for TemplateStep — preset selection and negative space signal emission.
 *
 * Verifies:
 * - preset_selected emitted when user selects a preset
 * - preset_hovered emitted after 500ms hover on a preset
 * - preset_hovered NOT emitted if user leaves before 500ms
 * - preset_all_skipped emitted via emitPresetAllSkipped helper
 * - allPresetsShown included in all payloads
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { TemplateStep, ALL_PRESET_IDS, emitPresetAllSkipped } from "@/app/onboarding/components/TemplateStep";

// ---------------------------------------------------------------------------
// Mock eventEmitter
// ---------------------------------------------------------------------------

const { mockEmit } = vi.hoisted(() => ({
  mockEmit: vi.fn(),
}));

vi.mock("@/lib/events/event-emitter", () => ({
  eventEmitter: {
    emit: mockEmit,
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderTemplateStep(selected: string | null = null, onSelect = vi.fn()) {
  return render(<TemplateStep selected={selected} onSelect={onSelect} />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TemplateStep", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("preset_selected signal", () => {
    it("emits preset_selected with presetId and allPresetsShown when user clicks a preset", () => {
      const onSelect = vi.fn();
      renderTemplateStep(null, onSelect);

      fireEvent.click(screen.getByText("Foodie Weekend"));

      expect(mockEmit).toHaveBeenCalledOnce();
      expect(mockEmit).toHaveBeenCalledWith(
        expect.objectContaining({
          eventType: "preset_selected",
          intentClass: "explicit",
          payload: expect.objectContaining({
            presetId: "foodie-weekend",
            allPresetsShown: ALL_PRESET_IDS,
          }),
        })
      );
    });

    it("calls onSelect with the template id when clicking an unselected preset", () => {
      const onSelect = vi.fn();
      renderTemplateStep(null, onSelect);

      fireEvent.click(screen.getByText("Adventure"));

      expect(onSelect).toHaveBeenCalledWith("adventure");
    });

    it("calls onSelect with null (deselect) when clicking the already-selected preset", () => {
      const onSelect = vi.fn();
      renderTemplateStep("culture-deep-dive", onSelect);

      fireEvent.click(screen.getByText("Culture Deep Dive"));

      expect(onSelect).toHaveBeenCalledWith(null);
    });

    it("does NOT emit preset_selected when deselecting a preset", () => {
      const onSelect = vi.fn();
      renderTemplateStep("chill", onSelect);

      fireEvent.click(screen.getByText("Chill"));

      expect(mockEmit).not.toHaveBeenCalled();
    });

    it("includes all 8 preset ids in allPresetsShown", () => {
      renderTemplateStep(null);

      fireEvent.click(screen.getByText("Night Owl"));

      const call = mockEmit.mock.calls[0][0];
      expect(call.payload.allPresetsShown).toHaveLength(8);
      expect(call.payload.allPresetsShown).toContain("foodie-weekend");
      expect(call.payload.allPresetsShown).toContain("weekend-sprint");
    });
  });

  describe("preset_hovered signal", () => {
    it("emits preset_hovered after 500ms of hovering a preset", () => {
      renderTemplateStep(null);

      fireEvent.mouseEnter(screen.getByText("Local Immersion").closest("button")!);

      // Should not emit yet
      expect(mockEmit).not.toHaveBeenCalled();

      // Advance timers past the 500ms threshold
      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(mockEmit).toHaveBeenCalledOnce();
      expect(mockEmit).toHaveBeenCalledWith(
        expect.objectContaining({
          eventType: "preset_hovered",
          intentClass: "implicit",
          payload: expect.objectContaining({
            presetId: "local-immersion",
            allPresetsShown: ALL_PRESET_IDS,
          }),
        })
      );
    });

    it("does NOT emit preset_hovered if user leaves before 500ms", () => {
      renderTemplateStep(null);

      const btn = screen.getByText("First Timer").closest("button")!;
      fireEvent.mouseEnter(btn);

      act(() => {
        vi.advanceTimersByTime(300);
      });

      fireEvent.mouseLeave(btn);

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(mockEmit).not.toHaveBeenCalled();
    });

    it("emits preset_hovered exactly once even if timer fires after mouseLeave clears it", () => {
      renderTemplateStep(null);

      const btn = screen.getByText("Weekend Sprint").closest("button")!;
      fireEvent.mouseEnter(btn);

      act(() => {
        vi.advanceTimersByTime(600);
      });

      // Only one emit — the hover signal
      expect(mockEmit).toHaveBeenCalledOnce();
      expect(mockEmit.mock.calls[0][0].eventType).toBe("preset_hovered");
    });
  });

  describe("preset_all_skipped signal", () => {
    it("emits preset_all_skipped with allPresetsShown via emitPresetAllSkipped helper", () => {
      emitPresetAllSkipped();

      expect(mockEmit).toHaveBeenCalledOnce();
      expect(mockEmit).toHaveBeenCalledWith(
        expect.objectContaining({
          eventType: "preset_all_skipped",
          intentClass: "explicit",
          payload: expect.objectContaining({
            allPresetsShown: ALL_PRESET_IDS,
          }),
        })
      );
    });

    it("allPresetsShown in preset_all_skipped contains all 8 presets", () => {
      emitPresetAllSkipped();

      const call = mockEmit.mock.calls[0][0];
      expect(call.payload.allPresetsShown).toHaveLength(8);
    });
  });

  describe("ALL_PRESET_IDS export", () => {
    it("exports the correct preset ids in order", () => {
      expect(ALL_PRESET_IDS).toEqual([
        "foodie-weekend",
        "culture-deep-dive",
        "adventure",
        "chill",
        "night-owl",
        "local-immersion",
        "first-timer",
        "weekend-sprint",
      ]);
    });
  });
});
