"use client";
import { useState } from "react";

interface Props {
  tripId: string;
}

export function ShareButton({ tripId }: Props) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleShare() {
    setError(null);
    try {
      const res = await fetch(`/api/trips/${tripId}/share`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to create share link");
      const { token } = await res.json();
      const url = `${window.location.origin}/shared/${token}`;
      await navigator.clipboard.writeText(url);
      setCopying(true);
      setTimeout(() => setCopying(false), 2000);
    } catch {
      setError("Could not create share link");
    }
  }

  return (
    <div className="relative">
      <button
        onClick={handleShare}
        className="flex items-center gap-1.5 rounded-lg border border-ink-700 bg-surface px-3 py-1.5 font-dm-mono text-xs text-ink-200 transition hover:bg-base"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
        {copying ? "Copied!" : "Share"}
      </button>
      {error && (
        <p className="absolute top-full mt-1 whitespace-nowrap font-dm-mono text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
}
