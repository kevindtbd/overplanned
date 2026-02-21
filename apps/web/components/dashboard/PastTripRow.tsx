"use client";

// PastTripRow -- Compact row for completed/past trips on the dashboard.
//
// Usage:
//   <PastTripRow trip={trip} />

import Image from "next/image";
import Link from "next/link";
import { type TripSummary } from "./TripHeroCard";

// Same city photo map (could be extracted to shared util later)
const CITY_PHOTOS: Record<string, string> = {
  Tokyo:
    "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=400&q=80",
  Kyoto:
    "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=400&q=80",
  Osaka:
    "https://images.unsplash.com/photo-1590559899731-a382839e5549?w=400&q=80",
  Bangkok:
    "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=400&q=80",
  Seoul:
    "https://images.unsplash.com/photo-1534274988757-a28bf1a57c17?w=400&q=80",
  Lisbon:
    "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=400&q=80",
  Barcelona:
    "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=400&q=80",
  Paris:
    "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=400&q=80",
  London:
    "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=400&q=80",
  Berlin:
    "https://images.unsplash.com/photo-1560969184-10fe8719e047?w=400&q=80",
};

const FALLBACK_PHOTO =
  "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=400&q=80";

function formatShortDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} - ${e.toLocaleDateString("en-US", opts)}`;
}

export function PastTripRow({ trip }: { trip: TripSummary }) {
  const photo = CITY_PHOTOS[trip.city] ?? FALLBACK_PHOTO;
  const displayName = trip.name || trip.destination;

  return (
    <Link
      href={`/trip/${trip.id}`}
      className="group flex items-center gap-4 rounded-xl border border-ink-900 bg-surface p-3 transition-colors duration-150 hover:border-accent/40"
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
