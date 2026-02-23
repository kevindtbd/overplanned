import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WelcomeCard } from "@/components/trip/WelcomeCard";

describe("WelcomeCard", () => {
  it("renders city name in heading", () => {
    render(
      <WelcomeCard city="Tokyo" totalSlots={12} totalDays={5} onDismiss={vi.fn()} />
    );
    expect(screen.getByText("Your Tokyo itinerary is ready")).toBeInTheDocument();
  });

  it("renders slot and day counts when slots exist", () => {
    render(
      <WelcomeCard city="Tokyo" totalSlots={12} totalDays={5} onDismiss={vi.fn()} />
    );
    expect(
      screen.getByText(/12 activities across 5 days/)
    ).toBeInTheDocument();
    expect(screen.getByText(/confirm on the ones you love/)).toBeInTheDocument();
  });

  it("renders zero-state copy when totalSlots is 0", () => {
    render(
      <WelcomeCard city="Tokyo" totalSlots={0} totalDays={5} onDismiss={vi.fn()} />
    );
    expect(
      screen.getByText(/5 days planned. Browse activities/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/confirm on the ones you love/)).not.toBeInTheDocument();
  });

  it("calls onDismiss when 'Got it' is clicked", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(
      <WelcomeCard city="Tokyo" totalSlots={12} totalDays={5} onDismiss={onDismiss} />
    );

    await user.click(screen.getByRole("button", { name: /got it/i }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("does not call onDismiss before button click", () => {
    const onDismiss = vi.fn();
    render(
      <WelcomeCard city="Tokyo" totalSlots={12} totalDays={5} onDismiss={onDismiss} />
    );
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("renders 'Got it' button accessible by role", () => {
    render(
      <WelcomeCard city="Tokyo" totalSlots={12} totalDays={5} onDismiss={vi.fn()} />
    );
    expect(screen.getByRole("button", { name: /got it/i })).toBeInTheDocument();
  });
});
