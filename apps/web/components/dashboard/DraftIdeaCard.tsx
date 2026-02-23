"use client";

// DraftIdeaCard -- Lightweight card for draft/saved trip ideas on the dashboard.
// Links to onboarding resume flow, not the trip detail page.
//
// Usage:
//   <DraftIdeaCard trip={trip} />

import Link from "next/link";
import { type TripSummary } from "./TripHeroCard";

// ---------- Helpers ----------

function formatDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const startStr = s.toLocaleDateString("en-US", opts);
  const endStr = e.toLocaleDateString("en-US", { ...opts, year: "numeric" });
  return `${startStr} - ${endStr}`;
}

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

// ---------- Component ----------

export function DraftIdeaCard({ trip }: { trip: TripSummary }) {
  const city = trip.primaryCity ?? "Unknown";
  const country = trip.primaryCountry ?? "";

  return (
    <Link
      href={`/onboarding?resume=${trip.id}`}
      className="block rounded-[20px] border border-warm-border bg-warm-surface p-5 transition-colors hover:border-accent/30"
      aria-label={`Continue planning trip to ${city}${country ? `, ${country}` : ""}`}
      data-testid="draft-idea-card"
    >
      {/* City name or route */}
      <h3 className="font-sora text-lg font-medium text-ink-100">
        {trip.routeString || city}
      </h3>

      {/* Country (only when no route string — route already includes cities) */}
      {!trip.routeString && country && (
        <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
          {country}
        </p>
      )}

      {/* Dates (if available) */}
      {trip.startDate && trip.endDate && (
        <p className="font-dm-mono text-xs text-ink-400 mt-1" data-testid="draft-dates">
          {formatDateRange(trip.startDate, trip.endDate)}
        </p>
      )}

      {/* Continue planning CTA */}
      <span className="inline-flex items-center gap-1 font-sora text-sm text-accent mt-3">
        Continue planning
        <ArrowRightIcon />
      </span>
    </Link>
  );
}
