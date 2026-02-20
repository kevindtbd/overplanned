"use client";

import { useState, useEffect, useCallback, useRef } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ItinerarySlot {
  id: string;
  dayNumber: number;
  timeSlot: string;
  title: string;
  neighborhood: string;
  category: string;
  durationMinutes: number;
}

interface GenerationStatus {
  status: "generating" | "completed" | "failed";
  progress: number; // 0-100
  slots: ItinerarySlot[];
  error?: string;
}

interface RevealAnimationProps {
  tripId: string;
  tripName: string;
  destination: string;
  onComplete: (slots: ItinerarySlot[]) => void;
  onRetry: () => void;
}

// ─── SVG Icons (no icon libraries) ───────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className ?? ""}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        opacity={0.2}
      />
      <path
        d="M12 2a10 10 0 019.95 9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function AlertIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
    </svg>
  );
}

function MapPinIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

// ─── Skeleton Card ───────────────────────────────────────────────────────────

function SkeletonCard({ index }: { index: number }) {
  return (
    <div
      className="card animate-pulse"
      style={{ animationDelay: `${index * 120}ms` }}
      aria-hidden="true"
    >
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-lg bg-warm-border" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-3/4 rounded bg-warm-border" />
          <div className="h-3 w-1/2 rounded bg-warm-border" />
          <div className="flex gap-2">
            <div className="h-3 w-16 rounded bg-warm-border" />
            <div className="h-3 w-20 rounded bg-warm-border" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Revealed Slot Card ──────────────────────────────────────────────────────

function SlotCard({
  slot,
  index,
  isNew,
}: {
  slot: ItinerarySlot;
  index: number;
  isNew: boolean;
}) {
  const formatDuration = (mins: number) => {
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  };

  return (
    <div
      className={`
        card transition-all duration-500
        ${isNew ? "animate-slot-reveal" : ""}
      `}
      style={{
        animationDelay: isNew ? `${index * 80}ms` : "0ms",
      }}
      role="listitem"
    >
      <div className="flex items-start gap-3">
        {/* Time slot indicator */}
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-terracotta/10 text-terracotta">
          <span className="font-dm-mono text-xs font-medium">
            {slot.timeSlot}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-sora text-sm font-semibold text-primary truncate">
            {slot.title}
          </h4>

          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1 font-dm-mono text-xs text-secondary">
              <MapPinIcon className="h-3 w-3" />
              {slot.neighborhood}
            </span>
            <span className="inline-flex items-center gap-1 font-dm-mono text-xs text-secondary">
              <ClockIcon className="h-3 w-3" />
              {formatDuration(slot.durationMinutes)}
            </span>
          </div>

          <span className="mt-2 inline-block rounded-full bg-warm-border px-2 py-0.5 font-dm-mono text-[10px] uppercase tracking-wider text-secondary">
            {slot.category}
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Progress Indicator ──────────────────────────────────────────────────────

function ProgressBar({ progress }: { progress: number }) {
  return (
    <div className="w-full" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
      <div className="flex items-center justify-between mb-2">
        <span className="label-mono">Building your itinerary</span>
        <span className="font-dm-mono text-xs text-terracotta font-medium">
          {progress}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-warm-border">
        <div
          className="h-full rounded-full bg-terracotta transition-all duration-700 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

// ─── Status Messages ─────────────────────────────────────────────────────────

const STATUS_MESSAGES = [
  "Sourcing local intelligence...",
  "Analyzing neighborhood vibes...",
  "Finding hidden gems...",
  "Optimizing your route...",
  "Mapping walking distances...",
  "Checking seasonal availability...",
  "Curating food recommendations...",
  "Balancing your pace...",
  "Finalizing your itinerary...",
];

function RotatingStatus() {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % STATUS_MESSAGES.length);
    }, 3200);
    return () => clearInterval(interval);
  }, []);

  return (
    <p
      className="font-dm-mono text-sm text-secondary transition-opacity duration-300"
      aria-live="polite"
    >
      {STATUS_MESSAGES[messageIndex]}
    </p>
  );
}

// ─── Error State ─────────────────────────────────────────────────────────────

function ErrorState({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-12 text-center" role="alert">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-50 dark:bg-red-950/30">
        <AlertIcon className="h-7 w-7 text-red-500" />
      </div>
      <div>
        <h3 className="font-sora text-lg font-semibold text-primary">
          Generation failed
        </h3>
        <p className="mt-1 max-w-sm font-dm-mono text-sm text-secondary">
          {error || "Something went wrong while building your itinerary. Give it another shot."}
        </p>
      </div>
      <button
        onClick={onRetry}
        className="btn-primary mt-2 flex items-center gap-2"
      >
        <RefreshIcon className="h-4 w-4" />
        <span>Try again</span>
      </button>
    </div>
  );
}

// ─── Completion State ────────────────────────────────────────────────────────

function CompletionBanner({ slotCount }: { slotCount: number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-terracotta/20 bg-terracotta/5 p-4">
      <CheckCircleIcon className="h-5 w-5 flex-shrink-0 text-terracotta" />
      <div>
        <p className="font-sora text-sm font-semibold text-primary">
          Itinerary ready
        </p>
        <p className="font-dm-mono text-xs text-secondary">
          {slotCount} activities planned
        </p>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 2000;

export function RevealAnimation({
  tripId,
  tripName,
  destination,
  onComplete,
  onRetry,
}: RevealAnimationProps) {
  const [status, setStatus] = useState<GenerationStatus>({
    status: "generating",
    progress: 0,
    slots: [],
  });
  const [revealedCount, setRevealedCount] = useState(0);
  const [isRevealing, setIsRevealing] = useState(false);
  const previousSlotCountRef = useRef(0);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const completionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Poll generation status ──
  const pollStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/trips/${tripId}/generation-status`);
      if (!res.ok) {
        throw new Error(`Status check failed: ${res.status}`);
      }
      const data: GenerationStatus = await res.json();
      setStatus(data);
    } catch {
      // Network error — keep polling, do not immediately fail
      // After enough retries the server status will reflect failure
    }
  }, [tripId]);

  useEffect(() => {
    // Initial poll
    pollStatus();

    // Set up recurring poll
    const poll = () => {
      pollTimeoutRef.current = setTimeout(async () => {
        await pollStatus();
        poll();
      }, POLL_INTERVAL_MS);
    };
    poll();

    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, [pollStatus]);

  // ── Progressive reveal: stagger new slots into view ──
  useEffect(() => {
    const newSlotCount = status.slots.length;
    if (newSlotCount > previousSlotCountRef.current) {
      setIsRevealing(true);
      // Reveal slots one by one with stagger
      const slotsToReveal = newSlotCount - previousSlotCountRef.current;
      const revealDelay = 80; // ms per slot stagger

      const timer = setTimeout(() => {
        setRevealedCount(newSlotCount);
        setIsRevealing(false);
      }, slotsToReveal * revealDelay + 500);

      setRevealedCount(newSlotCount);
      previousSlotCountRef.current = newSlotCount;

      return () => clearTimeout(timer);
    }
  }, [status.slots.length]);

  // ── Transition to day view on completion ──
  useEffect(() => {
    if (status.status === "completed" && status.slots.length > 0) {
      // Short delay to let user see the complete state before transitioning
      completionTimerRef.current = setTimeout(() => {
        onComplete(status.slots);
      }, 2400);

      return () => {
        if (completionTimerRef.current) clearTimeout(completionTimerRef.current);
      };
    }
  }, [status.status, status.slots, onComplete]);

  // ── Stop polling on terminal states ──
  useEffect(() => {
    if (status.status === "completed" || status.status === "failed") {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
    }
  }, [status.status]);

  // ── Group slots by day for rendering ──
  const slotsByDay = status.slots.reduce<Record<number, ItinerarySlot[]>>(
    (acc, slot) => {
      if (!acc[slot.dayNumber]) acc[slot.dayNumber] = [];
      acc[slot.dayNumber].push(slot);
      return acc;
    },
    {}
  );
  const dayNumbers = Object.keys(slotsByDay)
    .map(Number)
    .sort((a, b) => a - b);

  // How many skeleton cards to show based on progress
  const expectedTotal = Math.max(
    Math.ceil((status.progress / 100) * 12),
    status.slots.length + 2
  );
  const skeletonCount = Math.max(0, expectedTotal - status.slots.length);

  return (
    <div className="min-h-screen bg-app">
      {/* Header */}
      <header className="px-4 pt-8 pb-6 sm:px-6">
        <div className="mx-auto max-w-lg">
          <div className="flex items-center gap-2 text-terracotta">
            {status.status === "generating" && (
              <SpinnerIcon className="h-5 w-5" />
            )}
            {status.status === "completed" && (
              <CheckCircleIcon className="h-5 w-5" />
            )}
          </div>
          <h1 className="mt-3 font-sora text-2xl font-bold text-primary">
            {tripName}
          </h1>
          <p className="mt-1 font-dm-mono text-sm text-secondary">
            {destination}
          </p>
        </div>
      </header>

      {/* Content */}
      <div className="px-4 pb-24 sm:px-6">
        <div className="mx-auto max-w-lg space-y-6">
          {/* Progress + status message */}
          {status.status === "generating" && (
            <div className="space-y-3">
              <ProgressBar progress={status.progress} />
              <RotatingStatus />
            </div>
          )}

          {/* Completion banner */}
          {status.status === "completed" && (
            <CompletionBanner slotCount={status.slots.length} />
          )}

          {/* Error state */}
          {status.status === "failed" && (
            <ErrorState error={status.error ?? ""} onRetry={onRetry} />
          )}

          {/* Slot cards — grouped by day */}
          {status.status !== "failed" && (
            <div className="space-y-6" role="list" aria-label="Itinerary slots">
              {dayNumbers.map((dayNum) => (
                <div key={dayNum}>
                  <h3 className="label-mono mb-3">Day {dayNum}</h3>
                  <div className="space-y-3">
                    {slotsByDay[dayNum].map((slot, i) => (
                      <SlotCard
                        key={slot.id}
                        slot={slot}
                        index={i}
                        isNew={isRevealing}
                      />
                    ))}
                  </div>
                </div>
              ))}

              {/* Skeleton placeholders */}
              {status.status === "generating" && skeletonCount > 0 && (
                <div>
                  {dayNumbers.length === 0 && (
                    <h3 className="label-mono mb-3">Day 1</h3>
                  )}
                  <div className="space-y-3">
                    {Array.from({ length: Math.min(skeletonCount, 6) }).map(
                      (_, i) => (
                        <SkeletonCard key={`skeleton-${i}`} index={i} />
                      )
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* View itinerary button on completion */}
          {status.status === "completed" && (
            <div className="pt-4 text-center">
              <button
                onClick={() => onComplete(status.slots)}
                className="btn-primary"
              >
                View full itinerary
              </button>
              <p className="mt-2 font-dm-mono text-xs text-secondary">
                Redirecting automatically...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export type { ItinerarySlot, GenerationStatus, RevealAnimationProps };
