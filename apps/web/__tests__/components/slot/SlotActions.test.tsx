import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SlotActions } from "../../../components/slot/SlotActions";

const defaultProps = {
  slotId: "a1b2c3d4-e5f6-4a7b-8c9d-000000000001",
  status: "proposed" as const,
  isLocked: false,
  onAction: vi.fn(),
};

describe("SlotActions", () => {
  describe("pre-trip skip with removal picker", () => {
    it("shows removal picker when skip is clicked in pre_trip phase", () => {
      render(<SlotActions {...defaultProps} tripPhase="pre_trip" />);

      fireEvent.click(screen.getByLabelText("Skip this slot"));

      // Picker should appear
      expect(screen.getByTestId("removal-reason-picker")).toBeInTheDocument();
      // onAction should NOT have been called yet
      expect(defaultProps.onAction).not.toHaveBeenCalled();
    });

    it("fires onAction with removalReason after picker selection", () => {
      const onAction = vi.fn();
      render(
        <SlotActions {...defaultProps} onAction={onAction} tripPhase="pre_trip" />
      );

      // Click skip to open picker
      fireEvent.click(screen.getByLabelText("Skip this slot"));

      // Select a reason
      fireEvent.click(screen.getByTestId("reason-too_far"));
      // Multiple "Skip" texts exist — use getAllByText and pick the picker's confirm button
      const skipButtons = screen.getAllByText("Skip");
      // The second "Skip" is the picker's confirm button
      fireEvent.click(skipButtons[1]);

      expect(onAction).toHaveBeenCalledOnce();
      expect(onAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action: "skip",
          removalReason: "too_far",
        })
      );
    });

    it("skips immediately (no picker) when tripPhase is active", () => {
      const onAction = vi.fn();
      render(
        <SlotActions {...defaultProps} onAction={onAction} tripPhase="active" />
      );

      fireEvent.click(screen.getByLabelText("Skip this slot"));

      // Should fire immediately without picker
      expect(onAction).toHaveBeenCalledOnce();
      expect(onAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action: "skip",
          signalType: "slot_skip",
          signalValue: -0.5,
        })
      );
      // No removalReason on non-pre-trip skips
      expect(onAction.mock.calls[0][0].removalReason).toBeUndefined();
    });

    it("skips immediately when tripPhase is undefined", () => {
      const onAction = vi.fn();
      render(<SlotActions {...defaultProps} onAction={onAction} />);

      fireEvent.click(screen.getByLabelText("Skip this slot"));

      expect(onAction).toHaveBeenCalledOnce();
      expect(onAction.mock.calls[0][0].removalReason).toBeUndefined();
    });

    it("passes activityName to picker", () => {
      render(
        <SlotActions
          {...defaultProps}
          tripPhase="pre_trip"
          activityName="Ramen Shop"
        />
      );

      fireEvent.click(screen.getByLabelText("Skip this slot"));

      expect(screen.getByText("Removing: Ramen Shop")).toBeInTheDocument();
    });

    it("closes picker on Cancel without firing onAction", () => {
      const onAction = vi.fn();
      render(
        <SlotActions {...defaultProps} onAction={onAction} tripPhase="pre_trip" />
      );

      fireEvent.click(screen.getByLabelText("Skip this slot"));
      expect(screen.getByTestId("removal-reason-picker")).toBeInTheDocument();

      fireEvent.click(screen.getByText("Cancel"));

      expect(screen.queryByTestId("removal-reason-picker")).not.toBeInTheDocument();
      expect(onAction).not.toHaveBeenCalled();
    });
  });

  describe("non-skip actions unaffected", () => {
    it("confirm fires immediately in pre_trip", () => {
      const onAction = vi.fn();
      render(
        <SlotActions {...defaultProps} onAction={onAction} tripPhase="pre_trip" />
      );

      fireEvent.click(screen.getByLabelText("Confirm this slot"));

      expect(onAction).toHaveBeenCalledOnce();
      expect(onAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action: "confirm",
          signalType: "slot_confirm",
        })
      );
    });

    it("lock fires immediately in pre_trip", () => {
      const onAction = vi.fn();
      render(
        <SlotActions {...defaultProps} onAction={onAction} tripPhase="pre_trip" />
      );

      fireEvent.click(screen.getByLabelText("Lock this slot"));

      expect(onAction).toHaveBeenCalledOnce();
      expect(onAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action: "lock",
        })
      );
    });
  });
});
