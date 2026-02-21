"use client";

// ResolutionPicker — Choice between two flag resolution paths.
//
// Path A: "Wrong for me"
//   → Writes IntentionSignal (source: user_explicit, confidence: 1.0) + BehavioralSignal
//   → Signals feed persona model to improve future recommendations
//
// Path B: "Wrong information"
//   → Flags the ActivityNode for admin review queue
//   → Used for factual errors: wrong hours, closed permanently, wrong location
//
// Usage:
//   <ResolutionPicker
//     slotId="uuid"
//     activityNodeId="uuid"
//     activityName="Tsukiji Outer Market"
//     onChoose={(path) => handlePath(path)}
//     onDismiss={() => closeSheet()}
//   />

export type FlagPath = "wrong_for_me" | "wrong_information";

export interface ResolutionPickerProps {
  slotId: string;
  activityNodeId: string;
  activityName: string;
  /** Called when user selects a path — parent handles the actual API calls */
  onChoose: (path: FlagPath) => void;
  /** Called when user dismisses without choosing */
  onDismiss: () => void;
}

// ---------- Icons ----------

function PersonIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="10" cy="6" r="3.5" />
      <path d="M2 17c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10 3L2 17h16L10 3z" />
      <line x1="10" y1="11" x2="10" y2="13" />
      <circle cx="10" cy="15.5" r="0.5" fill="currentColor" />
    </svg>
  );
}

function ChevronRightIcon() {
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
      <polyline points="6 4 10 8 6 12" />
    </svg>
  );
}

// ---------- Component ----------

export function ResolutionPicker({
  slotId: _slotId,
  activityNodeId: _activityNodeId,
  activityName,
  onChoose,
  onDismiss,
}: ResolutionPickerProps) {
  return (
    <div className="space-y-3" role="group" aria-label="Choose what's wrong">
      {/* Heading */}
      <div className="space-y-1">
        <p className="font-sora font-semibold text-ink-100 text-sm">
          What's the issue with {activityName}?
        </p>
        <p className="font-dm-mono text-[11px] text-ink-400 uppercase tracking-wider">
          Your feedback improves future recommendations
        </p>
      </div>

      {/* Path A — Wrong for me */}
      <button
        type="button"
        onClick={() => onChoose("wrong_for_me")}
        className="
          w-full flex items-center gap-3 p-4 rounded-xl
          border border-ink-700 bg-surface
          hover:border-[#C4694F]/40 hover:bg-base
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2
          text-left group
        "
        aria-label="Flag as wrong for me — not my style"
      >
        <span className="text-ink-400 group-hover:text-[#C4694F] transition-colors">
          <PersonIcon />
        </span>

        <div className="flex-1 space-y-0.5">
          <p className="font-sora font-medium text-ink-100 text-sm">
            Wrong for me
          </p>
          <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
            Not my style, not what I'm into right now
          </p>
        </div>

        <span className="text-ink-400 group-hover:text-[#C4694F] transition-colors">
          <ChevronRightIcon />
        </span>
      </button>

      {/* Path B — Wrong information */}
      <button
        type="button"
        onClick={() => onChoose("wrong_information")}
        className="
          w-full flex items-center gap-3 p-4 rounded-xl
          border border-ink-700 bg-surface
          hover:border-amber-400/60 hover:bg-warning-bg/30
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2
          text-left group
        "
        aria-label="Flag as wrong information — factual error"
      >
        <span className="text-ink-400 group-hover:text-warning transition-colors">
          <AlertIcon />
        </span>

        <div className="flex-1 space-y-0.5">
          <p className="font-sora font-medium text-ink-100 text-sm">
            Wrong information
          </p>
          <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
            Wrong hours, closed, wrong location, factual error
          </p>
        </div>

        <span className="text-ink-400 group-hover:text-warning transition-colors">
          <ChevronRightIcon />
        </span>
      </button>

      {/* Dismiss */}
      <button
        type="button"
        onClick={onDismiss}
        className="
          w-full py-2 font-dm-mono text-[11px] text-ink-400 uppercase tracking-wider
          hover:text-ink-100 transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-700 focus-visible:ring-offset-2
          rounded
        "
      >
        Cancel
      </button>
    </div>
  );
}
