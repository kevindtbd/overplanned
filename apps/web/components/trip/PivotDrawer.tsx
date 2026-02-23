"use client";
import { useState } from "react";

interface Props {
  tripId: string;
  slotId: string;
  currentActivityName: string;
  onClose: () => void;
  onPivotCreated: () => void;
}

export function PivotDrawer({ tripId, slotId, currentActivityName, onClose, onPivotCreated }: Props) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/trips/${tripId}/pivot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slotId, trigger: "user_request", reason: reason.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to create pivot");
      }
      onPivotCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-2xl bg-warm-background p-6 sm:rounded-2xl">
        <h3 className="font-heading text-lg text-ink-100">Suggest a change</h3>
        <p className="mt-1 font-mono text-xs text-ink-400">
          Replacing: {currentActivityName}
        </p>

        <label className="mt-4 block">
          <span className="font-mono text-xs text-ink-300">Why swap this?</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-warm-border bg-warm-surface px-3 py-2 font-mono text-sm text-ink-100 placeholder:text-ink-500 focus:border-terracotta focus:outline-none"
            rows={3}
            placeholder="e.g. Found a better restaurant nearby..."
            maxLength={500}
          />
        </label>

        {error && (
          <p className="mt-2 font-mono text-xs text-red-500">{error}</p>
        )}

        <div className="mt-4 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-warm-border px-4 py-2 font-mono text-xs text-ink-300 hover:bg-warm-surface"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !reason.trim()}
            className="flex-1 rounded-lg bg-terracotta px-4 py-2 font-mono text-xs text-white transition hover:bg-terracotta/90 disabled:opacity-50"
          >
            {submitting ? "Submitting..." : "Suggest change"}
          </button>
        </div>
      </div>
    </div>
  );
}
