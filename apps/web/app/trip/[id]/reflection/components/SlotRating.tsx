"use client";

// SlotRating — Post-trip per-slot highlight rating.
// Three-state: loved / skipped / missed (SVG icons, no emoji).
// Fires BehavioralSignal callbacks for post_loved, post_skipped, post_missed.

import { useState, useCallback } from "react";

export type SlotRatingValue = "loved" | "skipped" | "missed" | null;

export interface SlotRatingEvent {
  slotId: string;
  activityNodeId?: string;
  rating: SlotRatingValue;
  signalType: "post_loved" | "post_skipped" | "post_missed";
  signalValue: number;
}

interface SlotRatingProps {
  slotId: string;
  activityNodeId?: string;
  activityName: string;
  imageUrl?: string;
  initialRating?: SlotRatingValue;
  onRate: (event: SlotRatingEvent) => void;
  disabled?: boolean;
}

// ---------- SVG Icons (no emoji, no icon libs) ----------

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10 17.5s-7-4.5-7-9a3.5 3.5 0 017 0 3.5 3.5 0 017 0c0 4.5-7 9-7 9z" />
    </svg>
  );
}

function SkipForwardIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polygon points="4,3 12,10 4,17" />
      <line x1="15" y1="4" x2="15" y2="16" />
    </svg>
  );
}

function TargetMissIcon({ filled }: { filled: boolean }) {
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
      <circle cx="10" cy="10" r="7" opacity={filled ? 1 : 0.6} />
      <circle cx="10" cy="10" r="3" fill={filled ? "currentColor" : "none"} />
      <line x1="4" y1="16" x2="16" y2="4" strokeWidth="2" />
    </svg>
  );
}

// ---------- Rating config ----------

const RATING_CONFIG: Record<
  NonNullable<SlotRatingValue>,
  {
    label: string;
    signalType: SlotRatingEvent["signalType"];
    signalValue: number;
    activeClass: string;
    hoverClass: string;
    Icon: typeof HeartIcon;
  }
> = {
  loved: {
    label: "Loved it",
    signalType: "post_loved",
    signalValue: 1.0,
    activeClass: "bg-emerald-100 text-emerald-700 border-emerald-400",
    hoverClass: "hover:border-emerald-400 hover:text-emerald-700",
    Icon: HeartIcon,
  },
  skipped: {
    label: "Skipped",
    signalType: "post_skipped",
    signalValue: -0.5,
    activeClass: "bg-amber-100 text-amber-700 border-amber-400",
    hoverClass: "hover:border-amber-400 hover:text-amber-700",
    Icon: SkipForwardIcon,
  },
  missed: {
    label: "Wish I went",
    signalType: "post_missed",
    signalValue: 0.75,
    activeClass: "bg-blue-100 text-blue-700 border-blue-400",
    hoverClass: "hover:border-blue-400 hover:text-blue-700",
    Icon: TargetMissIcon,
  },
};

// ---------- Component ----------

export function SlotRating({
  slotId,
  activityNodeId,
  activityName,
  imageUrl,
  initialRating = null,
  onRate,
  disabled = false,
}: SlotRatingProps) {
  const [selected, setSelected] = useState<SlotRatingValue>(initialRating);

  const handleRate = useCallback(
    (rating: NonNullable<SlotRatingValue>) => {
      if (disabled) return;
      const next = selected === rating ? null : rating;
      setSelected(next);

      if (next) {
        const config = RATING_CONFIG[next];
        onRate({
          slotId,
          activityNodeId,
          rating: next,
          signalType: config.signalType,
          signalValue: config.signalValue,
        });
      }
    },
    [slotId, activityNodeId, selected, disabled, onRate]
  );

  return (
    <div
      className="rounded-xl border border-ink-700 bg-surface p-4 space-y-3"
      role="group"
      aria-label={`Rate ${activityName}`}
    >
      {/* Slot identity */}
      <div className="flex items-center gap-3">
        {imageUrl ? (
          <div className="w-10 h-10 rounded-lg overflow-hidden bg-base shrink-0">
            <img
              src={imageUrl}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
            />
          </div>
        ) : (
          <div className="w-10 h-10 rounded-lg bg-base flex items-center justify-center shrink-0">
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-ink-400 opacity-40"
              aria-hidden="true"
            >
              <rect x="2" y="4" width="16" height="12" rx="2" />
              <circle cx="7" cy="9" r="2" />
              <path d="M2 14l4-3 3 2 5-5 4 4" />
            </svg>
          </div>
        )}
        <h3 className="font-sora font-semibold text-ink-100 text-sm leading-tight">
          {activityName}
        </h3>
      </div>

      {/* Rating buttons */}
      <div className="flex items-center gap-2">
        {(Object.keys(RATING_CONFIG) as NonNullable<SlotRatingValue>[]).map(
          (rating) => {
            const config = RATING_CONFIG[rating];
            const isActive = selected === rating;
            return (
              <button
                key={rating}
                type="button"
                onClick={() => handleRate(rating)}
                disabled={disabled}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                  font-dm-mono text-xs uppercase tracking-wider
                  border transition-all duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
                  disabled:opacity-40 disabled:cursor-not-allowed
                  ${
                    isActive
                      ? config.activeClass
                      : `bg-surface text-ink-400 border-ink-700 ${config.hoverClass}`
                  }
                `}
                aria-pressed={isActive}
                aria-label={config.label}
              >
                <config.Icon filled={isActive} />
                <span>{config.label}</span>
              </button>
            );
          }
        )}
      </div>
    </div>
  );
}
