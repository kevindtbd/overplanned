/**
 * Component tests for DisplayPreferences
 * Tests loading/error states, radio pill rendering, selection triggers PATCH,
 * optimistic revert on failure, and all 5 field groups.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DisplayPreferences } from "@/components/settings/DisplayPreferences";

const DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetchSuccess(data: Record<string, string> = DEFAULTS) {
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

describe("DisplayPreferences — loading and error states", () => {
  it("renders skeleton during fetch, then content after load", async () => {
    mockFetchSuccess();
    const { container } = render(<DisplayPreferences />);

    // Skeleton has animate-pulse
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, skeleton disappears and fieldsets appear
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    // All 5 legends should be visible
    expect(screen.getByText("Distance")).toBeInTheDocument();
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("Date format")).toBeInTheDocument();
    expect(screen.getByText("Time format")).toBeInTheDocument();
    expect(screen.getByText("Theme")).toBeInTheDocument();
  });

  it("shows error message when fetch fails", async () => {
    mockFetchError();
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load display preferences.")
      ).toBeInTheDocument();
    });
  });
});

describe("DisplayPreferences — all 5 groups render", () => {
  it("renders radio pills for each field group", async () => {
    mockFetchSuccess();
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });

    // Distance: mi, km
    expect(screen.getByLabelText("mi")).toBeInTheDocument();
    expect(screen.getByLabelText("km")).toBeInTheDocument();

    // Temperature: F, C
    expect(screen.getByLabelText("F")).toBeInTheDocument();
    expect(screen.getByLabelText("C")).toBeInTheDocument();

    // Date format
    expect(screen.getByLabelText("MM/DD/YYYY")).toBeInTheDocument();
    expect(screen.getByLabelText("DD/MM/YYYY")).toBeInTheDocument();
    expect(screen.getByLabelText("YYYY-MM-DD")).toBeInTheDocument();

    // Time format
    expect(screen.getByLabelText("12h")).toBeInTheDocument();
    expect(screen.getByLabelText("24h")).toBeInTheDocument();

    // Theme
    expect(screen.getByLabelText("Light")).toBeInTheDocument();
    expect(screen.getByLabelText("Dark")).toBeInTheDocument();
    expect(screen.getByLabelText("System")).toBeInTheDocument();
  });

  it("shows current selection as checked", async () => {
    mockFetchSuccess({ ...DEFAULTS, theme: "dark" });
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Theme")).toBeInTheDocument();
    });

    const darkRadio = screen.getByLabelText("Dark") as HTMLInputElement;
    expect(darkRadio.checked).toBe(true);

    const systemRadio = screen.getByLabelText("System") as HTMLInputElement;
    expect(systemRadio.checked).toBe(false);
  });
});

describe("DisplayPreferences — selection triggers PATCH", () => {
  const user = userEvent.setup();

  it("selecting a radio pill triggers PATCH with correct field", async () => {
    mockFetchSuccess();
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Theme")).toBeInTheDocument();
    });

    // Mock the PATCH response
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...DEFAULTS, theme: "dark" }),
    });

    await user.click(screen.getByLabelText("Dark"));

    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
      // Second call is the PATCH (first was GET on mount)
      const patchCall = (calls as [string, RequestInit][]).find(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      expect(patchCall![0]).toBe("/api/settings/display");
      expect(JSON.parse(patchCall![1].body as string)).toEqual({ theme: "dark" });
    });
  });
});

describe("DisplayPreferences — revert on PATCH failure", () => {
  const user = userEvent.setup();

  it("reverts selection on PATCH failure", async () => {
    mockFetchSuccess(); // initial GET
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Theme")).toBeInTheDocument();
    });

    // Mock PATCH to fail
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    await user.click(screen.getByLabelText("Dark"));

    // Should revert to "system" after PATCH fails
    await waitFor(() => {
      const systemRadio = screen.getByLabelText("System") as HTMLInputElement;
      expect(systemRadio.checked).toBe(true);
    });
  });
});

describe("DisplayPreferences — network error does not crash", () => {
  const user = userEvent.setup();

  it("handles network error gracefully during PATCH", async () => {
    mockFetchSuccess();
    render(<DisplayPreferences />);

    await waitFor(() => {
      expect(screen.getByText("Distance")).toBeInTheDocument();
    });

    // Mock PATCH to throw network error
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("Network error")
    );

    await user.click(screen.getByLabelText("km"));

    // Should revert to "mi" after error
    await waitFor(() => {
      const miRadio = screen.getByLabelText("mi") as HTMLInputElement;
      expect(miRadio.checked).toBe(true);
    });
  });
});
