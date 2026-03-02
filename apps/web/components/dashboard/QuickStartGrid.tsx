"use client";

// QuickStartGrid -- Action-forward empty state for the dashboard.
// Shows seeded city cards + "Somewhere else" to fast-track users into onboarding.
// Cities derived from LAUNCH_CITIES -- only shows cities with seeded ActivityNode data.

import Image from "next/image";
import Link from "next/link";
import { getCityPhoto } from "@/lib/city-photos";
import { LAUNCH_CITIES, type CityData } from "@/lib/cities";

// ---------- Icons ----------

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

// ---------- Data ----------

// Only cities with seeded ActivityNode data. Update when new cities are seeded.
const FEATURED_SLUGS = ["bend", "austin", "seattle"];
const FEATURED_CITIES = LAUNCH_CITIES.filter((c) =>
  FEATURED_SLUGS.includes(c.slug)
);

// ---------- CityCard ----------

function CityCard({ slug, city, state, country }: CityData) {
  const href = `/onboarding?city=${encodeURIComponent(city)}&step=dates`;
  const label = state || country;

  return (
    <Link
      href={href}
      aria-label={`Plan a trip to ${city}, ${label}`}
      className="group relative block h-[140px] overflow-hidden rounded-xl focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
    >
      <Image
        src={getCityPhoto(slug, 600, 75)}
        alt={`${city}, ${label}`}
        fill
        className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        sizes="(max-width: 640px) 50vw, 300px"
      />
      <div className="photo-overlay-warm absolute inset-0" aria-hidden="true" />
      <div className="absolute inset-0 flex flex-col justify-end p-3">
        <span className="font-dm-mono text-[10px] uppercase tracking-wider text-white/60">
          {label}
        </span>
        <span className="font-sora text-lg font-medium leading-tight text-white">
          {city}
        </span>
      </div>
    </Link>
  );
}

// ---------- SomewhereElseCard ----------

function SomewhereElseCard() {
  return (
    <Link
      href="/onboarding"
      aria-label="Plan a trip to a different city"
      className="flex h-[140px] flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-accent/40 bg-raised transition-colors hover:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
    >
      <PlusIcon className="h-6 w-6 text-accent" />
      <span className="font-sora text-sm text-ink-300">Somewhere else</span>
    </Link>
  );
}

// ---------- QuickStartGrid ----------

export function QuickStartGrid() {
  return (
    <section aria-labelledby="quickstart-heading">
      <h2
        id="quickstart-heading"
        className="font-dm-mono text-xs uppercase tracking-wider text-ink-400"
      >
        Where to?
      </h2>
      <div className="mt-3 grid grid-cols-2 gap-3">
        {FEATURED_CITIES.map((city) => (
          <CityCard key={city.slug} {...city} />
        ))}
        <SomewhereElseCard />
      </div>
    </section>
  );
}
