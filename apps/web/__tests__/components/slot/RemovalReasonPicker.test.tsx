import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RemovalReasonPicker } from "../../../components/slot/RemovalReasonPicker";

describe("RemovalReasonPicker", () => {
  it("renders nothing when open=false", () => {
    const { container } = render(
      <RemovalReasonPicker open={false} onSelect={vi.fn()} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders 4 reason options when open", () => {
    render(
      <RemovalReasonPicker open={true} onSelect={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("reason-not_interested")).toBeInTheDocument();
    expect(screen.getByTestId("reason-wrong_vibe")).toBeInTheDocument();
    expect(screen.getByTestId("reason-already_been")).toBeInTheDocument();
    expect(screen.getByTestId("reason-too_far")).toBeInTheDocument();
  });

  it("displays activity name when provided", () => {
    render(
      <RemovalReasonPicker
        open={true}
        onSelect={vi.fn()}
        onClose={vi.fn()}
        activityName="Ramen Shop"
      />
    );
    expect(screen.getByText("Removing: Ramen Shop")).toBeInTheDocument();
  });

  it("fires onSelect with chosen reason when Skip is clicked", () => {
    const onSelect = vi.fn();
    render(
      <RemovalReasonPicker open={true} onSelect={onSelect} onClose={vi.fn()} />
    );

    fireEvent.click(screen.getByTestId("reason-wrong_vibe"));
    fireEvent.click(screen.getByText("Skip"));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("wrong_vibe");
  });

  it("fires onSelect with default reason when Skip is clicked without selecting", () => {
    const onSelect = vi.fn();
    render(
      <RemovalReasonPicker open={true} onSelect={onSelect} onClose={vi.fn()} />
    );

    fireEvent.click(screen.getByText("Skip"));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("not_interested");
  });

  it("fires onSelect with default reason on backdrop click", () => {
    const onSelect = vi.fn();
    render(
      <RemovalReasonPicker open={true} onSelect={onSelect} onClose={vi.fn()} />
    );

    fireEvent.click(screen.getByTestId("removal-backdrop"));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("not_interested");
  });

  it("fires onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(
      <RemovalReasonPicker open={true} onSelect={vi.fn()} onClose={onClose} />
    );

    fireEvent.click(screen.getByText("Cancel"));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows heading text", () => {
    render(
      <RemovalReasonPicker open={true} onSelect={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText("Why skip this?")).toBeInTheDocument();
  });
});
