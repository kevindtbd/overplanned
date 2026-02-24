"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { VIBE_ARCHETYPE_LIST, type VibeKey } from "@/lib/vibes";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CityResult {
  city: string;
  country: string;
  score: number;
  imageUrl: string | null;
  tagline: string | null;
  nodeCount: number;
}

interface ExploreClientProps {
  userId: string;
}

/* ------------------------------------------------------------------ */
/*  SVG Icons (inline, no icon libraries)                              */
/* ------------------------------------------------------------------ */

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M10 12L6 8L10 4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M6 4L10 8L6 12"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Vibe Card                                                          */
/* ------------------------------------------------------------------ */

function VibeCard({
  label,
  description,
  selected,
  onSelect,
}: {
  label: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`
        text-left rounded-xl p-6 bg-surface border transition-colors
        focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
        ${
          selected
            ? "border-accent shadow-md"
            : "border-ink-700 hover:border-accent"
        }
      `}
    >
      <h3 className="font-sora text-base font-semibold text-ink-100 mb-1.5">
        {label}
      </h3>
      <p className="font-dm-mono text-sm text-ink-300 leading-relaxed">
        {description}
      </p>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  City Card                                                          */
/* ------------------------------------------------------------------ */

function CityCard({
  city,
  country,
  imageUrl,
  tagline,
}: {
  city: string;
  country: string;
  imageUrl: string | null;
  tagline: string | null;
}) {
  // Unsplash fallback: generic city travel photo
  const src =
    imageUrl ??
    `https://source.unsplash.com/800x500/?${encodeURIComponent(city)}+travel`;

  return (
    <div className="rounded-xl overflow-hidden border border-ink-700 shadow-card">
      {/* Image with overlay */}
      <div className="relative w-full aspect-[16/9]">
        <img
          src={src}
          alt={`${city}, ${country} -- atmospheric travel photo`}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        <div className="photo-overlay-warm absolute inset-0" />
        <div className="absolute bottom-0 left-0 p-5">
          <h3 className="font-sora text-xl font-semibold text-white leading-tight">
            {city}
          </h3>
          <p className="font-dm-mono text-xs text-white/70 mt-0.5">
            {country}
          </p>
        </div>
      </div>

      {/* Tagline + CTA */}
      <div className="bg-surface p-5">
        {tagline && (
          <p
            className="font-dm-mono text-sm text-ink-300 leading-relaxed mb-4"
            aria-describedby={`tagline-${city}`}
          >
            {tagline}
          </p>
        )}
        <Link
          href={`/onboard?city=${encodeURIComponent(city)}&country=${encodeURIComponent(country)}`}
          className="btn-primary inline-flex items-center gap-1.5"
        >
          Plan this trip
          <ArrowRightIcon className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading skeleton                                                    */
/* ------------------------------------------------------------------ */

function ShortlistSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading destinations">
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-xl overflow-hidden border border-ink-700">
          <div className="skel w-full aspect-[16/9]" />
          <div className="bg-surface p-5 space-y-3">
            <div className="skel h-4 w-2/3 rounded" />
            <div className="skel h-9 w-36 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                      */
/* ------------------------------------------------------------------ */

export default function ExploreClient({ userId: _userId }: ExploreClientProps) {
  const [selectedVibe, setSelectedVibe] = useState<VibeKey | null>(null);
  const [cities, setCities] = useState<CityResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // FALLBACK: If confident guess returns null (Qdrant down, insufficient data),
  // render vibe-first flow. Never show error state on this surface.
  // For MVP, only the vibe-first path exists. Confident guess is v2.

  const fetchCities = useCallback(async (vibeKey: VibeKey) => {
    setSelectedVibe(vibeKey);
    setCities(null);
    setLoading(true);
    setError(false);

    try {
      const res = await fetch(
        `/api/explore/vibes?key=${encodeURIComponent(vibeKey)}`
      );

      if (!res.ok) {
        setError(true);
        setLoading(false);
        return;
      }

      const data = await res.json();
      setCities(data.cities ?? []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const resetToVibes = useCallback(() => {
    setSelectedVibe(null);
    setCities(null);
    setError(false);
  }, []);

  // ------- State 2: Shortlist -------
  if (selectedVibe && (loading || cities !== null || error)) {
    return (
      <div className="min-h-screen bg-base">
        <div className="mx-auto max-w-xl px-5 py-12">
          {/* Back button */}
          <button
            type="button"
            onClick={resetToVibes}
            className="btn-ghost flex items-center gap-1 mb-8"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Try another vibe
          </button>

          {/* Loading */}
          {loading && <ShortlistSkeleton />}

          {/* Results */}
          {!loading && cities && cities.length > 0 && (
            <div className="space-y-5" role="list" aria-label="Destination shortlist">
              {cities.map((c) => (
                <div key={`${c.city}-${c.country}`} role="listitem">
                  <CityCard
                    city={c.city}
                    country={c.country}
                    imageUrl={c.imageUrl}
                    tagline={c.tagline}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!loading && cities && cities.length === 0 && (
            <div className="text-center py-16">
              <h2 className="font-sora text-lg font-semibold text-ink-100 mb-2">
                We are still mapping this vibe
              </h2>
              <p className="font-dm-mono text-sm text-ink-400 mb-8">
                Check back soon or try a different one
              </p>
              <button
                type="button"
                onClick={resetToVibes}
                className="btn-primary"
              >
                Back to vibes
              </button>
            </div>
          )}

          {/* Error fallback: silently show empty state, never expose errors */}
          {!loading && error && (
            <div className="text-center py-16">
              <h2 className="font-sora text-lg font-semibold text-ink-100 mb-2">
                We are still mapping this vibe
              </h2>
              <p className="font-dm-mono text-sm text-ink-400 mb-8">
                Check back soon or try a different one
              </p>
              <button
                type="button"
                onClick={resetToVibes}
                className="btn-primary"
              >
                Back to vibes
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ------- State 1: Vibe Selection -------
  return (
    <div className="min-h-screen bg-base">
      <div className="mx-auto max-w-xl px-5 py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-sora text-2xl font-semibold text-ink-100 mb-2">
            Where should you go next?
          </h1>
          <p className="font-dm-mono text-sm text-ink-400">
            Pick the vibe that sounds right
          </p>
        </div>

        {/* 2x2 vibe grid */}
        <div
          className="grid grid-cols-1 sm:grid-cols-2 gap-4"
          role="radiogroup"
          aria-label="Vibe archetypes"
        >
          {VIBE_ARCHETYPE_LIST.map((vibe) => (
            <VibeCard
              key={vibe.key}
              label={vibe.label}
              description={vibe.description}
              selected={selectedVibe === vibe.key}
              onSelect={() => fetchCities(vibe.key)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
