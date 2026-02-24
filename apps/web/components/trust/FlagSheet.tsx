"use client";

// FlagSheet — Bottom sheet triggered by the flag button on SlotCard (showFlag=true).
//
// Two paths via ResolutionPicker:
//
// Path A: "Wrong for me"
//   POST /api/signals/intention  → { intentionType: 'rejection', source: 'user_explicit', confidence: 1.0 }
//   POST /api/signals/behavioral → { signalType: 'slot_flag_preference', signalValue: -1.0 }
//
// Path B: "Wrong information"
//   POST /api/nodes/:activityNodeId/flag → { reason: 'wrong_information' }
//   → ActivityNode.status → 'flagged', queued for admin review
//
// Both paths write appropriate signals then call onComplete.
//
// Usage inside SlotCard (showFlag=true):
//   <FlagSheet
//     slot={slotData}
//     userId="uuid"
//     sessionId="session-id"
//     onComplete={() => handleFlagComplete()}
//     onDismiss={() => setShowFlagSheet(false)}
//   />

import { useState, useCallback, useEffect, useRef } from "react";
import { ResolutionPicker, type FlagPath } from "./ResolutionPicker";

// ---------- Types ----------

export interface FlagSlotData {
  id: string;
  activityNodeId: string;
  activityName: string;
  tripId: string;
  dayNumber: number;
}

export interface FlagSheetProps {
  slot: FlagSlotData;
  userId: string;
  sessionId?: string;
  onComplete: (path: FlagPath) => void;
  onDismiss: () => void;
}

type FlagState =
  | { phase: "picking" }
  | { phase: "submitting"; path: FlagPath }
  | { phase: "done"; path: FlagPath }
  | { phase: "error"; message: string };

// ---------- API helpers ----------

async function writeIntentionSignal(params: {
  userId: string;
  tripId: string;
  slotId: string;
  activityNodeId: string;
  sessionId?: string;
}): Promise<void> {
  const res = await fetch("/api/signals/intention", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId: params.userId,
      tripId: params.tripId,
      slotId: params.slotId,
      activityNodeId: params.activityNodeId,
      intentionType: "rejection",
      source: "user_explicit",
      confidence: 1.0,
      userProvided: true,
      sessionId: params.sessionId,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `Signal write failed (${res.status})`);
  }
}

async function writeBehavioralSignal(params: {
  userId: string;
  tripId: string;
  slotId: string;
  activityNodeId: string;
  sessionId?: string;
}): Promise<void> {
  const res = await fetch("/api/signals/behavioral", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId: params.userId,
      tripId: params.tripId,
      slotId: params.slotId,
      activityNodeId: params.activityNodeId,
      signalType: "slot_flag_preference",
      signalValue: -1.0,
      tripPhase: "mid_trip",
      rawAction: "flag_wrong_for_me",
      sessionId: params.sessionId,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `Behavioral signal write failed (${res.status})`);
  }
}

async function flagActivityNode(params: {
  activityNodeId: string;
  userId: string;
  tripId: string;
  slotId: string;
  reason: string;
}): Promise<void> {
  const res = await fetch(`/api/nodes/${params.activityNodeId}/flag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reason: params.reason,
      userId: params.userId,
      tripId: params.tripId,
      slotId: params.slotId,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `Node flag failed (${res.status})`);
  }
}

// ---------- Icons ----------

function FlagIcon() {
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
      <path d="M3 2v12M3 2h9l-2 4 2 4H3" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <polyline points="8 12 11 15 16 9" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="4" y1="4" x2="12" y2="12" />
      <line x1="12" y1="4" x2="4" y2="12" />
    </svg>
  );
}

// ---------- FlagSheet ----------

export function FlagSheet({
  slot,
  userId,
  sessionId,
  onComplete,
  onDismiss,
}: FlagSheetProps) {
  const [state, setState] = useState<FlagState>({ phase: "picking" });
  const overlayRef = useRef<HTMLDivElement>(null);

  // Trap focus within sheet
  useEffect(() => {
    const el = overlayRef.current;
    if (!el) return;
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    focusable[0]?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onDismiss();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onDismiss]);

  const handleChoose = useCallback(
    async (path: FlagPath) => {
      setState({ phase: "submitting", path });

      try {
        if (path === "wrong_for_me") {
          // Parallel writes: IntentionSignal + BehavioralSignal
          await Promise.all([
            writeIntentionSignal({
              userId,
              tripId: slot.tripId,
              slotId: slot.id,
              activityNodeId: slot.activityNodeId,
              sessionId,
            }),
            writeBehavioralSignal({
              userId,
              tripId: slot.tripId,
              slotId: slot.id,
              activityNodeId: slot.activityNodeId,
              sessionId,
            }),
          ]);
        } else {
          // Flag ActivityNode for admin review
          await flagActivityNode({
            activityNodeId: slot.activityNodeId,
            userId,
            tripId: slot.tripId,
            slotId: slot.id,
            reason: "wrong_information",
          });
        }

        setState({ phase: "done", path });

        // Auto-dismiss after showing confirmation
        setTimeout(() => {
          onComplete(path);
        }, 1800);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Something went wrong. Please try again.";
        setState({ phase: "error", message });
      }
    },
    [userId, slot, sessionId, onComplete]
  );

  const handleRetry = useCallback(() => {
    setState({ phase: "picking" });
  }, []);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onDismiss}
      />

      {/* Sheet */}
      <div
        ref={overlayRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Flag issue with ${slot.activityName}`}
        className="
          fixed bottom-0 left-0 right-0 z-50
          rounded-t-2xl border-t border-ink-700
          bg-surface shadow-xl
          max-w-lg mx-auto
          safe-area-inset-bottom
        "
      >
        {/* Handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-ink-700" aria-hidden="true" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 pb-4 pt-2 border-b border-ink-700">
          <div className="flex items-center gap-2 text-ink-400">
            <FlagIcon />
            <span className="font-dm-mono text-[11px] uppercase tracking-wider">
              Report an issue
            </span>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close flag sheet"
            className="
              p-1.5 rounded-lg text-ink-400
              hover:bg-base hover:text-ink-100
              transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F]
            "
          >
            <CloseIcon />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-5">
          {state.phase === "picking" && (
            <ResolutionPicker
              slotId={slot.id}
              activityNodeId={slot.activityNodeId}
              activityName={slot.activityName}
              onChoose={handleChoose}
              onDismiss={onDismiss}
            />
          )}

          {state.phase === "submitting" && (
            <div
              className="flex flex-col items-center gap-3 py-6"
              aria-live="polite"
              aria-busy="true"
            >
              <div className="w-8 h-8 border-2 border-[#C4694F] border-t-transparent rounded-full animate-spin" />
              <p className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
                {state.path === "wrong_for_me"
                  ? "Updating your preferences..."
                  : "Sending to review queue..."}
              </p>
            </div>
          )}

          {state.phase === "done" && (
            <div
              className="flex flex-col items-center gap-3 py-6 text-center"
              aria-live="polite"
            >
              <span className="text-emerald-600">
                <CheckCircleIcon />
              </span>
              <div className="space-y-1">
                <p className="font-sora font-medium text-ink-100 text-sm">
                  {state.path === "wrong_for_me"
                    ? "Got it. We'll adjust your recommendations."
                    : "Thanks. This has been sent for review."}
                </p>
                <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
                  {state.path === "wrong_for_me"
                    ? "Your preferences have been updated"
                    : "Our team will look into this"}
                </p>
              </div>
            </div>
          )}

          {state.phase === "error" && (
            <div className="space-y-4" aria-live="polite">
              <div className="rounded-lg border border-red-200 bg-error-bg px-4 py-3">
                <p className="font-dm-mono text-xs text-red-700">{state.message}</p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleRetry}
                  className="
                    flex-1 py-2.5 rounded-lg bg-[#C4694F] text-white
                    font-dm-mono text-xs uppercase tracking-wider
                    hover:bg-[#b35b42] transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F]
                  "
                >
                  Try again
                </button>
                <button
                  type="button"
                  onClick={onDismiss}
                  className="
                    flex-1 py-2.5 rounded-lg border border-ink-700 bg-surface
                    text-ink-400 font-dm-mono text-xs uppercase tracking-wider
                    hover:bg-base transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-700
                  "
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ---------- Trigger button (rendered inside SlotCard when showFlag=true) ----------

export interface FlagTriggerProps {
  onClick: () => void;
  disabled?: boolean;
}

export function FlagTrigger({ onClick, disabled = false }: FlagTriggerProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="Report an issue with this slot"
      className="
        flex items-center gap-1.5 px-3 py-1.5 rounded-lg
        border border-ink-700 bg-surface
        text-ink-400
        font-dm-mono text-[10px] uppercase tracking-wider
        hover:border-amber-400/60 hover:text-warning
        transition-all duration-150
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2
        disabled:opacity-40 disabled:cursor-not-allowed
      "
    >
      <FlagIcon />
      <span>Flag</span>
    </button>
  );
}

// Small FlagIcon variant for use in SlotCard
export function FlagIconSmall() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 2v12M3 2h9l-2 4 2 4H3" />
    </svg>
  );
}
