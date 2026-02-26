"use client";

// RemovalReasonPicker — Bottom-sheet picker for WHY a user is removing a slot.
// Shown on pre-trip skip only. Selecting a reason dismisses the sheet and fires
// the skip action with a weighted negative signal.
//
// Mobile: bottom sheet (items-end, rounded-t-2xl)
// Desktop: centered modal (sm:items-center, sm:rounded-2xl)

import { useState } from "react";
import {
  REMOVAL_REASONS,
  DEFAULT_REMOVAL_REASON,
  type RemovalReason,
} from "@/lib/constants/removal-reasons";

interface Props {
  open: boolean;
  onSelect: (reason: RemovalReason) => void;
  onClose: () => void;
  activityName?: string;
}

export function RemovalReasonPicker({
  open,
  onSelect,
  onClose,
  activityName,
}: Props) {
  const [selected, setSelected] = useState<RemovalReason | null>(null);

  if (!open) return null;

  function handleBackdropClick() {
    onSelect(DEFAULT_REMOVAL_REASON);
  }

  function handleConfirm() {
    onSelect(selected ?? DEFAULT_REMOVAL_REASON);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
      data-testid="removal-reason-picker"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={handleBackdropClick}
        data-testid="removal-backdrop"
      />

      {/* Panel */}
      <div className="relative w-full max-w-md rounded-t-2xl bg-base p-6 sm:rounded-2xl">
        <h3 className="font-sora text-lg text-ink-100">Why skip this?</h3>
        {activityName && (
          <p className="mt-1 font-dm-mono text-xs text-ink-400">
            Removing: {activityName}
          </p>
        )}

        <div className="mt-4 space-y-2">
          {REMOVAL_REASONS.map((reason) => (
            <button
              key={reason.id}
              type="button"
              onClick={() => setSelected(reason.id)}
              className={`
                w-full flex items-center gap-3 px-4 py-3 rounded-xl
                font-dm-mono text-sm text-left
                transition-all duration-150
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2
                ${
                  selected === reason.id
                    ? "border-2 border-accent bg-accent/5 text-ink-100"
                    : "border border-ink-700 bg-surface text-ink-300 hover:border-ink-500"
                }
              `}
              data-testid={`reason-${reason.id}`}
            >
              {/* Radio indicator */}
              <span
                className={`
                  flex-shrink-0 w-4 h-4 rounded-full border-2
                  ${
                    selected === reason.id
                      ? "border-accent bg-accent"
                      : "border-ink-500"
                  }
                `}
              >
                {selected === reason.id && (
                  <span className="block w-full h-full rounded-full ring-2 ring-base ring-inset" />
                )}
              </span>
              <span>{reason.label}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-ink-700 px-4 py-2 font-dm-mono text-xs text-ink-300 hover:bg-surface"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="flex-1 rounded-lg bg-accent px-4 py-2 font-dm-mono text-xs text-white transition hover:bg-accent/90"
          >
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}
