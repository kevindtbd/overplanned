"use client";

// PivotDrawer — Mid-trip swap card interface.
//
// Behavior:
//   - Shows original slot vs up to N alternative ActivityNodes
//   - User picks an alternative, then accepts / rejects / lets expire
//   - Writes BehavioralSignal: pivot_accepted | pivot_rejected | pivot_expired
//   - Writes RawEvent with full candidate set shown
//   - Captures PivotEvent.responseTimeMs from mount to resolution
//   - On accept: PATCH /api/slots/[slotId]/swap — updates ItinerarySlot
//     (activityNodeId = selected, wasSwapped = true, pivotEventId)
//
// Usage:
//   <PivotDrawer
//     pivotEventId="uuid"
//     slot={originalSlot}
//     alternatives={[...SwapCandidate[]]}
//     tripId="uuid"
//     tripPhase="active"
//     onClose={() => {}}
//     onResolved={(outcome) => {}}
//   />

import { useCallback, useEffect, useRef, useState } from "react";
import { SwapCard, type SwapCandidate } from "./SwapCard";
import { type SlotData } from "@/components/slot/SlotCard";
import { type VibeTagDisplay } from "@/components/slot/VibeChips";

// ---------- Types ----------

export type PivotOutcome = "accepted" | "rejected" | "expired";

export interface PivotDrawerProps {
  pivotEventId: string;
  /** The current slot being considered for a pivot */
  slot: SlotData & {
    activityNodeId?: string;
    neighborhood?: string;
    category?: string;
    priceLevel?: number;
    descriptionShort?: string;
  };
  /** Ranked alternative ActivityNodes to show */
  alternatives: SwapCandidate[];
  tripId: string;
  tripPhase?: "pre_trip" | "active" | "post_trip";
  /** Session ID for RawEvent logging */
  sessionId?: string;
  /** Timezone for display */
  timezone?: string;
  /** Trigger type for display context */
  triggerType?: "weather_change" | "venue_closed" | "time_overrun" | "user_mood" | "user_request";
  onClose: () => void;
  onResolved?: (outcome: PivotOutcome, selectedNodeId?: string) => void;
}

interface Resolution {
  outcome: PivotOutcome;
  selectedNodeId?: string;
  responseTimeMs: number;
}

// ---------- Helpers ----------

const TRIGGER_LABELS: Record<string, string> = {
  weather_change: "Weather changed",
  venue_closed: "Venue closed",
  time_overrun: "Running late",
  user_mood: "Mood shift",
  user_request: "Swap requested",
};

async function writeBehavioralSignal(body: {
  tripId: string;
  slotId: string;
  activityNodeId?: string | null;
  signalType: string;
  signalValue: number;
  tripPhase: string;
  rawAction: string;
}): Promise<void> {
  try {
    await fetch("/api/signals/behavioral", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // Non-fatal — signal logging should not block UX
  }
}

async function writeRawEvent(body: {
  userId?: string;
  sessionId: string;
  tripId: string;
  activityNodeId?: string | null;
  clientEventId: string;
  eventType: string;
  intentClass: string;
  surface: string;
  payload: Record<string, unknown>;
}): Promise<void> {
  try {
    // RawEvents go to the FastAPI service via the Next.js proxy
    await fetch("/api/events/raw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // Non-fatal
  }
}

async function swapSlot(
  slotId: string,
  pivotEventId: string,
  selectedNodeId: string,
): Promise<void> {
  const res = await fetch(`/api/slots/${slotId}/swap`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pivotEventId, selectedNodeId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error ?? "Swap request failed");
  }
}

// ---------- Sub-components ----------

function TriggerBanner({ triggerType }: { triggerType?: string }) {
  if (!triggerType) return null;
  const label = TRIGGER_LABELS[triggerType] ?? triggerType.replace("_", " ");
  return (
    <div className="
      flex items-center gap-2 px-4 py-2
      bg-warning-bg border-b border-amber-200
    ">
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-warning shrink-0"
        aria-hidden="true"
      >
        <path d="M8 2L1.5 13.5h13L8 2z" />
        <line x1="8" y1="7" x2="8" y2="10" />
        <circle cx="8" cy="12" r="0.5" fill="currentColor" />
      </svg>
      <span className="font-dm-mono text-[11px] uppercase tracking-wider text-warning">
        {label}
      </span>
    </div>
  );
}

function ActionBar({
  selectedNodeId,
  isSubmitting,
  onAccept,
  onReject,
}: {
  selectedNodeId?: string;
  isSubmitting: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const hasSelection = Boolean(selectedNodeId);

  return (
    <div className="
      flex items-center gap-3 p-4
      border-t border-ink-700 bg-surface
    ">
      {/* Reject */}
      <button
        type="button"
        onClick={onReject}
        disabled={isSubmitting}
        className="
          flex items-center gap-1.5 px-4 py-2 rounded-lg
          font-dm-mono text-xs uppercase tracking-wider
          border border-ink-700
          bg-base text-ink-400
          hover:border-red-300 hover:text-error
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:opacity-40 disabled:cursor-not-allowed
        "
        aria-label="Keep current slot"
      >
        <svg
          width="14"
          height="14"
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
        Keep current
      </button>

      {/* Accept */}
      <button
        type="button"
        onClick={onAccept}
        disabled={!hasSelection || isSubmitting}
        className={`
          flex-1 flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg
          font-dm-mono text-xs uppercase tracking-wider
          transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:opacity-40 disabled:cursor-not-allowed
          ${hasSelection
            ? "bg-accent text-white hover:bg-accent-fg border border-accent-fg"
            : "bg-base text-ink-400 border border-ink-700"
          }
        `}
        aria-label={hasSelection ? "Accept selected alternative" : "Select an alternative first"}
      >
        {isSubmitting ? (
          <>
            <svg
              className="animate-spin"
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M8 2a6 6 0 110 12A6 6 0 018 2z" strokeDasharray="20" strokeDashoffset="5" strokeLinecap="round" />
            </svg>
            Swapping...
          </>
        ) : (
          <>
            <svg
              width="14"
              height="14"
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
            {hasSelection ? "Swap to this" : "Select an option"}
          </>
        )}
      </button>
    </div>
  );
}

// ---------- Main component ----------

export function PivotDrawer({
  pivotEventId,
  slot,
  alternatives,
  tripId,
  tripPhase = "active",
  sessionId,
  timezone,
  triggerType,
  onClose,
  onResolved,
}: PivotDrawerProps) {
  const openedAt = useRef<number>(Date.now());
  const [selectedNodeId, setSelectedNodeId] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<Resolution | null>(null);

  // Build original slot as SwapCandidate
  const originalCandidate: SwapCandidate = {
    activityNodeId: slot.activityNodeId ?? slot.id,
    activityName: slot.activityName,
    imageUrl: slot.imageUrl,
    neighborhood: slot.neighborhood,
    category: slot.category ?? slot.slotType,
    priceLevel: slot.priceLevel,
    durationMinutes: slot.durationMinutes,
    vibeTags: slot.vibeTags,
    descriptionShort: slot.descriptionShort,
  };

  // Log the candidate set as a RawEvent on mount
  useEffect(() => {
    const sid = sessionId ?? "pivot-session";
    writeRawEvent({
      sessionId: sid,
      tripId,
      activityNodeId: slot.activityNodeId,
      clientEventId: `pivot-shown-${pivotEventId}`,
      eventType: "pivot_candidates_shown",
      intentClass: "contextual",
      surface: "pivot_drawer",
      payload: {
        pivotEventId,
        slotId: slot.id,
        originalNodeId: slot.activityNodeId,
        alternativeIds: alternatives.map((a) => a.activityNodeId),
        candidateCount: alternatives.length,
        triggerType,
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-expire: if user hasn't acted within 5 minutes, record expiry
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (!resolved) {
        const responseTimeMs = Date.now() - openedAt.current;
        await handleResolve("expired", undefined, responseTimeMs);
      }
    }, 5 * 60 * 1000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved]);

  // ---------- Resolution logic ----------

  const handleResolve = useCallback(
    async (
      outcome: PivotOutcome,
      chosenNodeId?: string,
      overrideMs?: number,
    ) => {
      if (resolved) return;
      const responseTimeMs = overrideMs ?? Date.now() - openedAt.current;
      const resolution: Resolution = { outcome, selectedNodeId: chosenNodeId, responseTimeMs };
      setResolved(resolution);

      const sid = sessionId ?? "pivot-session";

      // Map outcome to SignalType
      const signalType =
        outcome === "accepted"
          ? "pivot_accepted"
          : outcome === "rejected"
          ? "pivot_rejected"
          : "pivot_rejected"; // expired maps to rejected signal

      const signalValue =
        outcome === "accepted" ? 1.0 : outcome === "rejected" ? -0.3 : 0.0;

      // 1. Write BehavioralSignal
      await writeBehavioralSignal({
        tripId,
        slotId: slot.id,
        activityNodeId: chosenNodeId ?? slot.activityNodeId,
        signalType,
        signalValue,
        tripPhase,
        rawAction: `pivot_drawer_${outcome}`,
      });

      // 2. Write RawEvent with resolution details
      await writeRawEvent({
        sessionId: sid,
        tripId,
        activityNodeId: chosenNodeId ?? slot.activityNodeId,
        clientEventId: `pivot-resolved-${pivotEventId}`,
        eventType: "pivot_resolved",
        intentClass: "explicit",
        surface: "pivot_drawer",
        payload: {
          pivotEventId,
          slotId: slot.id,
          originalNodeId: slot.activityNodeId,
          selectedNodeId: chosenNodeId,
          outcome,
          responseTimeMs,
          alternativeIds: alternatives.map((a) => a.activityNodeId),
        },
      });

      // 3. PATCH slot on accept
      if (outcome === "accepted" && chosenNodeId) {
        try {
          await swapSlot(slot.id, pivotEventId, chosenNodeId);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Swap failed");
          setResolved(null);
          return;
        }
      }

      onResolved?.(outcome, chosenNodeId);
      onClose();
    },
    [resolved, sessionId, tripId, slot, tripPhase, pivotEventId, alternatives, onResolved, onClose],
  );

  const handleAccept = useCallback(async () => {
    if (!selectedNodeId || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    await handleResolve("accepted", selectedNodeId);
    setIsSubmitting(false);
  }, [selectedNodeId, isSubmitting, handleResolve]);

  const handleReject = useCallback(async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    await handleResolve("rejected");
    setIsSubmitting(false);
  }, [isSubmitting, handleResolve]);

  // Trap focus inside drawer
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = drawerRef.current;
    if (!el) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        handleReject();
      }
      if (e.key === "Tab") {
        const focusable = el!.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }
      }
    }

    el.addEventListener("keydown", handleKeyDown);
    return () => el.removeEventListener("keydown", handleKeyDown);
  }, [handleReject]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] transition-opacity"
        aria-hidden="true"
        onClick={() => handleReject()}
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Swap slot"
        className="
          fixed bottom-0 left-0 right-0 z-50
          md:top-0 md:bottom-0 md:right-0 md:left-auto md:w-[480px]
          flex flex-col
          bg-base
          rounded-t-2xl md:rounded-l-2xl md:rounded-r-none
          shadow-[0_-4px_40px_rgba(0,0,0,0.16)] md:shadow-[-4px_0_40px_rgba(0,0,0,0.12)]
          max-h-[90dvh] md:max-h-full
          overflow-hidden
          animate-[drawer-in_0.25s_ease-out_both]
        "
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-ink-700 shrink-0">
          <div>
            <h2 className="font-sora font-semibold text-base text-ink-100">
              Swap this stop?
            </h2>
            <p className="font-dm-mono text-[11px] uppercase tracking-wider text-ink-400 mt-0.5">
              {alternatives.length} alternative{alternatives.length !== 1 ? "s" : ""} found
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleReject()}
            className="
              p-2 rounded-lg
              text-ink-400
              hover:text-ink-100 hover:bg-surface
              transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
            "
            aria-label="Close pivot drawer"
          >
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
          </button>
        </div>

        {/* Trigger context */}
        <TriggerBanner triggerType={triggerType} />

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="mx-4 mt-3 px-3 py-2 rounded-lg bg-error-bg border border-red-200 text-red-700 font-dm-mono text-[11px]"
          >
            {error}
          </div>
        )}

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto overscroll-contain">
          <div className="p-4 space-y-4">
            {/* Current slot */}
            <section aria-labelledby="current-heading">
              <h3
                id="current-heading"
                className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400 mb-2"
              >
                Currently scheduled
              </h3>
              <SwapCard
                side="original"
                candidate={originalCandidate}
              />
            </section>

            {/* Divider with swap icon */}
            <div className="flex items-center gap-3">
              <div className="flex-1 border-t border-ink-700" />
              <div className="
                w-7 h-7 rounded-full
                border border-ink-700 bg-surface
                flex items-center justify-center
                text-ink-400
              ">
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
                  <polyline points="5 10 8 13 11 10" />
                  <polyline points="5 6 8 3 11 6" />
                  <line x1="8" y1="3" x2="8" y2="13" />
                </svg>
              </div>
              <div className="flex-1 border-t border-ink-700" />
            </div>

            {/* Alternatives */}
            <section aria-labelledby="alternatives-heading">
              <h3
                id="alternatives-heading"
                className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400 mb-2"
              >
                Alternatives nearby
              </h3>

              {alternatives.length === 0 ? (
                <div className="
                  p-6 rounded-xl border border-dashed border-ink-700
                  text-center
                  font-dm-mono text-[12px] text-ink-400 uppercase tracking-wider
                ">
                  No alternatives available right now
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {alternatives.map((alt) => (
                    <SwapCard
                      key={alt.activityNodeId}
                      side="alternative"
                      candidate={alt}
                      isSelected={selectedNodeId === alt.activityNodeId}
                      onClick={() => {
                        setSelectedNodeId(
                          selectedNodeId === alt.activityNodeId
                            ? undefined
                            : alt.activityNodeId,
                        );
                      }}
                    />
                  ))}
                </div>
              )}
            </section>

            {/* Bottom padding for action bar */}
            <div className="h-2" aria-hidden="true" />
          </div>
        </div>

        {/* Action bar */}
        <ActionBar
          selectedNodeId={selectedNodeId}
          isSubmitting={isSubmitting}
          onAccept={handleAccept}
          onReject={handleReject}
        />
      </div>

      <style>{`
        @keyframes drawer-in {
          from { transform: translateY(100%); }
          to { transform: translateY(0); }
        }
        @media (min-width: 768px) {
          @keyframes drawer-in {
            from { transform: translateX(100%); }
            to { transform: translateX(0); }
          }
        }
      `}</style>
    </>
  );
}
