"use client";

// BackfillStep -- Skippable step in onboarding that lets users add past trips
// for persona seeding. Captures city, approximate dates, travel context, and
// free-form diary text. Submits to the backfill pipeline.
// Non-blocking: advances to next step without waiting for pipeline completion.

import { useState, useRef } from "react";

interface BackfillStepProps {
  onSkip: () => void;
  onContinue: () => void;
}

// ---------- Constants ----------

const CONTEXT_OPTIONS = [
  { value: "solo", label: "Solo" },
  { value: "partner", label: "Partner" },
  { value: "family", label: "Family" },
  { value: "friends", label: "Friends" },
  { value: "work", label: "Work" },
] as const;

const MAX_TEXT_LENGTH = 10000;

// ---------- Icons ----------

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
    >
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function LoadingSpinner({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className ?? ""}`}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        opacity={0.25}
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

// ---------- Component ----------

export function BackfillStep({ onSkip, onContinue }: BackfillStepProps) {
  const [city, setCity] = useState("");
  const [approxDates, setApproxDates] = useState("");
  const [context, setContext] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitCount, setSubmitCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSubmit = text.trim().length >= 20 && !isSubmitting;

  async function handleSubmit() {
    if (!canSubmit) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const payload: Record<string, string> = { text: text.trim() };
      if (city.trim()) payload.cityHint = city.trim();
      if (approxDates.trim()) payload.dateRangeHint = approxDates.trim();
      if (context) payload.contextTag = context;

      const res = await fetch("/api/backfill/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to submit trip");
      }

      setSubmitted(true);
      setSubmitCount((c) => c + 1);
      setText("");
      setCity("");
      setApproxDates("");
      setContext(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Something went wrong. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleAddAnother() {
    setSubmitted(false);
    setError(null);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  return (
    <div className="mx-auto w-full max-w-md pt-8">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        Tell us about a past trip
      </h2>
      <p className="mt-2 text-secondary text-sm">
        This helps us personalize your recommendations. The more detail, the
        better we can tailor your next trip.
      </p>

      {!submitted ? (
        <>
          {/* City + dates row */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="backfill-city"
                className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400"
              >
                Where did you go?
              </label>
              <input
                id="backfill-city"
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value.slice(0, 100))}
                placeholder="Tokyo"
                className="mt-1 w-full rounded-lg border-[1.5px] border-ink-700 bg-input py-2 px-3 font-sora text-sm text-primary placeholder:text-secondary/60 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
                data-testid="backfill-city"
              />
            </div>
            <div>
              <label
                htmlFor="backfill-dates"
                className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400"
              >
                When, roughly?
              </label>
              <input
                id="backfill-dates"
                type="text"
                value={approxDates}
                onChange={(e) => setApproxDates(e.target.value.slice(0, 100))}
                placeholder="March 2025"
                className="mt-1 w-full rounded-lg border-[1.5px] border-ink-700 bg-input py-2 px-3 font-sora text-sm text-primary placeholder:text-secondary/60 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
                data-testid="backfill-dates"
              />
            </div>
          </div>

          {/* Context tags */}
          <div className="mt-4">
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
              Who were you with?
            </p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="backfill-context-tags">
              {CONTEXT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() =>
                    setContext((prev) => (prev === opt.value ? null : opt.value))
                  }
                  className={`rounded-full px-3 py-1 font-dm-mono text-xs transition-colors ${
                    context === opt.value
                      ? "bg-accent text-white"
                      : "bg-surface text-ink-300 hover:bg-ink-700"
                  }`}
                  data-testid={`backfill-context-${opt.value}`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Text area */}
          <div className="mt-4">
            <label
              htmlFor="backfill-text"
              className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400"
            >
              What was it like?
            </label>
            <textarea
              id="backfill-text"
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_TEXT_LENGTH))}
              placeholder="Visited Tsukiji Market early morning, had amazing ramen at Fuunji near Shinjuku, spent an afternoon in Shimokitazawa browsing vintage shops..."
              rows={5}
              className="mt-1 w-full rounded-xl border-[1.5px] border-ink-700 bg-input py-3 px-4 font-sora text-sm text-primary placeholder:text-secondary/60 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 resize-none"
              data-testid="backfill-textarea"
            />
            <div className="mt-1 flex items-center justify-between">
              <p className="font-dm-mono text-xs text-ink-500">
                {text.trim().length < 20 && text.length > 0
                  ? "Add a bit more detail"
                  : "\u00A0"}
              </p>
              <p className="font-dm-mono text-xs text-ink-500">
                {text.length.toLocaleString()}/{MAX_TEXT_LENGTH.toLocaleString()}
              </p>
            </div>
          </div>

          {/* Error */}
          {error && (
            <p className="mt-2 font-dm-mono text-xs text-red-400" data-testid="backfill-error">
              {error}
            </p>
          )}
        </>
      ) : (
        /* Confirmation state */
        <div className="mt-6 rounded-xl border border-accent/20 bg-accent/5 p-5" data-testid="backfill-confirmation">
          <div className="flex items-start gap-3">
            <CheckCircleIcon className="h-5 w-5 text-accent mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-sora text-sm font-medium text-primary">
                Trip {submitCount > 1 ? `#${submitCount} ` : ""}added
              </p>
              <p className="mt-1 font-dm-mono text-xs text-ink-400">
                We&apos;re processing your trip in the background. You&apos;ll see it on
                your dashboard soon.
              </p>
            </div>
          </div>

          {/* Add another */}
          <button
            onClick={handleAddAnother}
            className="mt-4 font-sora text-sm text-accent hover:text-accent/80 transition-colors"
            data-testid="backfill-add-another"
          >
            + Add another trip
          </button>
        </div>
      )}

      {/* Bottom actions */}
      <div className="mt-6 flex items-center justify-between">
        <button
          onClick={onSkip}
          className="font-dm-mono text-sm text-ink-400 hover:text-ink-300 transition-colors"
          data-testid="backfill-skip"
        >
          Skip for now
        </button>

        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="btn-primary flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="backfill-submit"
          >
            {isSubmitting ? (
              <LoadingSpinner className="h-4 w-4" />
            ) : null}
            <span>Add trip</span>
          </button>
        ) : (
          <button
            onClick={onContinue}
            className="btn-primary"
            data-testid="backfill-continue"
          >
            Continue
          </button>
        )}
      </div>
    </div>
  );
}
