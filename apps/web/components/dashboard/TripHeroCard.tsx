"use client";

// TripHeroCard -- Large hero card for an active trip on the dashboard.
// Shows destination photo with warm overlay, trip name, dates, and planning progress.
//
// Usage:
//   <TripHeroCard trip={trip} />

import Image from "next/image";
import Link from "next/link";

// ---------- Unsplash city photos ----------

const CITY_PHOTOS: Record<string, string> = {
  Tokyo:
    "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=1200&q=80",
  Kyoto:
    "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1200&q=80",
  Osaka:
    "https://images.unsplash.com/photo-1590559899731-a382839e5549?w=1200&q=80",
  Bangkok:
    "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=1200&q=80",
  Seoul:
    "https://images.unsplash.com/photo-1534274988757-a28bf1a57c17?w=1200&q=80",
  Taipei:
    "https://images.unsplash.com/photo-1470004914212-05527e49370b?w=1200&q=80",
  Lisbon:
    "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=1200&q=80",
  Barcelona:
    "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=1200&q=80",
  "Mexico City":
    "https://images.unsplash.com/photo-1585464231875-d9ef1f5ad396?w=1200&q=80",
  "New York":
    "https://images.unsplash.com/photo-1496442226666-8d4d0e62e6e9?w=1200&q=80",
  London:
    "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=1200&q=80",
  Paris:
    "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=1200&q=80",
  Berlin:
    "https://images.unsplash.com/photo-1560969184-10fe8719e047?w=1200&q=80",
};

const FALLBACK_PHOTO =
  "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80";

// ---------- Types ----------

export interface TripSummary {
  id: string;
  name: string | null;
  destination: string;
  city: string;
  country: string;
  mode: string;
  status: string;
  startDate: string;
  endDate: string;
  planningProgress: number;
  memberCount: number;
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

function getCityPhoto(city: string): string {
  return CITY_PHOTOS[city] ?? FALLBACK_PHOTO;
}

// ---------- Component ----------

export function TripHeroCard({ trip }: { trip: TripSummary }) {
  const photo = getCityPhoto(trip.city);
  const displayName = trip.name || trip.destination;
  const progress = Math.min(Math.max(trip.planningProgress ?? 0, 0), 100);

  return (
    <Link
      href={`/trip/${trip.id}`}
      className="group block rounded-2xl shadow-card overflow-hidden relative"
    >
      {/* Background photo */}
      <div className="relative h-56 sm:h-64 w-full">
        <Image
          src={photo}
          alt={displayName}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
        />
        <div className="photo-overlay-warm absolute inset-0" aria-hidden="true" />

        {/* Content over photo */}
        <div className="absolute inset-0 flex flex-col justify-end p-5">
          {/* Mode badge */}
          <span className="font-dm-mono text-[10px] uppercase tracking-[0.1em] text-white/60 mb-1">
            {trip.mode} trip
          </span>

          {/* Trip name */}
          <h3 className="font-sora text-xl font-semibold text-white leading-tight">
            {displayName}
          </h3>

          {/* Destination + dates */}
          <p className="font-dm-mono text-sm text-white/80 mt-1">
            {trip.city}, {trip.country}
          </p>
          <p className="font-dm-mono text-xs text-white/60 mt-0.5">
            {formatDateRange(trip.startDate, trip.endDate)}
          </p>

          {/* Progress bar */}
          {trip.status === "planning" && (
            <div className="mt-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-dm-mono text-[10px] uppercase tracking-wider text-white/50">
                  Planning progress
                </span>
                <span className="font-dm-mono text-[10px] text-white/50">
                  {progress}%
                </span>
              </div>
              <div className="h-1 w-full rounded-full bg-white/20 overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Member count for group trips */}
          {trip.memberCount > 1 && (
            <div className="mt-2 flex items-center gap-1.5">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-white/60"
                aria-hidden="true"
              >
                <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 00-3-3.87" />
                <path d="M16 3.13a4 4 0 010 7.75" />
              </svg>
              <span className="font-dm-mono text-[10px] text-white/60">
                {trip.memberCount} members
              </span>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
