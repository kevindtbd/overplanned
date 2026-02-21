"use client";

// SlotActions — Confirm / Skip / Lock action buttons for a slot card.
// Emits BehavioralSignal-shaped callbacks. Used inside SlotCard.
// Usage: <SlotActions slotId="abc" status="proposed" onAction={handleAction} />

export type SlotActionType = "confirm" | "skip" | "lock";

export interface SlotActionEvent {
  slotId: string;
  action: SlotActionType;
  /** Maps to BehavioralSignal.signalType */
  signalType: "slot_confirm" | "slot_skip" | "slot_complete";
  /** Maps to BehavioralSignal.signalValue */
  signalValue: number;
}

interface SlotActionsProps {
  slotId: string;
  status: "proposed" | "voted" | "confirmed" | "active" | "completed" | "skipped";
  isLocked: boolean;
  onAction: (event: SlotActionEvent) => void;
  disabled?: boolean;
}

// SVG icons rendered inline per design system (no icon libraries)
function CheckIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />
    </svg>
  );
}

function SkipIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="4" y1="4" x2="12" y2="12" />
      <line x1="12" y1="4" x2="4" y2="12" />
    </svg>
  );
}

function LockIcon({ locked }: { locked: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {locked ? (
        <>
          <rect x="3.5" y="7" width="9" height="7" rx="1" />
          <path d="M5.5 7V5a2.5 2.5 0 015 0v2" />
        </>
      ) : (
        <>
          <rect x="3.5" y="7" width="9" height="7" rx="1" />
          <path d="M5.5 7V5a2.5 2.5 0 015 0" />
        </>
      )}
    </svg>
  );
}

export function SlotActions({
  slotId,
  status,
  isLocked,
  onAction,
  disabled = false,
}: SlotActionsProps) {
  const isTerminal = status === "completed" || status === "skipped";

  function handleConfirm() {
    onAction({
      slotId,
      action: "confirm",
      signalType: "slot_confirm",
      signalValue: 1.0,
    });
  }

  function handleSkip() {
    onAction({
      slotId,
      action: "skip",
      signalType: "slot_skip",
      signalValue: -0.5,
    });
  }

  function handleLock() {
    onAction({
      slotId,
      action: "lock",
      signalType: "slot_complete",
      signalValue: isLocked ? 0 : 1.0,
    });
  }

  return (
    <div className="flex items-center gap-2" role="group" aria-label="Slot actions">
      {/* Confirm */}
      <button
        type="button"
        onClick={handleConfirm}
        disabled={disabled || isTerminal || status === "confirmed"}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-lg
          font-dm-mono text-xs uppercase tracking-wider
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:opacity-40 disabled:cursor-not-allowed
          ${
            status === "confirmed"
              ? "bg-[var(--success-bg)] text-success border border-[var(--success)]"
              : "bg-surface text-ink-100 border border-ink-700 hover:border-[var(--success)] hover:text-success"
          }
        `}
        aria-label="Confirm this slot"
      >
        <CheckIcon />
        <span>{status === "confirmed" ? "Confirmed" : "Confirm"}</span>
      </button>

      {/* Skip */}
      <button
        type="button"
        onClick={handleSkip}
        disabled={disabled || isTerminal || isLocked}
        className="
          flex items-center gap-1.5 px-3 py-1.5 rounded-lg
          font-dm-mono text-xs uppercase tracking-wider
          bg-surface text-ink-400 border border-ink-700
          hover:border-[var(--error)] hover:text-error
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:opacity-40 disabled:cursor-not-allowed
        "
        aria-label="Skip this slot"
      >
        <SkipIcon />
        <span>Skip</span>
      </button>

      {/* Lock */}
      <button
        type="button"
        onClick={handleLock}
        disabled={disabled || isTerminal}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-lg
          font-dm-mono text-xs uppercase tracking-wider
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:opacity-40 disabled:cursor-not-allowed
          ${
            isLocked
              ? "bg-[var(--warning-bg)] text-warning border border-[var(--warning)]"
              : "bg-surface text-ink-400 border border-ink-700 hover:border-[var(--warning)] hover:text-warning"
          }
        `}
        aria-label={isLocked ? "Unlock this slot" : "Lock this slot"}
      >
        <LockIcon locked={isLocked} />
        <span>{isLocked ? "Locked" : "Lock"}</span>
      </button>
    </div>
  );
}
