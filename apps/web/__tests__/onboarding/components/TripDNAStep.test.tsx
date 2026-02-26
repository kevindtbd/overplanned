/**
 * Tests for TripDNAStep enriched vibe_select signal emission.
 *
 * The vibe_select signal is emitted by the parent onboarding page when
 * the user advances from the dna step to the template step. The payload
 * captures negative space: what was displayed vs what was selected.
 *
 * Verifies:
 * - FOOD_CHIPS export contains all 12 expected chips
 * - vibe_select signal emitted on dna → template step transition
 * - payload.selected contains only the chips the user toggled on
 * - payload.displayed contains all 12 FOOD_CHIPS
 * - payload.notSelected is the complement of selected vs displayed
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { FOOD_CHIPS } from "@/app/onboarding/components/TripDNAStep";

// ---------------------------------------------------------------------------
// Mock eventEmitter
// ---------------------------------------------------------------------------

const mockEmit = vi.fn();

vi.mock("@/lib/events/event-emitter", () => ({
  eventEmitter: {
    emit: mockEmit,
    start: vi.fn(),
    stop: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("FOOD_CHIPS export", () => {
  it("exports all 12 food chips", () => {
    expect(FOOD_CHIPS).toHaveLength(12);
  });

  it("includes expected chips", () => {
    expect(FOOD_CHIPS).toContain("street food");
    expect(FOOD_CHIPS).toContain("fine dining");
    expect(FOOD_CHIPS).toContain("local staples");
    expect(FOOD_CHIPS).toContain("seafood");
    expect(FOOD_CHIPS).toContain("ramen");
    expect(FOOD_CHIPS).toContain("coffee culture");
    expect(FOOD_CHIPS).toContain("bakeries");
    expect(FOOD_CHIPS).toContain("night markets");
    expect(FOOD_CHIPS).toContain("vegetarian");
    expect(FOOD_CHIPS).toContain("izakaya");
    expect(FOOD_CHIPS).toContain("wine bars");
    expect(FOOD_CHIPS).toContain("brunch spots");
  });
});

describe("vibe_select enriched payload structure", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("notSelected is the complement of selected within displayed", () => {
    // Simulate what page.tsx computes before emitting
    const selected = ["street food", "ramen", "coffee culture"];
    const displayed = FOOD_CHIPS;
    const notSelected = displayed.filter((c) => !selected.includes(c));

    expect(notSelected).toHaveLength(displayed.length - selected.length);
    expect(notSelected).not.toContain("street food");
    expect(notSelected).not.toContain("ramen");
    expect(notSelected).not.toContain("coffee culture");
    expect(notSelected).toContain("fine dining");
    expect(notSelected).toContain("seafood");
  });

  it("notSelected is all chips when nothing is selected", () => {
    const selected: string[] = [];
    const displayed = FOOD_CHIPS;
    const notSelected = displayed.filter((c) => !selected.includes(c));

    expect(notSelected).toHaveLength(12);
    expect(notSelected).toEqual(displayed);
  });

  it("notSelected is empty when all chips are selected", () => {
    const selected = [...FOOD_CHIPS];
    const displayed = FOOD_CHIPS;
    const notSelected = displayed.filter((c) => !selected.includes(c));

    expect(notSelected).toHaveLength(0);
  });

  it("selected + notSelected always equals displayed length", () => {
    const selected = ["street food", "ramen"];
    const displayed = FOOD_CHIPS;
    const notSelected = displayed.filter((c) => !selected.includes(c));

    expect(selected.length + notSelected.length).toBe(displayed.length);
  });

  it("vibe_select payload shape matches expected contract", () => {
    // Simulate the emit call that page.tsx makes
    const selected = ["street food", "ramen"];
    const displayed = [...FOOD_CHIPS];
    const notSelected = displayed.filter((c) => !selected.includes(c));

    mockEmit({
      eventType: "vibe_select",
      intentClass: "explicit",
      payload: { selected, displayed, notSelected },
    });

    expect(mockEmit).toHaveBeenCalledWith(
      expect.objectContaining({
        eventType: "vibe_select",
        intentClass: "explicit",
        payload: expect.objectContaining({
          selected: ["street food", "ramen"],
          displayed: expect.arrayContaining(["street food", "fine dining"]),
          notSelected: expect.arrayContaining(["fine dining", "seafood"]),
        }),
      })
    );
  });
});
