"use client";

// Dashboard Page -- /dashboard
// Fetches the user's trips and renders hero cards for active trips,
// compact rows for past trips, and an EmptyState when no trips exist.

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { TripHeroCard, type TripSummary } from "@/components/dashboard/TripHeroCard";
import { PastTripRow } from "@/components/dashboard/PastTripRow";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/states";

// ---------- Icons ----------

function CompassIcon() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

// ---------- Component ----------

type FetchState = "loading" | "error" | "success";

export default function DashboardPage() {
  const router = useRouter();
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

  // Partition trips into active and past
  const activeTrips = trips.filter(
    (t) => t.status === "planning" || t.status === "active"
  );
  const pastTrips = trips.filter(
    (t) => t.status === "completed" || t.status === "cancelled"
  );

  return (
    <AppShell context="app">
      <div className="space-y-8">
        {/* Page header */}
        <header>
          <h1 className="font-sora text-2xl font-bold text-ink-100 sm:text-3xl">
            Your trips
          </h1>
          <p className="mt-1 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Plan, track, and relive
          </p>
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

        {/* Empty state */}
        {fetchState === "success" && trips.length === 0 && (
          <EmptyState
            icon={<CompassIcon />}
            title="Your adventures start here"
            description="Plan your first trip and we will build you a local-first itinerary."
            action={{
              label: "Plan a trip",
              onClick: () => router.push("/onboarding"),
            }}
          />
        )}

        {/* Active trips */}
        {fetchState === "success" && activeTrips.length > 0 && (
          <section aria-labelledby="active-trips-heading">
            <h2
              id="active-trips-heading"
              className="section-eyebrow mb-4"
            >
              Active
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {activeTrips.map((trip) => (
                <TripHeroCard key={trip.id} trip={trip} />
              ))}
            </div>
          </section>
        )}

        {/* Past trips */}
        {fetchState === "success" && pastTrips.length > 0 && (
          <section aria-labelledby="past-trips-heading">
            <h2
              id="past-trips-heading"
              className="section-eyebrow mb-4"
            >
              Past trips
            </h2>
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
