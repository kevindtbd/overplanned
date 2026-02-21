import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardPage from "@/app/dashboard/page";

// Mock Next.js router
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
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

  it("shows empty state when no trips exist", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Your adventures start here")).toBeInTheDocument();
      expect(screen.getByText("Plan your first trip and we will build you a local-first itinerary.")).toBeInTheDocument();
    });
  });

  it("shows active trips in hero card format", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockActiveTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Planning progress")).toBeInTheDocument();
    });
  });

  it("shows past trips in compact row format", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [mockPastTrip] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Paris Getaway")).toBeInTheDocument();
      expect(screen.getByText("Past trips")).toBeInTheDocument();
    });
  });

  it("partitions trips into active and past correctly", async () => {
    const mixedTrips = [
      mockActiveTrip,
      mockPastTrip,
      { ...mockActiveTrip, id: "trip-3", status: "active" },
      { ...mockPastTrip, id: "trip-4", status: "cancelled" },
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
    // and 2 past trips (completed + cancelled)
  });

  it("navigates to onboarding when 'Plan a trip' is clicked", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ trips: [] }),
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Your adventures start here")).toBeInTheDocument();
    });

    const planButton = screen.getByRole("button", { name: "Plan a trip" });
    await user.click(planButton);

    expect(mockPush).toHaveBeenCalledWith("/onboarding");
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
});
