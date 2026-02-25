import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TripHeroCard, type TripSummary } from "@/components/dashboard/TripHeroCard";

// Mock Next.js Image component
vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));

const mockTrip: TripSummary = {
  id: "trip-1",
  name: "Tokyo Adventure",
  primaryDestination: "Tokyo, Japan",
  primaryCity: "Tokyo",
  primaryCountry: "Japan",
  routeString: null,
  mode: "solo",
  status: "planning",
  startDate: "2026-03-15",
  endDate: "2026-03-22",
  planningProgress: 65,
  memberCount: 1,
  legCount: 1,
  createdAt: "2026-02-01T00:00:00Z",
};

describe("TripHeroCard", () => {
  it("renders trip name", () => {
    render(<TripHeroCard trip={mockTrip} />);
    expect(screen.getByText("Tokyo Adventure")).toBeInTheDocument();
  });

  it("renders destination as fallback when name is null", () => {
    const tripWithoutName = { ...mockTrip, name: null };
    render(<TripHeroCard trip={tripWithoutName} />);
    // Should render as the main heading (h3)
    const heading = screen.getByRole("heading", { name: "Tokyo, Japan" });
    expect(heading).toBeInTheDocument();
  });

  it("renders city and country", () => {
    render(<TripHeroCard trip={mockTrip} />);
    expect(screen.getByText("Tokyo, Japan")).toBeInTheDocument();
  });

  it("renders formatted date range", () => {
    render(<TripHeroCard trip={mockTrip} />);
    // Date shifts by timezone — match either local or UTC rendering
    const dateText = screen.getByText(/Mar (14|15) - Mar (21|22), 2026/);
    expect(dateText).toBeInTheDocument();
  });

  it("renders trip mode badge", () => {
    render(<TripHeroCard trip={mockTrip} />);
    expect(screen.getByText("solo trip")).toBeInTheDocument();
  });

  it("renders planning progress for planning status", () => {
    render(<TripHeroCard trip={mockTrip} />);
    expect(screen.getByText("Planning progress")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
  });

  it("does not render planning progress for non-planning status", () => {
    const completedTrip = { ...mockTrip, status: "completed" };
    render(<TripHeroCard trip={completedTrip} />);
    expect(screen.queryByText("Planning progress")).not.toBeInTheDocument();
  });

  it("renders member count for group trips", () => {
    const groupTrip = { ...mockTrip, memberCount: 3 };
    render(<TripHeroCard trip={groupTrip} />);
    expect(screen.getByText("3 members")).toBeInTheDocument();
  });
});
