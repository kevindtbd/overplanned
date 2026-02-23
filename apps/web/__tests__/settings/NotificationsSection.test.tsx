import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationsSection } from "@/components/settings/NotificationsSection";

const GET_DEFAULTS = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  checkinReminder: false,
  citySeeded: true,
  inspirationNudges: false,
  productUpdates: false,
  preTripDaysBefore: 3,
};

function mockFetchSuccess(getData = GET_DEFAULTS) {
  const fetchMock = vi.fn();
  // First call = GET
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  // Subsequent calls = PATCH
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({}),
  });
  global.fetch = fetchMock;
  return fetchMock;
}

describe("NotificationsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders skeleton during load, then toggles after GET resolves", async () => {
    mockFetchSuccess();
    const { container } = render(<NotificationsSection />);

    // Skeleton visible
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, toggles appear
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("switch");
    expect(toggles).toHaveLength(8);
  });

  it("all 7 toggles render with correct default states", async () => {
    mockFetchSuccess();
    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(8);
    });

    const toggles = screen.getAllByRole("switch");

    // Order: tripReminders, morningBriefing, groupActivity, postTripPrompt, checkinReminder, citySeeded, inspirationNudges, productUpdates
    expect(toggles[0]).toHaveAttribute("aria-checked", "true");  // tripReminders
    expect(toggles[1]).toHaveAttribute("aria-checked", "true");  // morningBriefing
    expect(toggles[2]).toHaveAttribute("aria-checked", "true");  // groupActivity
    expect(toggles[3]).toHaveAttribute("aria-checked", "true");  // postTripPrompt
    expect(toggles[4]).toHaveAttribute("aria-checked", "false"); // checkinReminder
    expect(toggles[5]).toHaveAttribute("aria-checked", "true");  // citySeeded
    expect(toggles[6]).toHaveAttribute("aria-checked", "false"); // inspirationNudges
    expect(toggles[7]).toHaveAttribute("aria-checked", "false"); // productUpdates
  });

  it("toggle click triggers immediate PATCH with single field in body", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(8);
    });

    const toggles = screen.getAllByRole("switch");

    // Click the first toggle (tripReminders, currently true -> false)
    await user.click(toggles[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2); // 1 GET + 1 PATCH
      const patchCall = fetchMock.mock.calls[1];
      expect(patchCall[0]).toBe("/api/settings/notifications");
      expect(patchCall[1].method).toBe("PATCH");
      const body = JSON.parse(patchCall[1].body);
      expect(body).toEqual({ tripReminders: false });
    });
  });

  it("aria-checked attribute changes on toggle click", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(8);
    });

    const toggles = screen.getAllByRole("switch");

    // inspirationNudges starts false (index 6 after checkinReminder insertion)
    expect(toggles[6]).toHaveAttribute("aria-checked", "false");

    await user.click(toggles[6]);

    // Should now be true (optimistic update)
    expect(toggles[6]).toHaveAttribute("aria-checked", "true");
  });

  it("reverts toggle on PATCH failure", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH fails
    fetchMock.mockResolvedValueOnce({ ok: false });
    global.fetch = fetchMock;

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(8);
    });

    const toggles = screen.getAllByRole("switch");

    // tripReminders starts true
    expect(toggles[0]).toHaveAttribute("aria-checked", "true");

    // Click to toggle off — PATCH fails, so it reverts back to true
    await user.click(toggles[0]);

    // After PATCH failure resolves, should revert back to true
    await waitFor(() => {
      expect(toggles[0]).toHaveAttribute("aria-checked", "true");
    });
  });

  it("network error reverts toggle with no crash", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => GET_DEFAULTS,
    });
    // PATCH throws
    fetchMock.mockRejectedValueOnce(new Error("Network error"));
    global.fetch = fetchMock;

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(8);
    });

    const toggles = screen.getAllByRole("switch");

    // morningBriefing starts true
    expect(toggles[1]).toHaveAttribute("aria-checked", "true");

    await user.click(toggles[1]);

    // Should revert after network error
    await waitFor(() => {
      expect(toggles[1]).toHaveAttribute("aria-checked", "true");
    });
  });

  it("shows error state when GET fails", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load notification preferences.")
      ).toBeInTheDocument();
    });

    // No toggles should render
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
  });
});
