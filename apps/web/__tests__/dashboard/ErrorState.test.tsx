import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorState } from "@/components/states/ErrorState";

describe("ErrorState", () => {
  it("renders with default error message when no message provided", () => {
    render(<ErrorState />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("renders custom error message when provided", () => {
    render(<ErrorState message="Failed to load data" />);
    expect(screen.getByText("Failed to load data")).toBeInTheDocument();
  });

  it("renders without retry button when onRetry is not provided", () => {
    render(<ErrorState message="Error occurred" />);
    const button = screen.queryByRole("button");
    expect(button).not.toBeInTheDocument();
  });

  it("renders retry button when onRetry is provided", () => {
    const mockRetry = vi.fn();
    render(<ErrorState message="Error" onRetry={mockRetry} />);

    const button = screen.getByRole("button", { name: "Try again" });
    expect(button).toBeInTheDocument();
  });

  it("calls onRetry handler when retry button is clicked", () => {
    const mockRetry = vi.fn();
    render(<ErrorState message="Error" onRetry={mockRetry} />);

    const button = screen.getByRole("button", { name: "Try again" });
    button.click();
    expect(mockRetry).toHaveBeenCalledTimes(1);
  });
});
