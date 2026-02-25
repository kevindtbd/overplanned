/**
 * Component tests for TravelStyleSection
 * Merges PreferencesSection + TravelInterests into a single tabbed component.
 * Tests: loading/error states, tab navigation, practical fieldsets, vibe groups,
 * chip toggles (immediate PATCH vs debounced), radio selects, textarea blur saves,
 * revert on failure, character counter, and layout class.
 */

import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TravelStyleSection } from "@/components/settings/TravelStyleSection";

// ---------- Constants ----------

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

// ---------- Mock helpers ----------

function mockFetchSuccess(getData: Record<string, unknown> = GET_DEFAULTS) {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValueOnce({ ok: true, json: async () => getData });
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ...getData }) });
  global.fetch = fetchMock;
  return fetchMock;
}

function mockFetchFailure() {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValueOnce({ ok: false, status: 500 });
  global.fetch = fetchMock;
  return fetchMock;
}

// ---------- Setup ----------

beforeEach(() => {
  vi.resetAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

// ---------- Helpers ----------

async function waitForLoaded(container: HTMLElement) {
  await waitFor(() => {
    expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
  });
}

async function switchToVibesTab() {
  const vibesTab = screen.getByRole("tab", { name: "Vibes" });
  fireEvent.click(vibesTab);
}

// ---------- Tests ----------

describe("TravelStyleSection — loading and error states", () => {
  it("renders skeleton during load, then content after GET resolves", async () => {
    const { container } = render(<TravelStyleSection />);
    mockFetchSuccess();

    // Skeleton visible immediately
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    await waitForLoaded(container);

    // Should now show the section heading
    expect(screen.getByText("Travel Style")).toBeInTheDocument();
  });

  it("shows error state when GET fails — 'Failed to load travel style.'", async () => {
    mockFetchFailure();
    render(<TravelStyleSection />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load travel style.")).toBeInTheDocument();
    });
  });
});

describe("TravelStyleSection — section heading", () => {
  it("section heading is 'Travel Style'", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    expect(screen.getByText("Travel Style")).toBeInTheDocument();
  });
});

describe("TravelStyleSection — tab navigation", () => {
  it("two tab buttons render ('Practical' and 'Vibes')", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(screen.getByRole("tab", { name: "Practical" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Vibes" })).toBeInTheDocument();
  });

  it("Practical tab is active by default (aria-selected='true')", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const practicalTab = screen.getByRole("tab", { name: "Practical" });
    const vibesTab = screen.getByRole("tab", { name: "Vibes" });

    expect(practicalTab).toHaveAttribute("aria-selected", "true");
    expect(vibesTab).toHaveAttribute("aria-selected", "false");
  });

  it("all 8 practical fieldset legends render on Practical tab", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Use querySelectorAll("legend") to avoid conflicts with chip labels
    // that share text (e.g., "Accommodation" chip label vs fieldset legend)
    const legends = Array.from(container.querySelectorAll("legend")).map(
      (el) => el.textContent?.trim()
    );

    expect(legends).toContain("Dietary needs");
    expect(legends).toContain("Accessibility");
    expect(legends).toContain("Budget comfort");
    expect(legends).toContain("Spending priorities");
    expect(legends).toContain("Accommodation");
    expect(legends).toContain("Getting around");
    expect(legends).toContain("Language comfort");
    expect(legends).toContain("How often do you travel?");
    expect(legends).toContain("Anything else about how you prefer to travel?");
    expect(legends).toHaveLength(9);
  });

  it("clicking 'Vibes' tab switches content — vibe groups appear, practical fieldsets disappear", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Practical fieldsets visible initially (9 = 8 groups + 1 textarea fieldset)
    const legendsBefore = container.querySelectorAll("legend");
    expect(legendsBefore.length).toBe(9);

    // Switch to Vibes tab
    await switchToVibesTab();

    // Practical fieldsets gone, vibes textarea fieldset has 1 legend
    const legendsAfter = container.querySelectorAll("legend");
    expect(legendsAfter.length).toBe(1);

    // Vibe groups visible
    expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
    expect(screen.getByText("Discovery Style")).toBeInTheDocument();
  });

  it("Vibes tab shows all 5 group headings", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    await switchToVibesTab();

    expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
    expect(screen.getByText("Discovery Style")).toBeInTheDocument();
    expect(screen.getByText("Food & Drink")).toBeInTheDocument();
    expect(screen.getByText("Activity Type")).toBeInTheDocument();
    expect(screen.getByText("Social & Time")).toBeInTheDocument();
  });
});

describe("TravelStyleSection — tab panels", () => {
  it("tab panels have role='tabpanel'", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const panel = screen.getByRole("tabpanel");
    expect(panel).toBeInTheDocument();
  });
});

describe("TravelStyleSection — Practical tab chip toggles (immediate PATCH)", () => {
  it("chip toggle sends immediate per-field PATCH (click 'Hostel' -> {accommodationTypes: ['hostel']})", async () => {
    const fetchMock = mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Click the Hostel chip
    const hostelChip = screen.getByRole("checkbox", { name: /hostel/i });
    fireEvent.click(hostelChip);

    await waitFor(() => {
      const patchCalls = (fetchMock.mock.calls as [string, RequestInit][]).filter(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBe(1);
      expect(patchCalls[0][0]).toBe("/api/settings/preferences");
      const body = JSON.parse(patchCalls[0][1].body as string);
      expect(body).toEqual({ accommodationTypes: ["hostel"] });
    });
  });

  it("budget radio select sends immediate PATCH (click 'Mid-range' -> {budgetComfort: 'mid-range'})", async () => {
    const fetchMock = mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const midRangeRadio = screen.getByRole("radio", { name: /mid-range/i });
    fireEvent.click(midRangeRadio);

    await waitFor(() => {
      const patchCalls = (fetchMock.mock.calls as [string, RequestInit][]).filter(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBe(1);
      const body = JSON.parse(patchCalls[0][1].body as string);
      expect(body).toEqual({ budgetComfort: "mid-range" });
    });
  });

  it("budget 'No preference' radio sends budgetComfort: null", async () => {
    const fetchMock = mockFetchSuccess({
      ...GET_DEFAULTS,
      budgetComfort: "mid-range",
    });
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Multiple "No preference" radios (budget + frequency) — budget is first
    const noPreferenceRadios = screen.getAllByRole("radio", { name: /no preference/i });
    fireEvent.click(noPreferenceRadios[0]);

    await waitFor(() => {
      const patchCalls = (fetchMock.mock.calls as [string, RequestInit][]).filter(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBe(1);
      const body = JSON.parse(patchCalls[0][1].body as string);
      expect(body).toEqual({ budgetComfort: null });
    });
  });

  it("practical textarea blur sends preferencesNote PATCH", async () => {
    const fetchMock = mockFetchSuccess();
    const user = userEvent.setup();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const textarea = screen.getByPlaceholderText(
      /I always need a gym nearby/i
    );

    await user.click(textarea); // focus it
    fireEvent.change(textarea, { target: { value: "Never book hostels, always need a gym" } });
    await user.tab();

    await waitFor(() => {
      const patchCalls = (fetchMock.mock.calls as [string, RequestInit][]).filter(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBeGreaterThanOrEqual(1);
      const lastPatch = patchCalls[patchCalls.length - 1];
      const body = JSON.parse(lastPatch[1].body as string);
      expect(body).toHaveProperty("preferencesNote");
      expect(body.preferencesNote).toBe("Never book hostels, always need a gym");
    });
  });
});

describe("TravelStyleSection — Vibes tab chip toggles (debounced at 500ms)", () => {
  it("vibe chip toggle is debounced — no PATCH before 500ms, PATCH after 500ms", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockFetchSuccess();

    await act(async () => {
      render(<TravelStyleSection />);
    });

    // Let the initial fetch/state settle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    // Switch to Vibes tab
    await act(async () => {
      const vibesTab = screen.getByRole("tab", { name: "Vibes" });
      fireEvent.click(vibesTab);
    });

    expect(screen.getByText("Hidden gems")).toBeInTheDocument();

    // Click the "Hidden gems" chip
    await act(async () => {
      fireEvent.click(screen.getByText("Hidden gems"));
    });

    // No PATCH should have fired yet
    const patchCallsBefore = ((fetchMock as Mock).mock.calls as [string, RequestInit][]).filter(
      (c) => c[1]?.method === "PATCH"
    );
    expect(patchCallsBefore.length).toBe(0);

    // Advance past the 500ms debounce
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    const patchCallsAfter = ((fetchMock as Mock).mock.calls as [string, RequestInit][]).filter(
      (c) => c[1]?.method === "PATCH"
    );
    expect(patchCallsAfter.length).toBe(1);
    expect(patchCallsAfter[0][0]).toBe("/api/settings/preferences");
    const body = JSON.parse(patchCallsAfter[0][1].body as string);
    expect(body).toEqual({ vibePreferences: ["hidden-gem"] });
  });

  it("vibes textarea blur sends travelStyleNote PATCH", async () => {
    const fetchMock = mockFetchSuccess();
    const user = userEvent.setup();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    await switchToVibesTab();

    const textarea = screen.getByPlaceholderText(
      /I always hunt for the best coffee spot/i
    );

    await user.click(textarea); // focus it
    fireEvent.change(textarea, { target: { value: "Best coffee in every city" } });
    await user.tab();

    await waitFor(() => {
      const patchCalls = ((fetchMock as Mock).mock.calls as [string, RequestInit][]).filter(
        (c) => c[1]?.method === "PATCH"
      );
      expect(patchCalls.length).toBeGreaterThanOrEqual(1);
      const lastPatch = patchCalls[patchCalls.length - 1];
      const body = JSON.parse(lastPatch[1].body as string);
      expect(body).toHaveProperty("travelStyleNote");
      expect(body.travelStyleNote).toBe("Best coffee in every city");
    });
  });
});

describe("TravelStyleSection — revert on PATCH failure", () => {
  it("reverts practical chip on PATCH failure", async () => {
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH fails
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500 });
    global.fetch = fetchMock;

    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Hostel chip starts unchecked
    const hostelChip = screen.getByRole("checkbox", { name: /hostel/i }) as HTMLInputElement;
    expect(hostelChip.checked).toBe(false);

    // Click it (optimistic toggle)
    fireEvent.click(hostelChip);
    expect(hostelChip.checked).toBe(true);

    // After PATCH fails, should revert
    await waitFor(() => {
      expect(hostelChip.checked).toBe(false);
    });
  });
});

describe("TravelStyleSection — character counter", () => {
  it("character counter shows when <=100 characters remaining", async () => {
    mockFetchSuccess();
    const user = userEvent.setup();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    const textarea = screen.getByPlaceholderText(
      /I always need a gym nearby/i
    );

    // Set value directly — user.type with 401 chars causes CI timeout
    // (401 individual keystroke simulations > 5s on slow machines)
    const longText = "a".repeat(401);
    await user.clear(textarea);
    fireEvent.change(textarea, { target: { value: longText } });

    // Counter should appear — showing "X characters remaining"
    await waitFor(() => {
      expect(screen.getByText("99 characters remaining")).toBeInTheDocument();
    });
  });

  it("character counter does NOT show when more than 100 characters remaining", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // Textarea is empty — 500 remaining, well above 100
    // Counter element should not be present
    expect(screen.queryByText("500")).not.toBeInTheDocument();
  });
});

describe("TravelStyleSection — layout", () => {
  it("2-col grid class is present (sm:grid-cols-2) in Practical tab content", async () => {
    mockFetchSuccess();
    const { container } = render(<TravelStyleSection />);
    await waitForLoaded(container);

    // The practical fieldsets should be wrapped in a 2-col grid on sm screens
    const grid = container.querySelector(".sm\\:grid-cols-2");
    expect(grid).toBeInTheDocument();
  });
});
