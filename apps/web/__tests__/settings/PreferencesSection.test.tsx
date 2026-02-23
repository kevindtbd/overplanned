import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { PreferencesSection } from "@/components/settings/PreferencesSection";

const GET_DEFAULTS = {
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
  vibePreferences: [],
  travelStyleNote: null,
  budgetComfort: null,
  spendingPriorities: [],
  accommodationTypes: [],
  transitModes: [],
  preferencesNote: null,
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

  await act(async () => {
    render(<PreferencesSection />);
  });

  // Wait for content to appear after GET resolves
  await waitFor(() => {
    expect(screen.getByText("Vegan")).toBeInTheDocument();
  });

  return fetchMock;
}

describe("PreferencesSection", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // -----------------------------------------------------------------------
  // 1. Skeleton during load, then content
  // -----------------------------------------------------------------------
  it("renders skeleton during load, then content after GET resolves", async () => {
    mockFetchSuccess();
    const { container } = render(<PreferencesSection />);

    // Skeleton has animate-pulse
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, skeleton gone and content appears
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    expect(screen.getByText("Vegan")).toBeInTheDocument();
    expect(screen.getByText("Vegetarian")).toBeInTheDocument();
    expect(screen.getByText("Halal")).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // 2. Error state when GET fails
  // -----------------------------------------------------------------------
  it("shows error state when GET fails", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false });

    render(<PreferencesSection />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load preferences.")).toBeInTheDocument();
    });

    expect(screen.queryByText("Vegan")).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // 3. All 8 fieldset headings render
  // -----------------------------------------------------------------------
  it("renders all 8 fieldset legend headings", async () => {
    const { container } = await (async () => {
      const fetchMock = mockFetchSuccess();
      let result!: ReturnType<typeof render>;
      await act(async () => {
        result = render(<PreferencesSection />);
      });
      await waitFor(() => expect(screen.getByText("Vegan")).toBeInTheDocument());
      return result;
    })();

    // Query legend elements directly to avoid ambiguity with chip labels
    const legends = Array.from(container.querySelectorAll("legend")).map(
      (el) => el.textContent?.trim()
    );

    const expectedLegends = [
      "Dietary needs",
      "Accessibility",
      "Budget comfort",
      "Spending priorities",
      "Accommodation",
      "Getting around",
      "Language comfort",
      "How often do you travel?",
      "Anything else about how you prefer to travel?",
    ];

    for (const legend of expectedLegends) {
      expect(legends).toContain(legend);
    }
  });

  // -----------------------------------------------------------------------
  // 4. All 10 dietary chip labels render
  // -----------------------------------------------------------------------
  it("renders all 10 dietary chip labels", async () => {
    await renderAndLoad();

    const dietaryLabels = [
      "Vegan",
      "Vegetarian",
      "Halal",
      "Kosher",
      "Gluten-free",
      "Nut allergy",
      "Shellfish allergy",
      "Dairy-free",
      "Pescatarian",
      "No pork",
    ];

    for (const label of dietaryLabels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  // -----------------------------------------------------------------------
  // 5. All 6 mobility chip labels render
  // -----------------------------------------------------------------------
  it("renders all 6 mobility chip labels", async () => {
    await renderAndLoad();

    const mobilityLabels = [
      "Wheelchair accessible",
      "Low-step preferred",
      "Elevator required",
      "Sensory-friendly",
      "Service animal",
      "Limited stamina",
    ];

    for (const label of mobilityLabels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  // -----------------------------------------------------------------------
  // 6. Budget radio selects correctly; "No preference" sends budgetComfort: null
  // -----------------------------------------------------------------------
  it("budget radio select sends per-field PATCH immediately", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Mid-range"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const patchCall = fetchMock.mock.calls[1];
    expect(patchCall[0]).toBe("/api/settings/preferences");
    expect(patchCall[1].method).toBe("PATCH");
    const body = JSON.parse(patchCall[1].body);
    expect(body.budgetComfort).toBe("mid-range");
  });

  it("budget 'No preference' radio sends budgetComfort: null", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      budgetComfort: "budget",
    });

    // "No preference" appears multiple times (budget + frequency fieldsets)
    // click the one inside Budget comfort fieldset — get all, pick first
    const noPreferenceButtons = screen.getAllByText("No preference");
    await act(async () => {
      fireEvent.click(noPreferenceButtons[0]);
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const patchCall = fetchMock.mock.calls[1];
    const body = JSON.parse(patchCall[1].body);
    expect(body.budgetComfort).toBeNull();
  });

  // -----------------------------------------------------------------------
  // 7. Chip toggle sends per-field PATCH immediately (accommodationTypes)
  // -----------------------------------------------------------------------
  it("chip toggle sends immediate per-field PATCH with updated array", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Hostel"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const patchCall = fetchMock.mock.calls[1];
    expect(patchCall[0]).toBe("/api/settings/preferences");
    expect(patchCall[1].method).toBe("PATCH");
    const body = JSON.parse(patchCall[1].body);
    expect(body.accommodationTypes).toEqual(["hostel"]);
  });

  it("clicking an already-selected chip removes it from the array", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      accommodationTypes: ["hostel"],
    });

    await act(async () => {
      fireEvent.click(screen.getByText("Hostel"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.accommodationTypes).toEqual([]);
  });

  // -----------------------------------------------------------------------
  // 8. Chip toggles for spending, accommodation, transit
  // -----------------------------------------------------------------------
  it("spending priority chip sends per-field PATCH immediately", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Experiences"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.spendingPriorities).toEqual(["experiences"]);
  });

  it("transit mode chip sends per-field PATCH immediately", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Biking"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.transitModes).toEqual(["biking"]);
  });

  it("accommodation chip 'Boutique hotel' sends per-field PATCH immediately", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Boutique hotel"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.accommodationTypes).toEqual(["boutique-hotel"]);
  });

  // -----------------------------------------------------------------------
  // 9. Free-form textarea blur save sends preferencesNote
  // -----------------------------------------------------------------------
  it("textarea saves preferencesNote on blur", async () => {
    const fetchMock = await renderAndLoad();

    const textarea = screen.getByPlaceholderText(
      "I always need a gym nearby, never book hostels..."
    );

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Always need a pool nearby" } });
      fireEvent.blur(textarea);
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const patchCall = fetchMock.mock.calls[1];
    expect(patchCall[0]).toBe("/api/settings/preferences");
    expect(patchCall[1].method).toBe("PATCH");
    const body = JSON.parse(patchCall[1].body);
    expect(body.preferencesNote).toBe("Always need a pool nearby");
  });

  it("textarea blur with unchanged value does not send PATCH", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      preferencesNote: "Existing note",
    });

    const textarea = screen.getByPlaceholderText(
      "I always need a gym nearby, never book hostels..."
    );

    // Blur without changing value
    await act(async () => {
      fireEvent.blur(textarea);
    });

    // Only the initial GET, no PATCH
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("textarea blur with empty string sends preferencesNote: null", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      preferencesNote: "Some note",
    });

    const textarea = screen.getByPlaceholderText(
      "I always need a gym nearby, never book hostels..."
    );

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "   " } });
      fireEvent.blur(textarea);
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.preferencesNote).toBeNull();
  });

  // -----------------------------------------------------------------------
  // 10. Character counter shows at <=100 remaining
  // -----------------------------------------------------------------------
  it("character counter appears only when <=100 characters remaining", async () => {
    await renderAndLoad();

    const textarea = screen.getByPlaceholderText(
      "I always need a gym nearby, never book hostels..."
    );

    // Counter should not show when far from the limit
    expect(screen.queryByText(/characters remaining/)).not.toBeInTheDocument();

    // Type a string that leaves exactly 100 chars remaining (500 - 400 = 100)
    const longText = "a".repeat(400);
    await act(async () => {
      fireEvent.change(textarea, { target: { value: longText } });
    });

    expect(screen.getByText("100 characters remaining")).toBeInTheDocument();

    // Type more — counter should update
    const longerText = "a".repeat(450);
    await act(async () => {
      fireEvent.change(textarea, { target: { value: longerText } });
    });

    expect(screen.getByText("50 characters remaining")).toBeInTheDocument();
  });

  it("character counter does not appear when more than 100 remaining", async () => {
    await renderAndLoad();

    const textarea = screen.getByPlaceholderText(
      "I always need a gym nearby, never book hostels..."
    );

    // 399 chars typed = 101 remaining, no counter
    await act(async () => {
      fireEvent.change(textarea, { target: { value: "a".repeat(399) } });
    });

    expect(screen.queryByText(/characters remaining/)).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // 11. 2-col grid class present
  // -----------------------------------------------------------------------
  it("applies 2-col grid layout class on desktop", async () => {
    const { container } = await (async () => {
      const fetchMock = mockFetchSuccess();
      let result!: ReturnType<typeof render>;
      await act(async () => {
        result = render(<PreferencesSection />);
      });
      await waitFor(() => expect(screen.getByText("Vegan")).toBeInTheDocument());
      return result;
    })();

    const grid = container.querySelector(".sm\\:grid-cols-2");
    expect(grid).toBeInTheDocument();
    expect(grid).toHaveClass("grid");
    expect(grid).toHaveClass("grid-cols-1");
    expect(grid).toHaveClass("gap-x-6");
    expect(grid).toHaveClass("gap-y-4");
  });

  // -----------------------------------------------------------------------
  // 12. Revert on PATCH failure
  // -----------------------------------------------------------------------
  it("reverts chip state on PATCH failure (ok: false)", async () => {
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
    await waitFor(() => expect(screen.getByText("Vegan")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });

    // Wait for PATCH to settle and revert
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Checkbox should be reverted to unchecked
    const veganLabel = screen.getByText("Vegan").closest("label")!;
    const veganCheckbox = veganLabel.querySelector("input") as HTMLInputElement;
    expect(veganCheckbox.checked).toBe(false);
  });

  it("reverts state on network error (fetch throws)", async () => {
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH throws
    fetchMock.mockRejectedValueOnce(new Error("Network error"));
    global.fetch = fetchMock;

    await act(async () => {
      render(<PreferencesSection />);
    });
    await waitFor(() => expect(screen.getByText("Vegan")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByText("Vegan"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const veganLabel = screen.getByText("Vegan").closest("label")!;
    const veganCheckbox = veganLabel.querySelector("input") as HTMLInputElement;
    expect(veganCheckbox.checked).toBe(false);
  });

  // -----------------------------------------------------------------------
  // Travel frequency "No preference" sends travelFrequency: null
  // -----------------------------------------------------------------------
  it("travel frequency 'No preference' sends travelFrequency: null", async () => {
    const fetchMock = await renderAndLoad({
      ...GET_DEFAULTS,
      travelFrequency: "monthly",
    });

    // Multiple "No preference" labels — get all, the second is for travelFrequency
    const noPreferenceButtons = screen.getAllByText("No preference");
    const frequencyNoPreference = noPreferenceButtons[noPreferenceButtons.length - 1];

    await act(async () => {
      fireEvent.click(frequencyNoPreference);
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.travelFrequency).toBeNull();
  });

  // -----------------------------------------------------------------------
  // Multiple chips accumulate in the same field
  // -----------------------------------------------------------------------
  it("multiple chip clicks accumulate values in the same field", async () => {
    const fetchMock = await renderAndLoad();

    await act(async () => {
      fireEvent.click(screen.getByText("Hostel"));
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Set up next PATCH mock to track the second call
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...GET_DEFAULTS, accommodationTypes: ["hostel"] }),
    });

    // Re-mock to reflect persisted state for second click
    // Since PATCH returns a fixed shape, the component uses lastSavedRef.
    // Test that the second click adds to the in-memory state.
    await act(async () => {
      fireEvent.click(screen.getByText("Camping"));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    const secondPatch = fetchMock.mock.calls[2];
    const body = JSON.parse(secondPatch[1].body);
    // Should include both hostel and camping
    expect(body.accommodationTypes).toContain("hostel");
    expect(body.accommodationTypes).toContain("camping");
  });
});
