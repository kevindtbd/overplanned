import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/states/EmptyState";

describe("EmptyState", () => {
  it("renders icon, title, and description", () => {
    const mockIcon = <div data-testid="test-icon">Icon</div>;
    render(
      <EmptyState
        icon={mockIcon}
        title="No trips yet"
        description="Start planning your first adventure"
      />
    );

    expect(screen.getByTestId("test-icon")).toBeInTheDocument();
    expect(screen.getByText("No trips yet")).toBeInTheDocument();
    expect(screen.getByText("Start planning your first adventure")).toBeInTheDocument();
  });

  it("renders without action button when action is not provided", () => {
    const mockIcon = <div>Icon</div>;
    render(
      <EmptyState
        icon={mockIcon}
        title="Empty state"
        description="No action available"
      />
    );

    const button = screen.queryByRole("button");
    expect(button).not.toBeInTheDocument();
  });

  it("renders action button when action is provided", () => {
    const mockIcon = <div>Icon</div>;
    const mockOnClick = vi.fn();
    render(
      <EmptyState
        icon={mockIcon}
        title="Empty state"
        description="Click to start"
        action={{ label: "Get started", onClick: mockOnClick }}
      />
    );

    const button = screen.getByRole("button", { name: "Get started" });
    expect(button).toBeInTheDocument();
  });

  it("calls onClick handler when action button is clicked", () => {
    const mockIcon = <div>Icon</div>;
    const mockOnClick = vi.fn();
    render(
      <EmptyState
        icon={mockIcon}
        title="Empty state"
        description="Click to start"
        action={{ label: "Start now", onClick: mockOnClick }}
      />
    );

    const button = screen.getByRole("button", { name: "Start now" });
    button.click();
    expect(mockOnClick).toHaveBeenCalledTimes(1);
  });

  it("applies correct styling classes", () => {
    const mockIcon = <div>Icon</div>;
    const { container } = render(
      <EmptyState
        icon={mockIcon}
        title="Test title"
        description="Test description"
      />
    );

    const wrapper = container.firstElementChild;
    expect(wrapper).toHaveClass("flex", "flex-col", "items-center", "justify-center");
  });
});
