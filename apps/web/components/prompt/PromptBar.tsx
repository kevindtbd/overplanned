"use client";

// PromptBar — Natural language mid-trip change input.
//
// Security: 200 character hard cap enforced client-side (server enforces independently).
// No activity data or persona is embedded in the request — the prompt text
// is the only user-controlled content sent to POST /prompt.
//
// Usage:
//   <PromptBar
//     tripId="uuid"
//     userId="uuid"
//     sessionId="optional-session-id"
//     onResult={(result) => handlePivotIntent(result)}
//     disabled={isPivotInProgress}
//   />

import { useState, useCallback, useRef, useId } from "react";

// ---------- Types ----------

export type PivotClassification =
  | "weather_change"
  | "venue_closure"
  | "time_overrun"
  | "mood_shift"
  | "custom";

export type ParseMethod = "haiku" | "keyword" | "default" | "rejected";

export interface ParsedIntent {
  classification: PivotClassification;
  confidence: number;
  entities: {
    location?: string | null;
    time?: string | null;
    activity_type?: string | null;
    [key: string]: unknown;
  };
  method: ParseMethod;
}

export interface PromptBarProps {
  tripId: string;
  userId: string;
  sessionId?: string;
  /** Called with the parsed intent after a successful POST /prompt */
  onResult: (result: ParsedIntent) => void;
  /** Prevent submission while a pivot is already in progress */
  disabled?: boolean;
  /** Optional placeholder override */
  placeholder?: string;
}

// ---------- Constants ----------

const MAX_CHARS = 200;
const API_ENDPOINT = "/api/prompt";

// Classification label display
const CLASSIFICATION_LABELS: Record<PivotClassification, string> = {
  weather_change: "Weather change",
  venue_closure: "Venue closed",
  time_overrun: "Running late",
  mood_shift: "Change of plans",
  custom: "Custom request",
};

// ---------- Icons ----------

function SendIcon({ className }: { className?: string }) {
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
      className={className}
      aria-hidden="true"
    >
      <line x1="14" y1="2" x2="6" y2="10" />
      <polyline points="14 2 9 14 6 10 2 7" />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className="animate-spin"
      aria-hidden="true"
    >
      <path d="M8 2a6 6 0 1 1 0 12A6 6 0 0 1 8 2z" strokeOpacity="0.3" />
      <path d="M8 2a6 6 0 0 1 6 6" />
    </svg>
  );
}

// ---------- Component ----------

export function PromptBar({
  tripId,
  userId,
  sessionId,
  onResult,
  disabled = false,
  placeholder = "Something changed? Tell me — rain, closed venue, tired...",
}: PromptBarProps) {
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ParsedIntent | null>(null);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputId = useId();

  const charsRemaining = MAX_CHARS - text.length;
  const isNearLimit = charsRemaining <= 30;
  const isAtLimit = charsRemaining <= 0;
  const canSubmit = text.trim().length > 0 && !isSubmitting && !disabled && !isAtLimit;

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      // Client-side cap — server enforces independently
      const value = e.target.value.slice(0, MAX_CHARS);
      setText(value);
      if (error) setError(null);
      if (lastResult) setLastResult(null);
    },
    [error, lastResult]
  );

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || isSubmitting || disabled) return;

    setIsSubmitting(true);
    setError(null);
    setLastResult(null);

    try {
      const body: Record<string, string> = {
        text: trimmed,
        tripId,
        userId,
      };
      if (sessionId) body.sessionId = sessionId;

      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        const msg =
          errBody?.error?.message ||
          errBody?.detail ||
          `Request failed (${res.status})`;
        throw new Error(msg);
      }

      const data = await res.json();
      const result: ParsedIntent = data.data;

      setLastResult(result);
      setText("");
      onResult(result);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setIsSubmitting(false);
      // Refocus input for rapid successive requests
      inputRef.current?.focus();
    }
  }, [text, tripId, userId, sessionId, isSubmitting, disabled, onResult]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Cmd+Enter or Ctrl+Enter submits
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (canSubmit) handleSubmit();
      }
    },
    [canSubmit, handleSubmit]
  );

  return (
    <div className="w-full space-y-2">
      {/* Input area */}
      <div
        className={`
          relative rounded-xl border bg-surface transition-all duration-150
          ${error ? "border-red-300" : "border-ink-700 focus-within:border-[#C4694F]/60"}
          ${disabled ? "opacity-60" : ""}
        `}
      >
        <label htmlFor={inputId} className="sr-only">
          Describe what changed during your trip
        </label>

        <textarea
          id={inputId}
          ref={inputRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isSubmitting}
          maxLength={MAX_CHARS}
          rows={2}
          aria-describedby={
            [error ? `${inputId}-error` : null, `${inputId}-counter`]
              .filter(Boolean)
              .join(" ") || undefined
          }
          className="
            w-full resize-none rounded-xl bg-transparent px-4 pt-3 pb-8
            font-sora text-sm text-ink-100 placeholder:text-ink-400
            focus:outline-none disabled:cursor-not-allowed
          "
        />

        {/* Character counter + submit — bottom bar */}
        <div className="absolute bottom-2 left-4 right-2 flex items-center justify-between">
          <span
            id={`${inputId}-counter`}
            aria-live="polite"
            aria-atomic="true"
            className={`
              font-dm-mono text-[10px] uppercase tracking-wider transition-colors
              ${isAtLimit ? "text-red-500" : isNearLimit ? "text-amber-500" : "text-ink-400"}
            `}
          >
            {charsRemaining} left
          </span>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            aria-label="Submit change request"
            className="
              flex items-center gap-1.5 rounded-lg px-3 py-1.5
              bg-[#C4694F] text-white
              font-dm-mono text-[10px] uppercase tracking-wider
              transition-all duration-150
              hover:bg-[#b35b42] active:scale-95
              disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[#C4694F]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2
            "
          >
            {isSubmitting ? (
              <>
                <SpinnerIcon />
                <span>Parsing</span>
              </>
            ) : (
              <>
                <SendIcon />
                <span>Send</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Keyboard hint */}
      <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
        Cmd + Enter to send
      </p>

      {/* Error state */}
      {error && (
        <div
          id={`${inputId}-error`}
          role="alert"
          className="
            rounded-lg border border-red-200 bg-error-bg px-3 py-2
            font-dm-mono text-xs text-red-700
          "
        >
          {error}
        </div>
      )}

      {/* Success state — show parsed intent */}
      {lastResult && !error && (
        <div
          aria-live="polite"
          className="
            rounded-lg border border-ink-700 bg-base px-3 py-2
            flex items-center justify-between
          "
        >
          <div className="flex items-center gap-2">
            <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
              Detected
            </span>
            <span className="font-dm-mono text-xs text-ink-100">
              {CLASSIFICATION_LABELS[lastResult.classification]}
            </span>
          </div>
          <span
            className={`
              font-dm-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded
              ${
                lastResult.confidence >= 0.7
                  ? "bg-success-bg text-success"
                  : lastResult.confidence >= 0.5
                  ? "bg-warning-bg text-warning"
                  : "bg-ink-800 text-ink-500"
              }
            `}
            title={`Confidence: ${(lastResult.confidence * 100).toFixed(0)}%`}
          >
            {lastResult.method === "haiku"
              ? "AI"
              : lastResult.method === "keyword"
              ? "Keyword"
              : lastResult.method === "rejected"
              ? "Blocked"
              : "Default"}
          </span>
        </div>
      )}
    </div>
  );
}
