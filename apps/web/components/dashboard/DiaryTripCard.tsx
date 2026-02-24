"use client";

// DiaryTripCard -- Lightweight card for backfilled past trips on the dashboard.
// Links to the diary detail page for enrichment (photos, notes, ratings).
//
// Usage:
//   <DiaryTripCard trip={trip} />

import Link from "next/link";

// ---------- Types ----------

export interface BackfillLeg {
  city: string;
  country: string;
  position: number;
}

export interface BackfillTripSummary {
  id: string;
  legs?: BackfillLeg[];
  /** @deprecated Use legs[0].city — kept for backward compat */
  city: string;
  /** @deprecated Use legs[0].country — kept for backward compat */
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

/**
 * Build a route string from backfill legs for card display.
 * For 5+ cities, truncates to: "Tokyo \u2192 Kyoto \u2192 ... \u2192 Hiroshima"
 */
function buildBackfillRouteString(legs: BackfillLeg[]): string {
  const sorted = [...legs].sort((a, b) => a.position - b.position);
  const cities = sorted.map((l) => l.city);
  if (cities.length <= 4) {
    return cities.join(" \u2192 ");
  }
  return `${cities[0]} \u2192 ${cities[1]} \u2192 ... \u2192 ${cities[cities.length - 1]}`;
}

/**
 * Derive the country subtitle for multi-city trips.
 * Single country: "Japan"
 * Two countries: "Japan & Thailand"
 * Three+: "Japan, Thailand & more"
 */
function buildCountrySubtitle(legs: BackfillLeg[]): string {
  const sorted = [...legs].sort((a, b) => a.position - b.position);
  const countries = [...new Set(sorted.map((l) => l.country))];
  if (countries.length === 1) return countries[0];
  if (countries.length === 2) return `${countries[0]} & ${countries[1]}`;
  return `${countries[0]}, ${countries[1]} & more`;
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
  const isMultiCity = trip.legs && trip.legs.length >= 2;

  // Build display strings
  const locationLabel = isMultiCity
    ? buildBackfillRouteString(trip.legs!)
    : trip.city;
  const subtitleLabel = isMultiCity
    ? buildCountrySubtitle(trip.legs!)
    : trip.country;

  return (
    <Link
      href={`/diary/${trip.id}`}
      className="block rounded-[20px] border border-warm-border bg-warm-surface p-5 transition-colors hover:border-accent/30"
      aria-label={`View diary for ${locationLabel}`}
      data-testid="diary-trip-card"
    >
      {/* Route / City name */}
      <h3
        className="font-sora text-lg font-medium text-ink-100"
        data-testid="diary-trip-location"
      >
        {locationLabel}
      </h3>

      {/* Country */}
      <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
        {subtitleLabel}
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
