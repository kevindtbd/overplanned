"use client";

/**
 * LegReviewStep — Review accumulated trip legs before continuing.
 * Shows compact cards for each leg, "Add another city" loops back,
 * "Continue" moves forward.
 */

import { MAX_LEGS } from "@/lib/constants/trip";

export interface OnboardingLeg {
  city: string;
  country: string;
  timezone: string;
  destination: string;
  startDate: string;
  endDate: string;
}

interface LegReviewStepProps {
  legs: OnboardingLeg[];
  onRemoveLeg: (index: number) => void;
  onAddAnother: () => void;
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} - ${e.toLocaleDateString("en-US", opts)}`;
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function LegReviewStep({
  legs,
  onRemoveLeg,
  onAddAnother,
}: LegReviewStepProps) {
  const canAddMore = legs.length < MAX_LEGS;

  return (
    <div className="mx-auto w-full max-w-md">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        Your cities
      </h2>
      <p className="label-mono mt-2">
        {legs.length === 1
          ? "add more cities or continue"
          : `${legs.length} cities planned`}
      </p>

      {/* Leg cards */}
      <div className="mt-6 space-y-3">
        {legs.map((leg, i) => (
          <div
            key={`${leg.city}-${i}`}
            className="flex items-center gap-3 rounded-xl border border-warm-border bg-warm-surface px-4 py-3"
            data-testid={`leg-card-${i}`}
          >
            {/* Position badge */}
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 font-dm-mono text-xs font-medium text-accent">
              {i + 1}
            </span>

            {/* City info */}
            <div className="flex-1 min-w-0">
              <p className="font-sora text-sm font-medium text-primary truncate">
                {leg.city}
              </p>
              <p className="font-dm-mono text-[10px] text-ink-400">
                {leg.country} &middot; {formatDateRange(leg.startDate, leg.endDate)}
              </p>
            </div>

            {/* Remove button — only when more than 1 leg */}
            {legs.length > 1 && (
              <button
                type="button"
                onClick={() => onRemoveLeg(i)}
                className="shrink-0 p-1 rounded-md text-ink-400 hover:text-ink-200 hover:bg-ink-700/50 transition-colors"
                aria-label={`Remove ${leg.city}`}
                data-testid={`remove-leg-${i}`}
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Add another city */}
      {canAddMore && (
        <button
          type="button"
          onClick={onAddAnother}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-ink-700 px-4 py-3 text-ink-400 hover:border-accent/40 hover:text-accent transition-colors"
          data-testid="add-another-city"
        >
          <PlusIcon className="h-4 w-4" />
          <span className="font-sora text-sm">Add another city</span>
        </button>
      )}

      {!canAddMore && (
        <p className="mt-4 text-center font-dm-mono text-xs text-ink-400">
          Maximum {MAX_LEGS} cities reached
        </p>
      )}
    </div>
  );
}
