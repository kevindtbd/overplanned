"use client";
import { useState } from "react";

interface Props {
  tripId: string;
}

export function InviteButton({ tripId }: Props) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleInvite() {
    setError(null);
    try {
      const res = await fetch(`/api/trips/${tripId}/invite`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to create invite");
      const { token } = await res.json();
      const url = `${window.location.origin}/invite/${token}`;
      await navigator.clipboard.writeText(url);
      setCopying(true);
      setTimeout(() => setCopying(false), 2000);
    } catch {
      setError("Could not create invite link");
    }
  }

  return (
    <div className="relative">
      <button
        onClick={handleInvite}
        className="flex items-center gap-1.5 rounded-lg border border-warm-border bg-warm-surface px-3 py-1.5 font-mono text-xs text-ink-200 transition hover:bg-warm-background"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <line x1="19" y1="8" x2="19" y2="14" />
          <line x1="22" y1="11" x2="16" y2="11" />
        </svg>
        {copying ? "Copied!" : "Invite"}
      </button>
      {error && (
        <p className="absolute top-full mt-1 whitespace-nowrap font-mono text-xs text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
