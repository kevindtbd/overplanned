import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DraftIdeaCard } from "@/components/dashboard/DraftIdeaCard";
import type { TripSummary } from "@/components/dashboard/TripHeroCard";

// Mock Next.js Link
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const baseDraft: TripSummary = {
  id: "draft-abc-123",
  name: null,
  primaryDestination: "Tokyo, Japan",
  primaryCity: "Tokyo",
  primaryCountry: "Japan",
  mode: "solo",
  status: "draft",
  startDate: "2026-04-10",
  endDate: "2026-04-17",
  planningProgress: 0,
  memberCount: 1,
  legCount: 1,
  createdAt: "2026-02-20T00:00:00Z",
};

describe("DraftIdeaCard", () => {
  it("renders city name", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    expect(screen.getByText("Tokyo")).toBeInTheDocument();
  });

  it("renders country", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    expect(screen.getByText("Japan")).toBeInTheDocument();
  });

  it("shows dates when present", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    // Apr 10 - Apr 17, 2026
    expect(screen.getByTestId("draft-dates")).toBeInTheDocument();
    expect(screen.getByTestId("draft-dates").textContent).toContain("Apr");
  });

  it("does not show dates when startDate is null", () => {
    const noDates = {
      ...baseDraft,
      startDate: null as unknown as string,
      endDate: null as unknown as string,
    };
    render(<DraftIdeaCard trip={noDates} />);
    expect(screen.queryByTestId("draft-dates")).not.toBeInTheDocument();
  });

  it("links to /onboarding?resume=<tripId>", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    const link = screen.getByTestId("draft-idea-card");
    expect(link).toHaveAttribute("href", "/onboarding?resume=draft-abc-123");
  });

  it("does NOT render progress bar or member count", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText(/members/i)).not.toBeInTheDocument();
  });

  it("shows 'Continue planning' text", () => {
    render(<DraftIdeaCard trip={baseDraft} />);
    expect(screen.getByText("Continue planning")).toBeInTheDocument();
  });
});
