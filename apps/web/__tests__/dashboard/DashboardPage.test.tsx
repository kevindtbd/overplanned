import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardPage from "@/app/dashboard/page";

// Mock Next.js Link
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

// Mock Next.js Image
vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} />
  ),
}));

// Mock AppShell - render children only
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockDraftTrip = {
  id: "trip-draft-1",
  name: null,
  destination: "Mexico City, Mexico",
  city: "Mexico City",
  country: "Mexico",
  mode: "solo",
  status: "draft",
  startDate: "2026-06-01",
  endDate: "2026-06-10",
  planningProgress: 0,
  memberCount: 1,
  createdAt: "2026-02-20T00:00:00Z",
};

const mockDraftTripNoDates = {
  id: "trip-draft-2",
  name: null,
  destination: "Kyoto, Japan",
  city: "Kyoto",
  country: "Japan",
  mode: "solo",
  status: "draft",
  startDate: null as string | null,
  endDate: null as string | null,
  planningProgress: 0,
  memberCount: 1,
  createdAt: "2026-02-21T00:00:00Z",
};

const mockActiveTrip = {
  id: "trip-1",
  name: "Tokyo Adventure",
  destination: "Tokyo, Japan",
  city: "Tokyo",
  country: "Japan",
  mode: "solo",
  status: "planning",
  startDate: "2026-03-15",
  endDate: "2026-03-22",
  planningProgress: 65,
  memberCount: 1,
  createdAt: "2026-02-01T00:00:00Z",
};

const mockPastTrip = {
  id: "trip-2",
  name: "Paris Getaway",
  destination: "Paris, France",
  city: "Paris",
  country: "France",
  mode: "solo",
  status: "completed",
  startDate: "2025-12-01",
  endDate: "2025-12-08",
  planningProgress: 100,
  memberCount: 1,
  createdAt: "2025-11-01T00:00:00Z",
};

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it("shows loading state initially", () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<DashboardPage />);

    // Should show loading skeletons
    expect(screen.getByText("Your trips")).toBeInTheDocument();
    // CardSkeleton doesn't have text content, but we can verify the page header is present
  });

  it("shows error state when API call fails", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("API Error")
    );

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("API Error")).toBeInTheDocument();
    });
  });

  it("shows QuickStartGrid when no trips exist", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Where to?")).toBeInTheDocument();
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
      expect(screen.getByText("New York")).toBeInTheDocument();
      expect(screen.getByText("Mexico City")).toBeInTheDocument();
      expect(screen.getByText("Somewhere else")).toBeInTheDocument();
    });
  });

  it("shows active trips without section label when no past trips", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockActiveTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
      expect(screen.getByText("Planning progress")).toBeInTheDocument();
    });
    // No section label when only active trips exist
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });

  it("shows past trips without section label when no active trips", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockPastTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Paris Getaway")).toBeInTheDocument();
    });
    // No section label when only past trips exist
    expect(screen.queryByText("Past trips")).not.toBeInTheDocument();
  });

  it("partitions trips into active and past correctly", async () => {
    const mixedTrips = [
      mockActiveTrip,
      mockPastTrip,
      { ...mockActiveTrip, id: "trip-3", status: "active" },
      { ...mockPastTrip, id: "trip-4", status: "archived" },
    ];

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: mixedTrips }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Past trips")).toBeInTheDocument();
    });

    // Should have 2 active trips (planning + active)
    // and 2 past trips (completed + archived)
  });

  it("QuickStartGrid city cards link to onboarding with query params", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Where to?")).toBeInTheDocument();
    });

    const tokyoLink = screen.getByRole("link", { name: /Plan a trip to Tokyo/i });
    expect(tokyoLink).toHaveAttribute("href", "/onboarding?city=Tokyo&step=dates");

    const nycLink = screen.getByRole("link", { name: /Plan a trip to New York/i });
    expect(nycLink).toHaveAttribute("href", "/onboarding?city=New%20York&step=dates");

    const somewhereElse = screen.getByRole("link", { name: /different city/i });
    expect(somewhereElse).toHaveAttribute("href", "/onboarding");
  });

  it("shows '+ New trip' header button when trips exist", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockActiveTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
    });

    const newTripLink = screen.getByRole("link", { name: /New trip/i });
    expect(newTripLink).toHaveAttribute("href", "/onboarding");
  });

  it("does not show '+ New trip' button on empty state", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Where to?")).toBeInTheDocument();
    });

    expect(screen.queryByText("New trip")).not.toBeInTheDocument();
  });

  it("retries fetch when retry button is clicked in error state", async () => {
    const user = userEvent.setup();

    // First call fails
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("Network error")
    );

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });

    // Second call succeeds
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockActiveTrip] }),
    });

    const retryButton = screen.getByRole("button", { name: /try again/i });
    await user.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
    });
  });

  // ---------- Draft card tests ----------

  it("renders DraftIdeaCard for draft trips with 'Continue planning' text", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockDraftTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Mexico City")).toBeInTheDocument();
      expect(screen.getByText("Continue planning")).toBeInTheDocument();
    });
  });

  it("draft trips link to /onboarding?resume=<tripId>, NOT /trip/<id>", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockDraftTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Continue planning")).toBeInTheDocument();
    });

    const draftLink = screen.getByTestId("draft-idea-card");
    expect(draftLink).toHaveAttribute("href", `/onboarding?resume=${mockDraftTrip.id}`);
    // Must NOT link to trip detail
    expect(draftLink).not.toHaveAttribute("href", `/trip/${mockDraftTrip.id}`);
  });

  it("planning/active trips still render TripHeroCard (not DraftIdeaCard)", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockActiveTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
      expect(screen.getByText("Planning progress")).toBeInTheDocument();
    });

    // Should NOT render as a draft card
    expect(screen.queryByText("Continue planning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("draft-idea-card")).not.toBeInTheDocument();
  });

  it("committed hero cards appear before draft idea cards in DOM", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockDraftTrip, mockActiveTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
      expect(screen.getByText("Continue planning")).toBeInTheDocument();
    });

    // Hero card text should appear before draft card text in DOM order
    const heroText = screen.getByText("Tokyo Adventure");
    const draftText = screen.getByText("Continue planning");
    // compareDocumentPosition bit 4 = DOCUMENT_POSITION_FOLLOWING
    const position = heroText.compareDocumentPosition(draftText);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("only drafts, no planning trips: drafts show, QuickStartGrid does NOT show", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockDraftTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Continue planning")).toBeInTheDocument();
    });

    // QuickStartGrid should NOT appear
    expect(screen.queryByText("Where to?")).not.toBeInTheDocument();
  });

  it("draft + past trips: section labels show", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockDraftTrip, mockPastTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Past trips")).toBeInTheDocument();
    });
  });
});
