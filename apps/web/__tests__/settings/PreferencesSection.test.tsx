import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { PreferencesSection } from "@/components/settings/PreferencesSection";

const GET_DEFAULTS = {
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
};

function mockFetchSuccess(getData = GET_DEFAULTS) {
  const fetchMock = vi.fn();
  // First call = GET (load preferences)
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  // Subsequent calls = PATCH
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ ...getData }),
  });
  global.fetch = fetchMock;
  return fetchMock;
}

async function renderAndLoad(getData = GET_DEFAULTS) {
  const fetchMock = mockFetchSuccess(getData);
  vi.useFakeTimers();

  await act(async () => {
    render(<PreferencesSection />);
  });
  // Flush GET promise
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });

  expect(screen.getByText("Vegan")).toBeInTheDocument();
  return fetchMock;
}

describe("PreferencesSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders skeleton during load, then checkboxes after GET resolves", async () => {
    mockFetchSuccess();
    const { container } = render(<PreferencesSection />);

    // Skeleton has animate-pulse
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, checkboxes appear
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    expect(screen.getByText("Vegan")).toBeInTheDocument();
    expect(screen.getByText("Vegetarian")).toBeInTheDocument();
    expect(screen.getByText("Halal")).toBeInTheDocument();
  });

  it("checkbox click triggers debounced PATCH after 500ms", async () => {
    const fetchMock = await renderAndLoad();

    // Click "Vegan" checkbox
    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });

    // PATCH should NOT have been called yet (only GET so far)
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Advance past debounce
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const patchCall = fetchMock.mock.calls[1];
    expect(patchCall[0]).toBe("/api/settings/preferences");
    expect(patchCall[1].method).toBe("PATCH");
    const body = JSON.parse(patchCall[1].body);
    expect(body.dietary).toContain("vegan");
  });

  it("rapid clicks within 500ms result in exactly 1 PATCH call", async () => {
    const fetchMock = await renderAndLoad();

    // Rapid clicks on different checkboxes
    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Halal"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Kosher"));
    });

    // Advance past the final debounce window
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    // 1 GET + exactly 1 PATCH
    const patchCalls = fetchMock.mock.calls.filter(
      (call: [string, RequestInit?]) => call[1]?.method === "PATCH"
    );
    expect(patchCalls).toHaveLength(1);
  });

  it("reverts all checkboxes on PATCH failure", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH fails
    fetchMock.mockResolvedValueOnce({ ok: false });
    global.fetch = fetchMock;

    await act(async () => {
      render(<PreferencesSection />);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText("Vegan")).toBeInTheDocument();

    // Click "Vegan"
    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });

    // Advance past debounce to trigger PATCH
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    // After PATCH failure, state reverts
    const veganCheckbox = screen.getByText("Vegan")
      .closest("label")!
      .querySelector("input") as HTMLInputElement;
    expect(veganCheckbox.checked).toBe(false);
  });

  it("radio 'No preference' sends travelFrequency: null in PATCH body", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      travelFrequency: "monthly",
    });

    // Click "No preference" radio
    await act(async () => {
      fireEvent.click(screen.getByText("No preference"));
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    const patchCall = fetchMock.mock.calls.find(
      (call: [string, RequestInit?]) => call[1]?.method === "PATCH"
    );
    expect(patchCall).toBeDefined();
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body.travelFrequency).toBeNull();
  });

  it("network error (fetch throws) reverts state with no crash", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH throws network error
    fetchMock.mockRejectedValueOnce(new Error("Network error"));
    global.fetch = fetchMock;

    await act(async () => {
      render(<PreferencesSection />);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText("Vegan")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    // Should revert without crashing
    const veganCheckbox = screen.getByText("Vegan")
      .closest("label")!
      .querySelector("input") as HTMLInputElement;
    expect(veganCheckbox.checked).toBe(false);
  });

  it("shows error state when GET fails", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false });

    render(<PreferencesSection />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load preferences.")).toBeInTheDocument();
    });

    expect(screen.queryByText("Vegan")).not.toBeInTheDocument();
  });

  it("all dietary checkboxes render with correct labels", async () => {
    mockFetchSuccess();
    render(<PreferencesSection />);

    await waitFor(() => {
      expect(screen.getByText("Vegan")).toBeInTheDocument();
    });

    const expectedLabels = [
      "Vegan",
      "Vegetarian",
      "Halal",
      "Kosher",
      "Gluten-free",
      "Nut allergy",
      "Shellfish allergy",
    ];

    for (const label of expectedLabels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
