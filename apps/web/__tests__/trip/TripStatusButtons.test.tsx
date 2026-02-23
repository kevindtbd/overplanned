/**
 * Component tests for trip status buttons (Start Trip + Completion Banner)
 * in the TripDetailPage.
 *
 * These test the rendering logic extracted from app/trip/[id]/page.tsx.
 * We test the conditional rendering and fetch calls by rendering a minimal
 * version of the status button/banner logic.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock modules before import
vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ id: "trip-1" })),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/trip/DayNavigation", () => ({
  DayNavigation: () => <div data-testid="day-nav">DayNav</div>,
}));

vi.mock("@/components/trip/DayView", () => ({
  DayView: () => <div data-testid="day-view">DayView</div>,
}));

vi.mock("@/components/trip/WelcomeCard", () => ({
  WelcomeCard: () => <div data-testid="welcome-card">WelcomeCard</div>,
}));

vi.mock("@/components/states", () => ({
  SlotSkeleton: () => <div>SlotSkeleton</div>,
  ErrorState: ({ message }: { message: string }) => <div>{message}</div>,
}));

vi.mock("@/lib/city-photos", () => ({
  getCityPhoto: () => undefined,
}));

vi.mock("@/components/trip/TripSettings", () => ({
  TripSettings: () => <div data-testid="trip-settings">TripSettings</div>,
}));

vi.mock("@/components/slot/SlotActions", () => ({
  SlotActions: () => null,
}));

// We mock useTripDetail to control the trip data
vi.mock("@/lib/hooks/useTripDetail", () => ({
  useTripDetail: vi.fn(),
}));

const { useTripDetail } = await import("@/lib/hooks/useTripDetail");
const mockUseTripDetail = vi.mocked(useTripDetail);

// Dynamic import after mocks
const { default: TripDetailPage } = await import("@/app/trip/[id]/page");

function makeTripData(overrides: Record<string, unknown> = {}) {
  return {
    id: "trip-1",
    name: "Tokyo Trip",
    destination: "Tokyo, Japan",
    city: "Tokyo",
    country: "Japan",
    timezone: "Asia/Tokyo",
    startDate: "2026-07-01T00:00:00Z",
    endDate: "2026-07-04T00:00:00Z",
    mode: "solo",
    status: "planning",
    planningProgress: 0,
    slots: [],
    members: [],
    ...overrides,
  };
}

describe("TripDetailPage — Start Trip button", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    // Mock sessionStorage
    const store: Record<string, string> = {};
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, val: string) => { store[key] = val; },
      removeItem: (key: string) => { delete store[key]; },
    });
  });

  it("shows 'Start trip' button for planning status + organizer", () => {
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({ status: "planning" }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.getByText("Start trip")).toBeInTheDocument();
  });

  it("hides 'Start trip' button for active status", () => {
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({ status: "active" }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Start trip")).not.toBeInTheDocument();
  });

  it("hides 'Start trip' button for completed status", () => {
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({ status: "completed" }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Start trip")).not.toBeInTheDocument();
  });

  it("hides 'Start trip' button for non-organizer", () => {
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({ status: "planning" }) as never,
      setTrip: vi.fn(),
      myRole: "member",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Start trip")).not.toBeInTheDocument();
  });

  it("clicking Start trip sends PATCH with status: active", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = mockFetch;

    const setTrip = vi.fn();
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({ status: "planning" }) as never,
      setTrip,
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    await user.click(screen.getByText("Start trip"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/trips/trip-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "active" }),
      });
    });
  });
});

describe("TripDetailPage — Completion banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("sessionStorage", {
      getItem: () => null,
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows completion banner for active + organizer + past endDate", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-01T00:00:00Z"));

    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({
        status: "active",
        endDate: "2026-07-04T00:00:00Z", // past
      }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.getByText("Trip complete!")).toBeInTheDocument();
    expect(screen.getByText("Mark as done")).toBeInTheDocument();
  });

  it("hides completion banner when endDate is in the future", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-01T00:00:00Z"));

    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({
        status: "active",
        endDate: "2026-07-04T00:00:00Z", // future
      }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Trip complete!")).not.toBeInTheDocument();
  });

  it("hides completion banner for non-organizer", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-01T00:00:00Z"));

    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({
        status: "active",
        endDate: "2026-07-04T00:00:00Z",
      }) as never,
      setTrip: vi.fn(),
      myRole: "member",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Trip complete!")).not.toBeInTheDocument();
  });

  it("hides completion banner for planning status", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-01T00:00:00Z"));

    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({
        status: "planning",
        endDate: "2026-07-04T00:00:00Z",
      }) as never,
      setTrip: vi.fn(),
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    expect(screen.queryByText("Trip complete!")).not.toBeInTheDocument();
  });

  it("clicking 'Mark as done' sends PATCH with status: completed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-08-01T00:00:00Z"));

    const user = userEvent.setup();
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = mockFetch;

    const setTrip = vi.fn();
    mockUseTripDetail.mockReturnValue({
      trip: makeTripData({
        status: "active",
        endDate: "2026-07-04T00:00:00Z",
      }) as never,
      setTrip,
      myRole: "organizer",
      fetchState: "success" as const,
      errorMessage: "",
      fetchTrip: vi.fn(),
    });

    render(<TripDetailPage />);
    await user.click(screen.getByText("Mark as done"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/trips/trip-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "completed" }),
      });
    });
  });
});
