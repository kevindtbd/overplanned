"use client";

import { useState, useCallback } from "react";

interface MoodPulseProps {
  tripId: string;
  tripStatus: string;
  energyProfile?: { lastMood?: string; updatedAt?: string } | null;
}

type MoodLevel = "high" | "medium" | "low";

const MOOD_OPTIONS: { value: MoodLevel; label: string; icon: JSX.Element }[] = [
  {
    value: "high",
    label: "High energy",
    icon: (
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M10 15V5" />
        <path d="M5 9l5-4 5 4" />
      </svg>
    ),
  },
  {
    value: "medium",
    label: "Steady",
    icon: (
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <path d="M4 10h12" />
      </svg>
    ),
  },
  {
    value: "low",
    label: "Low energy",
    icon: (
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M10 5v10" />
        <path d="M5 11l5 4 5-4" />
      </svg>
    ),
  },
];

const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;

export function MoodPulse({ tripId, tripStatus, energyProfile }: MoodPulseProps) {
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [hidden, setHidden] = useState(false);

  const handleTap = useCallback(
    async (mood: MoodLevel) => {
      if (submitting) return;
      setSubmitting(true);
      try {
        await fetch(`/api/trips/${tripId}/mood`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mood }),
        });
        setConfirmed(true);
        // Hide after a brief confirmation
        setTimeout(() => setHidden(true), 1200);
      } catch {
        // Silently fail — non-critical signal
        setSubmitting(false);
      }
    },
    [tripId, submitting]
  );

  // Only render for active trips
  if (tripStatus !== "active") return null;

  // If mood was captured within the last 12 hours, don't show
  if (energyProfile?.updatedAt) {
    const elapsed = Date.now() - new Date(energyProfile.updatedAt).getTime();
    if (elapsed < TWELVE_HOURS_MS) return null;
  }

  // After confirmation animation completes, fully hide
  if (hidden) return null;

  return (
    <div className="rounded-xl bg-surface border border-ink-700 p-4">
      {confirmed ? (
        <p className="font-sora text-sm text-ink-100 text-center">
          Got it!
        </p>
      ) : (
        <>
          <h4 className="font-sora text-sm text-ink-100 mb-3">
            How&apos;s the energy?
          </h4>
          <div className="flex gap-2">
            {MOOD_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => handleTap(option.value)}
                disabled={submitting}
                className="
                  flex-1 flex flex-col items-center gap-1.5
                  rounded-lg border border-ink-700
                  px-3 py-3
                  text-ink-300
                  hover:border-accent hover:text-accent
                  active:bg-accent/10
                  transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed
                "
                aria-label={option.label}
              >
                {option.icon}
                <span className="font-dm-mono text-[10px]">{option.label}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
