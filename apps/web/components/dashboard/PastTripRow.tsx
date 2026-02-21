"use client";

// PastTripRow -- Compact row for completed/past trips on the dashboard.
//
// Usage:
//   <PastTripRow trip={trip} />

import Image from "next/image";
import Link from "next/link";
import { type TripSummary } from "./TripHeroCard";
import { getCityPhoto } from "@/lib/city-photos";

function formatShortDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} - ${e.toLocaleDateString("en-US", opts)}`;
}

export function PastTripRow({ trip }: { trip: TripSummary }) {
  const photo = getCityPhoto(trip.city, 400);
  const displayName = trip.name || trip.destination;

  return (
    <Link
      href={`/trip/${trip.id}`}
      className="group flex items-center gap-4 rounded-xl border border-ink-700 bg-surface p-3 transition-colors duration-150 hover:border-accent/40"
    >
      {/* Thumbnail */}
      <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-lg">
        <Image
          src={photo}
          alt={displayName}
          fill
          sizes="56px"
          className="object-cover"
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <h4 className="font-sora text-sm font-medium text-ink-100 truncate">
          {displayName}
        </h4>
        <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
          {trip.city}, {trip.country}
        </p>
      </div>

      {/* Dates */}
      <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider shrink-0 hidden sm:block">
        {formatShortDateRange(trip.startDate, trip.endDate)}
      </span>

      {/* Arrow */}
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-ink-400 shrink-0 transition-transform duration-150 group-hover:translate-x-0.5"
        aria-hidden="true"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </Link>
  );
}
