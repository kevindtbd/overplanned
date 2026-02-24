"use client";

import { useParams, useRouter } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import { RevealAnimation } from "@/components/trip/RevealAnimation";
import type { ItinerarySlot } from "@/components/trip/RevealAnimation";

// ─── Types ───────────────────────────────────────────────────────────────────

interface TripMeta {
  id: string;
  name: string;
  destination: string;
  city: string;
  startDate: string;
  endDate: string;
}

// ─── SVG Icons ───────────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className ?? ""}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        opacity={0.2}
      />
      <path
        d="M12 2a10 10 0 019.95 9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function AlertIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

// ─── Page Component ──────────────────────────────────────────────────────────

export default function GeneratingPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tripId = params.id;

  const [tripMeta, setTripMeta] = useState<TripMeta | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch trip metadata so we can display name + destination
  useEffect(() => {
    let cancelled = false;

    async function fetchTrip() {
      try {
        const res = await fetch(`/api/trips/${tripId}`);
        if (!res.ok) {
          throw new Error(
            res.status === 404
              ? "Trip not found"
              : `Failed to load trip (${res.status})`
          );
        }
        const data = await res.json();
        if (!cancelled) {
          setTripMeta({
            id: data.id,
            name: data.name,
            destination: data.destination,
            city: data.city,
            startDate: data.startDate,
            endDate: data.endDate,
          });
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Failed to load trip"
          );
          setIsLoading(false);
        }
      }
    }

    fetchTrip();
    return () => {
      cancelled = true;
    };
  }, [tripId]);

  // Navigate to the day-view itinerary on completion
  const handleComplete = useCallback(
    (_slots: ItinerarySlot[]) => {
      router.push(`/trips/${tripId}`);
    },
    [router, tripId]
  );

  // Retry generation
  const handleRetry = useCallback(async () => {
    try {
      const res = await fetch(`/api/trips/${tripId}/generate`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error("Failed to restart generation");
      }
      // Force re-mount of RevealAnimation by toggling key
      setTripMeta((prev) => (prev ? { ...prev } : prev));
    } catch {
      // If retry request itself fails, stay on current state
      // RevealAnimation will continue showing the error
    }
  }, [tripId]);

  // ── Loading state ──
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base">
        <div className="flex flex-col items-center gap-3">
          <SpinnerIcon className="h-8 w-8 text-accent" />
          <p className="font-dm-mono text-sm text-secondary">
            Loading trip...
          </p>
        </div>
      </div>
    );
  }

  // ── Error loading trip metadata ──
  if (loadError || !tripMeta) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base">
        <div className="flex flex-col items-center gap-4 px-4 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-error-bg dark:bg-red-950/30">
            <AlertIcon className="h-7 w-7 text-error" />
          </div>
          <div>
            <h2 className="font-sora text-lg font-semibold text-primary">
              Could not load trip
            </h2>
            <p className="mt-1 max-w-sm font-dm-mono text-sm text-secondary">
              {loadError ?? "The trip could not be found."}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => router.back()}
              className="btn-secondary flex items-center gap-2"
            >
              <ArrowLeftIcon className="h-4 w-4" />
              <span>Go back</span>
            </button>
            <button
              onClick={() => window.location.reload()}
              className="btn-primary"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Main: reveal animation ──
  return (
    <RevealAnimation
      key={tripMeta.id + tripMeta.name}
      tripId={tripMeta.id}
      tripName={tripMeta.name}
      destination={`${tripMeta.city ?? tripMeta.destination}`}
      onComplete={handleComplete}
      onRetry={handleRetry}
    />
  );
}
