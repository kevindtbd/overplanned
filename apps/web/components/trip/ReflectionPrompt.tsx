"use client";
import { useState } from "react";

interface Props {
  tripId: string;
  hasSubmitted: boolean;
}

export function ReflectionPrompt({ tripId, hasSubmitted }: Props) {
  const [rating, setRating] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [submitted, setSubmitted] = useState(hasSubmitted);
  const [submitting, setSubmitting] = useState(false);

  if (submitted) {
    return (
      <div className="rounded-xl border border-ink-700 bg-surface p-4">
        <p className="font-dm-mono text-xs text-ink-300">
          Thanks for your feedback! Your reflection helps improve future recommendations.
        </p>
      </div>
    );
  }

  async function handleSubmit() {
    if (rating === null) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/trips/${tripId}/reflection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, note: note.trim() || undefined }),
      });
      if (res.ok) setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  const stars = [1, 2, 3, 4, 5];

  return (
    <div className="rounded-xl border border-ink-700 bg-surface p-4">
      <h3 className="font-sora text-base text-ink-100">How was your trip?</h3>
      <p className="mt-1 font-dm-mono text-xs text-ink-400">
        Rate your experience to help us improve future recommendations.
      </p>

      <div className="mt-3 flex gap-1">
        {stars.map((s) => (
          <button
            key={s}
            onClick={() => setRating(s)}
            className={`h-8 w-8 rounded transition ${
              rating !== null && s <= rating
                ? "bg-accent text-white"
                : "bg-base text-ink-400 hover:text-accent"
            }`}
          >
            <span className="font-dm-mono text-sm">{s}</span>
          </button>
        ))}
      </div>

      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="mt-3 block w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-dm-mono text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent focus:outline-none"
        rows={2}
        placeholder="Any thoughts? (optional)"
        maxLength={1000}
      />

      <button
        onClick={handleSubmit}
        disabled={rating === null || submitting}
        className="mt-3 rounded-lg bg-accent px-4 py-2 font-dm-mono text-xs text-white transition hover:bg-accent/90 disabled:opacity-50"
      >
        {submitting ? "Submitting..." : "Submit reflection"}
      </button>
    </div>
  );
}
