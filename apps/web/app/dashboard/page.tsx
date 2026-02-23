"use client";

// Dashboard Page -- /dashboard
// Fetches the user's trips and renders hero cards for active trips,
// compact rows for past trips, and a QuickStartGrid when no trips exist.

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { TripHeroCard, type TripSummary } from "@/components/dashboard/TripHeroCard";
import { DraftIdeaCard } from "@/components/dashboard/DraftIdeaCard";
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
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [errorMessage, setErrorMessage] = useState("Failed to load trips");

  const fetchTrips = useCallback(async () => {
    setFetchState("loading");
    try {
      const res = await fetch("/api/trips");
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to load trips");
      }
      const { trips: tripList } = await res.json();
      setTrips(tripList);
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
    (committedTrips.length + draftTrips.length) > 0 && pastTrips.length > 0;

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
              Plan, track, and relive
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

        {/* Empty state -- action-forward launchpad */}
        {fetchState === "success" && trips.length === 0 && (
          <QuickStartGrid />
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
