/**
 * Component tests for CityCombobox — city search with launch cities + freeform resolve.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { CityCombobox, type CityData } from "@/components/trip/CityCombobox";

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

    fireEvent.change(input, { target: { value: "tok" } });

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(screen.getByText("Tokyo")).toBeInTheDocument();
  });

  it("filters by country name", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "japan" } });

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(screen.getByText("Tokyo")).toBeInTheDocument();
    expect(screen.getByText("Kyoto")).toBeInTheDocument();
    expect(screen.getByText("Osaka")).toBeInTheDocument();
  });

  it("selects a city from suggestions and calls onChange", () => {
    const { onChange } = renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.change(input, { target: { value: "tok" } });

    const option = screen.getByText("Tokyo");
    fireEvent.mouseDown(option.closest("[role='option']")!);

    expect(onChange).toHaveBeenCalledWith({
      city: "Tokyo",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Tokyo, Japan",
    });
  });

  it("shows all LAUNCH_CITIES when focused with empty query", () => {
    renderCombobox();
    const input = screen.getByRole("combobox");

    fireEvent.focus(input);

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(13);
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
