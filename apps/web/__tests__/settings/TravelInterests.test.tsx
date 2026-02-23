/**
 * Component tests for TravelInterests
 * Tests loading/error states, disclosure groups, chip toggle with debounce,
 * textarea blur save, and revert on failure.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TravelInterests } from "@/components/settings/TravelInterests";

const API_DEFAULTS = {
  vibePreferences: [],
  travelStyleNote: null,
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function mockFetchSuccess(data: Record<string, unknown> = API_DEFAULTS) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: true,
    json: async () => data,
  });
}

function mockFetchError() {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: false,
    status: 500,
  });
}

describe("TravelInterests — loading and error states", () => {
  it("renders skeleton during fetch, then content after load", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelInterests />);

    // Skeleton has animate-pulse
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, skeleton disappears
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    // Heading should be visible
    expect(screen.getByText("Travel Interests")).toBeInTheDocument();
  });

  it("shows error message when fetch fails", async () => {
    mockFetchError();
    render(<TravelInterests />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load travel interests.")
      ).toBeInTheDocument();
    });
  });
});

describe("TravelInterests — all groups visible", () => {
  it("shows all vibe groups and their chips after load", async () => {
    mockFetchSuccess();
    render(<TravelInterests />);

    await waitFor(() => {
      expect(screen.getByText("Discovery Style")).toBeInTheDocument();
    });

    // All groups should be visible (no disclosure)
    expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
    expect(screen.getByText("High energy")).toBeInTheDocument();
    expect(screen.getByText("Slow burn")).toBeInTheDocument();

    expect(screen.getByText("Discovery Style")).toBeInTheDocument();
    expect(screen.getByText("Hidden gems")).toBeInTheDocument();
    expect(screen.getByText("Locals only")).toBeInTheDocument();

    expect(screen.getByText("Food & Drink")).toBeInTheDocument();
    expect(screen.getByText("Street food")).toBeInTheDocument();

    expect(screen.getByText("Activity Type")).toBeInTheDocument();
    expect(screen.getByText("Nature immersive")).toBeInTheDocument();

    expect(screen.getByText("Social & Time")).toBeInTheDocument();
    expect(screen.getByText("Late night")).toBeInTheDocument();
  });
});

describe("TravelInterests — chip toggle with debounce", () => {
  it("chip click triggers debounced PATCH after 500ms", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetchSuccess();

    await act(async () => {
      render(<TravelInterests />);
    });

    // The fetch promise resolves via microtasks with shouldAdvanceTime
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(screen.getByText("Hidden gems")).toBeInTheDocument();

    // Mock the PATCH response before clicking
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ vibePreferences: ["hidden-gem"] }),
    });

    // Click a chip
    await act(async () => {
      fireEvent.click(screen.getByText("Hidden gems"));
    });

    // PATCH should NOT have fired yet (only the initial GET)
    const patchCallsBefore = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: [string, RequestInit]) => c[1]?.method === "PATCH"
    );
    expect(patchCallsBefore.length).toBe(0);

    // Advance past debounce
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    const patchCallsAfter = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: [string, RequestInit]) => c[1]?.method === "PATCH"
    );
    expect(patchCallsAfter.length).toBe(1);
    expect(patchCallsAfter[0][0]).toBe("/api/settings/preferences");
    expect(JSON.parse(patchCallsAfter[0][1].body as string)).toEqual({
      vibePreferences: ["hidden-gem"],
    });
  });

  it("rapid clicks within 500ms result in exactly 1 PATCH", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetchSuccess();

    await act(async () => {
      render(<TravelInterests />);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(screen.getByText("Hidden gems")).toBeInTheDocument();

    // Mock the PATCH response
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        vibePreferences: ["hidden-gem", "locals-only", "iconic-worth-it"],
      }),
    });

    // Click three chips rapidly
    await act(async () => {
      fireEvent.click(screen.getByText("Hidden gems"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
      fireEvent.click(screen.getByText("Locals only"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
      fireEvent.click(screen.getByText("Iconic & worth it"));
    });

    // Advance past debounce
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    const patchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: [string, RequestInit]) => c[1]?.method === "PATCH"
    );
    // Only 1 PATCH should fire (the last debounced one)
    expect(patchCalls.length).toBe(1);
  });
});

describe("TravelInterests — textarea blur save", () => {
  it("textarea blur triggers PATCH with travelStyleNote", async () => {
    mockFetchSuccess();
    const user = userEvent.setup();
    render(<TravelInterests />);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(
          "I always hunt for the best coffee spot in every city..."
        )
      ).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(
      "I always hunt for the best coffee spot in every city..."
    );

    // Mock the PATCH response
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ travelStyleNote: "Love morning markets" }),
    });

    await user.type(textarea, "Love morning markets");
    await user.tab(); // trigger blur

    await waitFor(() => {
      const patchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
        (c: [string, RequestInit]) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBeGreaterThanOrEqual(1);
      const lastPatch = patchCalls[patchCalls.length - 1];
      const body = JSON.parse(lastPatch[1].body as string);
      expect(body).toHaveProperty("travelStyleNote");
      expect(body.travelStyleNote).toBe("Love morning markets");
    });
  });
});

describe("TravelInterests — revert on failure", () => {
  it("reverts vibes on PATCH failure", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetchSuccess({ ...API_DEFAULTS, vibePreferences: [] });

    await act(async () => {
      render(<TravelInterests />);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(screen.getByText("Hidden gems")).toBeInTheDocument();

    // Mock PATCH failure
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    // Click to toggle on
    await act(async () => {
      fireEvent.click(screen.getByText("Hidden gems"));
    });

    // Advance past debounce + let the PATCH promise settle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    // After PATCH failure, the checkbox should be unchecked (reverted)
    const checkbox = screen.getByRole("checkbox", { name: "Hidden gems" }) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
  });
});
