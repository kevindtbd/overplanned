"use client";

// DiaryTripCard -- Lightweight card for backfilled past trips on the dashboard.
// Links to the diary detail page for enrichment (photos, notes, ratings).
//
// Usage:
//   <DiaryTripCard trip={trip} />

import Link from "next/link";

// ---------- Types ----------

export interface BackfillTripSummary {
  id: string;
  city: string;
  country: string;
  startDate: string | null;
  endDate: string | null;
  contextTag: string | null;
  status: string;
  resolvedVenueCount: number;
  totalVenueCount: number;
  createdAt: string;
}

// ---------- Helpers ----------

function formatDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const startStr = s.toLocaleDateString("en-US", opts);
  const endStr = e.toLocaleDateString("en-US", { ...opts, year: "numeric" });
  return `${startStr} - ${endStr}`;
}

const CONTEXT_LABELS: Record<string, string> = {
  solo: "Solo",
  partner: "Partner",
  family: "Family",
  friends: "Friends",
  work: "Work",
};

// ---------- Icons ----------

function ArrowRightIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function ProcessingIndicator() {
  return (
    <span className="inline-flex items-center gap-1.5 font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
      Processing
    </span>
  );
}

// ---------- Component ----------

export function DiaryTripCard({ trip }: { trip: BackfillTripSummary }) {
  const isProcessing = trip.status === "processing";

  return (
    <Link
      href={`/diary/${trip.id}`}
      className="block rounded-[20px] border border-warm-border bg-warm-surface p-5 transition-colors hover:border-accent/30"
      aria-label={`View diary for ${trip.city}, ${trip.country}`}
      data-testid="diary-trip-card"
    >
      {/* City name */}
      <h3 className="font-sora text-lg font-medium text-ink-100">
        {trip.city}
      </h3>

      {/* Country */}
      <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
        {trip.country}
      </p>

      {/* Dates */}
      {trip.startDate && trip.endDate && (
        <p className="font-dm-mono text-xs text-ink-400 mt-1" data-testid="diary-dates">
          {formatDateRange(trip.startDate, trip.endDate)}
        </p>
      )}
      {!trip.startDate && (
        <p className="font-dm-mono text-xs text-ink-500 mt-1">Dates unknown</p>
      )}

      {/* Meta row: venue count + context tag */}
      <div className="flex items-center gap-3 mt-2">
        {!isProcessing && trip.totalVenueCount > 0 && (
          <span className="font-dm-mono text-xs text-ink-400">
            {trip.resolvedVenueCount} {trip.resolvedVenueCount === 1 ? "place" : "places"}
          </span>
        )}

        {trip.contextTag && (
          <span className="rounded-full bg-warm-background px-2 py-0.5 font-dm-mono text-[10px] text-ink-400">
            {CONTEXT_LABELS[trip.contextTag] || trip.contextTag}
          </span>
        )}
      </div>

      {/* Status / CTA */}
      <div className="mt-3">
        {isProcessing ? (
          <ProcessingIndicator />
        ) : (
          <span className="inline-flex items-center gap-1 font-sora text-sm text-accent">
            View diary
            <ArrowRightIcon />
          </span>
        )}
      </div>
    </Link>
  );
}
