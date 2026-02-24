"use client";

// Dashboard Page -- /dashboard
// Fetches the user's trips and renders hero cards for active trips,
// compact rows for past trips, and a QuickStartGrid when no trips exist.

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { TripHeroCard, type TripSummary } from "@/components/dashboard/TripHeroCard";
import { DraftIdeaCard } from "@/components/dashboard/DraftIdeaCard";
import { DiaryTripCard, type BackfillTripSummary } from "@/components/dashboard/DiaryTripCard";
import { PastTripRow } from "@/components/dashboard/PastTripRow";
import { QuickStartGrid } from "@/components/dashboard/QuickStartGrid";
import { CardSkeleton, ErrorState } from "@/components/states";

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

// ---------- Component ----------

type FetchState = "loading" | "error" | "success";

export default function DashboardPage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [backfillTrips, setBackfillTrips] = useState<BackfillTripSummary[]>([]);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [errorMessage, setErrorMessage] = useState("Failed to load trips");

  const fetchTrips = useCallback(async () => {
    setFetchState("loading");
    try {
      const [tripsRes, backfillRes] = await Promise.all([
        fetch("/api/trips"),
        fetch("/api/backfill/trips"),
      ]);
      if (!tripsRes.ok) {
        const data = await tripsRes.json().catch(() => ({}));
        throw new Error(data.error || "Failed to load trips");
      }
      const { trips: tripList } = await tripsRes.json();
      setTrips(tripList);

      // Backfill trips are non-critical — fail silently
      if (backfillRes.ok) {
        const { trips: bfList } = await backfillRes.json();
        setBackfillTrips(bfList);
      }

      setFetchState("success");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load trips"
      );
      setFetchState("error");
    }
  }, []);

  useEffect(() => {
    fetchTrips();
  }, [fetchTrips]);

  // Partition trips into committed, draft, and past
  const committedTrips = trips.filter(
    (t) => t.status === "planning" || t.status === "active"
  );
  const draftTrips = trips.filter((t) => t.status === "draft");
  const pastTrips = trips.filter(
    (t) => t.status === "completed" || t.status === "archived"
  );
  const showLabels =
    (committedTrips.length + draftTrips.length) > 0 &&
    (pastTrips.length > 0 || backfillTrips.length > 0);

  return (
    <AppShell context="app">
      <div className="space-y-8">
        {/* Page header */}
        <header className="flex items-baseline justify-between">
          <div>
            <h1 className="font-sora text-2xl font-medium text-ink-100 sm:text-3xl">
              Your trips
            </h1>
            <p className="mt-1 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
              Plan, track, revisit
            </p>
          </div>
          {fetchState === "success" && trips.length > 0 && (
            <Link
              href="/onboarding"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-sora text-sm text-accent transition-colors hover:bg-accent/10"
            >
              <PlusIcon className="h-4 w-4" />
              New trip
            </Link>
          )}
        </header>

        {/* Loading state */}
        {fetchState === "loading" && (
          <div className="space-y-4">
            <CardSkeleton className="h-56" />
            <CardSkeleton className="h-56" />
          </div>
        )}

        {/* Error state */}
        {fetchState === "error" && (
          <ErrorState message={errorMessage} onRetry={fetchTrips} />
        )}

        {/* Empty state -- action-forward launchpad (only when no trips AND no backfill trips) */}
        {fetchState === "success" && trips.length === 0 && backfillTrips.length === 0 && (
          <>
            <QuickStartGrid />
            <Link
              href="/explore"
              className="mt-2 inline-flex items-center gap-2 font-dm-mono text-sm text-ink-300 transition-colors hover:text-accent hover:underline"
            >
              Explore destinations <span aria-hidden="true">&rarr;</span>
            </Link>
          </>
        )}

        {/* Active trips (committed hero cards + draft idea cards) */}
        {fetchState === "success" &&
          (committedTrips.length > 0 || draftTrips.length > 0) && (
          <section aria-labelledby={showLabels ? "active-trips-heading" : undefined}>
            {showLabels && (
              <h2 id="active-trips-heading" className="sec-label mb-4">
                Active
              </h2>
            )}

            {/* Committed trips -- hero cards */}
            {committedTrips.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                {committedTrips.map((trip) => (
                  <TripHeroCard key={trip.id} trip={trip} />
                ))}
              </div>
            )}

            {/* Draft trips -- idea cards */}
            {draftTrips.length > 0 && (
              <div className={`grid gap-4 sm:grid-cols-2${committedTrips.length > 0 ? " mt-4" : ""}`}>
                {draftTrips.map((trip) => (
                  <DraftIdeaCard key={trip.id} trip={trip} />
                ))}
              </div>
            )}

            <Link
              href="/explore"
              className="mt-4 inline-flex items-center gap-2 font-dm-mono text-sm text-ink-400 transition-colors hover:text-accent hover:underline"
            >
              Explore destinations <span aria-hidden="true">&rarr;</span>
            </Link>
          </section>
        )}

        {/* Past Travels -- backfill diary trips */}
        {fetchState === "success" && backfillTrips.length > 0 && (
          <section aria-labelledby="diary-trips-heading">
            <h2 id="diary-trips-heading" className="sec-label mb-4">
              Past travels
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {backfillTrips.map((bt) => (
                <DiaryTripCard key={bt.id} trip={bt} />
              ))}
            </div>
          </section>
        )}

        {/* Backfill prompt -- when user has planned trips but no backfill trips */}
        {fetchState === "success" &&
          trips.length > 0 &&
          backfillTrips.length === 0 && (
          <section className="rounded-[20px] border border-ink-700 bg-surface p-5">
            <p className="font-sora text-sm text-ink-300">
              Traveled before Overplanned?
            </p>
            <p className="mt-1 font-dm-mono text-xs text-ink-400">
              Add past trips to help us personalize your recommendations.
            </p>
            <Link
              href="/onboarding?step=backfill"
              className="mt-3 inline-flex items-center gap-1 font-sora text-sm text-accent hover:text-accent/80 transition-colors"
            >
              <PlusIcon className="h-4 w-4" />
              Add a past trip
            </Link>
          </section>
        )}

        {/* Past trips */}
        {fetchState === "success" && pastTrips.length > 0 && (
          <section aria-labelledby={showLabels ? "past-trips-heading" : undefined}>
            {showLabels && (
              <h2 id="past-trips-heading" className="sec-label mb-4">
                Past trips
              </h2>
            )}
            <div className="space-y-2">
              {pastTrips.map((trip) => (
                <PastTripRow key={trip.id} trip={trip} />
              ))}
            </div>
          </section>
        )}
      </div>
    </AppShell>
  );
}
