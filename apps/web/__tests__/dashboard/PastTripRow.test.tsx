import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PastTripRow } from "@/components/dashboard/PastTripRow";
import { type TripSummary } from "@/components/dashboard/TripHeroCard";

// Mock Next.js components
vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const mockTrip: TripSummary = {
  id: "trip-1",
  name: "Paris Getaway",
  primaryDestination: "Paris, France",
  primaryCity: "Paris",
  primaryCountry: "France",
  routeString: "Paris",
  mode: "solo",
  status: "completed",
  startDate: "2025-12-10",
  endDate: "2025-12-17",
  planningProgress: 100,
  memberCount: 1,
  legCount: 1,
  createdAt: "2025-11-01T00:00:00Z",
};

describe("PastTripRow", () => {
  it("renders trip name", () => {
    render(<PastTripRow trip={mockTrip} />);
    expect(screen.getByText("Paris Getaway")).toBeInTheDocument();
  });

  it("renders destination as fallback when name is null", () => {
    const tripWithoutName = { ...mockTrip, name: null };
    render(<PastTripRow trip={tripWithoutName} />);
    // Should render as the main heading (h4)
    const heading = screen.getByRole("heading", { name: "Paris, France" });
    expect(heading).toBeInTheDocument();
  });

  it("renders city and country", () => {
    render(<PastTripRow trip={mockTrip} />);
    expect(screen.getByText("Paris, France")).toBeInTheDocument();
  });

  it("renders formatted date range", () => {
    render(<PastTripRow trip={mockTrip} />);
    // Date shifts by timezone — match either local or UTC rendering
    const dateText = screen.getByText(/Dec (9|10) - Dec (16|17)/);
    expect(dateText).toBeInTheDocument();
  });

  it("renders as a link to the trip page", () => {
    const { container } = render(<PastTripRow trip={mockTrip} />);
    const link = container.querySelector('a[href="/trip/trip-1"]');
    expect(link).toBeInTheDocument();
  });
});
