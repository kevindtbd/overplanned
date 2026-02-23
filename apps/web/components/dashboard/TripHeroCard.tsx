"use client";

// TripHeroCard -- Large hero card for an active trip on the dashboard.
// Shows destination photo with warm overlay, trip name, dates, and planning progress.
//
// Usage:
//   <TripHeroCard trip={trip} />

import Image from "next/image";
import Link from "next/link";
import { getCityPhoto } from "@/lib/city-photos";

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

// ---------- Component ----------

export function TripHeroCard({ trip }: { trip: TripSummary }) {
  const photo = getCityPhoto(trip.city);
  const displayName = trip.name || trip.destination;
  const progress = Math.min(Math.max(trip.planningProgress ?? 0, 0), 100);

  return (
    <Link
      href={`/trip/${trip.id}`}
      className="group block rounded-[20px] shadow-lg overflow-hidden relative"
      aria-label={`View trip to ${displayName}, ${formatDateRange(trip.startDate, trip.endDate)}`}
    >
      {/* Background photo */}
      <div className="relative h-[340px] w-full">
        <Image
          src={photo}
          alt={displayName}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover transition-transform duration-300 group-hover:scale-[1.03] focus-visible:scale-[1.03]"
        />
        <div className="photo-overlay-warm absolute inset-0" aria-hidden="true" />

        {/* Content over photo */}
        <div className="absolute inset-0 flex flex-col justify-end p-5">
          {/* Mode badge */}
          <span className="font-dm-mono text-[10px] uppercase tracking-[0.1em] text-white/60 mb-1">
            {trip.mode} trip
          </span>

          {/* Trip name */}
          <h3 className="font-sora text-2xl font-medium text-white leading-tight">
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
          {(trip.status === "draft" || trip.status === "planning") && (
            <div className="mt-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-dm-mono text-[10px] uppercase tracking-wider text-white/50">
                  Planning progress
                </span>
                <span className="font-dm-mono text-[10px] text-white/50">
                  {progress}%
                </span>
              </div>
              <div
                className="h-1 w-full rounded-full bg-white/20 overflow-hidden"
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Planning progress"
              >
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
