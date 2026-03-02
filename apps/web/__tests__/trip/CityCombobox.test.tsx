/**
 * Component tests for CityCombobox — city search with launch cities + freeform resolve.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { CityCombobox } from "@/components/trip/CityCombobox";

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  vi.resetAllMocks();
});

function renderCombobox(overrides: Partial<Parameters<typeof CityCombobox>[0]> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <CityCombobox value={null} onChange={onChange} {...overrides} />
  );
  return { onChange, ...utils };
}

describe("CityCombobox", () => {
  it("renders with default placeholder", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Search cities...");
  });

  it("shows filtered LAUNCH_CITIES on typing", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "ben" } });

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(screen.getByText("Bend")).toBeInTheDocument();
  });

  it("filters by state abbreviation", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "CO" } });

    const options = screen.getAllByRole("option");
    // Denver, Durango, Fort Collins, Telluride — all CO cities
    expect(options.length).toBeGreaterThanOrEqual(4);
  });

  it("filters by destination string", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Portland, ME" } });

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
  });

  it("selects a city from suggestions and calls onChange", () => {
    const { onChange } = renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "ben" } });

    const option = screen.getByText("Bend");
    fireEvent.mouseDown(option.closest("[role='option']")!);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        slug: "bend",
        city: "Bend",
        state: "OR",
        timezone: "America/Los_Angeles",
        destination: "Bend, OR",
      })
    );
  });

  it("shows all LAUNCH_CITIES when focused with empty query", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.focus(input);

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(30);
  });

  it("renders both Portland cities without duplicate key warnings", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Portland" } });

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(2);

    // No React duplicate key warning
    const keyWarnings = consoleSpy.mock.calls.filter((args) =>
      String(args[0]).includes("key")
    );
    expect(keyWarnings).toHaveLength(0);
    consoleSpy.mockRestore();
  });

  it("selects Portland OR when its option is clicked", () => {
    const { onChange } = renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Portland" } });

    // Find the OR option — it comes first in the list
    const options = screen.getAllByRole("option");
    fireEvent.mouseDown(options[0]);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ slug: "portland", state: "OR" })
    );
  });

  it("selects Portland ME when its option is clicked", () => {
    const { onChange } = renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Portland" } });

    const options = screen.getAllByRole("option");
    fireEvent.mouseDown(options[1]);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ slug: "portland-me", state: "ME" })
    );
  });

  it("shows freeform option when no matches", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Hanoi" } });

    // No listbox options should exist
    expect(screen.queryAllByRole("option")).toHaveLength(0);

    // Freeform button should appear
    expect(
      screen.getByRole("button", { name: /Hanoi/ })
    ).toBeInTheDocument();
  });

  it("resolves freeform city via API on mouseDown", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          city: "Hanoi",
          country: "Vietnam",
          timezone: "Asia/Ho_Chi_Minh",
          destination: "Hanoi, Vietnam",
        }),
    });

    const { onChange } = renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Hanoi" } });

    const freeformBtn = screen.getByRole("button", { name: /Hanoi/ });
    fireEvent.mouseDown(freeformBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/cities/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city: "Hanoi" }),
      });
    });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith({
        city: "Hanoi",
        country: "Vietnam",
        timezone: "Asia/Ho_Chi_Minh",
        destination: "Hanoi, Vietnam",
      });
    });
  });

  it("shows error on API failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ error: "Internal server error" }),
    });

    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "Hanoi" } });

    const freeformBtn = screen.getByRole("button", { name: /Hanoi/ });
    fireEvent.mouseDown(freeformBtn);

    await waitFor(() => {
      expect(screen.getByText("Internal server error")).toBeInTheDocument();
    });
  });
});
