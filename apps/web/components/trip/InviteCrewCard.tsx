"use client";

import { useState } from "react";

interface Props {
  tripId: string;
  onDismiss: () => void;
}

export function InviteCrewCard({ tripId, onDismiss }: Props) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(null);

  async function handleInvite() {
    setError(null);
    setFallbackUrl(null);
    try {
      const res = await fetch(`/api/trips/${tripId}/invite`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to create invite");
      const { token } = await res.json();
      const url = `${window.location.origin}/invite/${token}`;
      try {
        await navigator.clipboard.writeText(url);
        setCopying(true);
        setTimeout(() => setCopying(false), 2000);
      } catch {
        // Clipboard failed — show URL as selectable text
        setFallbackUrl(url);
      }
    } catch {
      setError("Could not create invite link");
    }
  }

  return (
    <div className="rounded-xl border border-warm-border bg-warm-surface p-4 relative">
      <button
        onClick={onDismiss}
        className="absolute top-3 right-3 rounded-lg p-1 text-ink-400 hover:text-ink-100 transition-colors"
        aria-label="Dismiss"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <h3 className="font-sora text-base font-medium text-ink-100">Invite your crew</h3>
      <p className="mt-1 font-dm-mono text-xs text-ink-400">
        Share a link so friends can vote on activities and suggest changes.
      </p>

      <button
        onClick={handleInvite}
        className="mt-3 rounded-lg bg-accent px-4 py-2 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90"
      >
        {copying ? "Copied!" : "Copy invite link"}
      </button>

      {error && (
        <p className="mt-2 font-dm-mono text-xs text-red-400">{error}</p>
      )}

      {fallbackUrl && (
        <div className="mt-2">
          <input
            type="text"
            readOnly
            value={fallbackUrl}
            className="w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2 font-dm-mono text-xs text-ink-200 select-all"
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
        </div>
      )}
    </div>
  );
}
