"use client";

// Trip Detail Page -- /trip/[id]
// Fetches real trip data from GET /api/trips/[id] and renders
// DayNavigation + DayView with actual slots.

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { DayNavigation } from "@/components/trip/DayNavigation";
import { DayView } from "@/components/trip/DayView";
import { WelcomeCard } from "@/components/trip/WelcomeCard";
import { type SlotData } from "@/components/slot/SlotCard";
import { type SlotActionEvent } from "@/components/slot/SlotActions";
import { TripSettings } from "@/components/trip/TripSettings";
import { SlotSkeleton, ErrorState } from "@/components/states";
import { getCityPhoto } from "@/lib/city-photos";
import { useTripDetail, type ApiSlot } from "@/lib/hooks/useTripDetail";

// ---------- Helpers ----------

function apiSlotToSlotData(slot: ApiSlot): SlotData {
  return {
    id: slot.id,
    activityName: slot.activityNode?.name ?? "Unnamed Activity",
    imageUrl: slot.activityNode?.primaryImageUrl ?? undefined,
    startTime: slot.startTime ?? undefined,
    endTime: slot.endTime ?? undefined,
    durationMinutes: slot.durationMinutes ?? undefined,
    slotType: slot.slotType as SlotData["slotType"],
    status: slot.status as SlotData["status"],
    isLocked: slot.isLocked,
    vibeTags: [], // Vibe tags would need a separate join; empty for now
    activityNodeId: slot.activityNode?.id,
  };
}

function computeTotalDays(startDate: string, endDate: string): number {
  const start = new Date(startDate);
  const end = new Date(endDate);
  const diff = Math.ceil(
    (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
  );
  return Math.max(diff, 1);
}

// ---------- Component ----------

export default function TripDetailPage() {
  const params = useParams<{ id: string }>();
  const tripId = params.id;

  const { trip, setTrip, myRole, fetchState, errorMessage, fetchTrip } =
    useTripDetail(tripId);

  const [currentDay, setCurrentDay] = useState(1);

  // -- Welcome card (post-creation feedback) --
  const [showWelcome, setShowWelcome] = useState(false);

  useEffect(() => {
    const key = `new-trip-${tripId}`;
    if (sessionStorage.getItem(key) === "1") {
      sessionStorage.removeItem(key);
      setShowWelcome(true);
    }
  }, [tripId]);

  // -- Settings panel --
  const [showSettings, setShowSettings] = useState(false);

  // -- FAB scroll collapse --
  const [fabCompact, setFabCompact] = useState(false);

  useEffect(() => {
    let lastY = 0;
    function onScroll() {
      const y = window.scrollY;
      setFabCompact(y > 80 && y > lastY);
      lastY = y;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // -- Progress pulse --
  const [confirmPulse, setConfirmPulse] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
    };
  }, []);

  // Compute derived data
  const totalDays = useMemo(() => {
    if (!trip) return 1;
    return computeTotalDays(trip.startDate, trip.endDate);
  }, [trip]);

  const slotsByDay = useMemo(() => {
    if (!trip) return {};
    const grouped: Record<number, SlotData[]> = {};
    for (const slot of trip.slots) {
      const day = slot.dayNumber;
      if (!grouped[day]) grouped[day] = [];
      grouped[day].push(apiSlotToSlotData(slot));
    }
    return grouped;
  }, [trip]);

  const slotsForDay = useMemo(
    () => slotsByDay[currentDay] || [],
    [slotsByDay, currentDay]
  );

  const handleSlotAction = useCallback(
    async (event: SlotActionEvent) => {
      // Dismiss welcome card on first slot action
      setShowWelcome(false);

      // Move action — delegate to move endpoint, refetch on completion
      if (event.action === "move" && event.moveData) {
        try {
          const res = await fetch(`/api/slots/${event.slotId}/move`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(event.moveData),
          });
          if (res.ok) {
            fetchTrip();
          }
        } catch {
          fetchTrip();
        }
        return;
      }

      // Progress pulse on confirm
      if (event.action === "confirm") {
        if (pulseTimer.current) clearTimeout(pulseTimer.current);
        setConfirmPulse(true);
        pulseTimer.current = setTimeout(() => setConfirmPulse(false), 600);
      }

      // Optimistic update
      setTrip((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          slots: prev.slots.map((s) => {
            if (s.id !== event.slotId) return s;
            if (event.action === "lock") {
              return { ...s, isLocked: !s.isLocked };
            }
            if (event.action === "confirm") {
              return { ...s, status: "confirmed" };
            }
            if (event.action === "skip") {
              return { ...s, status: "skipped" };
            }
            return s;
          }),
        };
      });

      // Fire API call
      try {
        const res = await fetch(`/api/slots/${event.slotId}/status`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: event.action }),
        });
        if (!res.ok) {
          // Revert on failure
          fetchTrip();
        }
      } catch {
        fetchTrip();
      }
    },
    [fetchTrip, setTrip]
  );

  const handleStartTrip = useCallback(async () => {
    if (!trip) return;
    setTrip(prev => prev ? { ...prev, status: "active" } : prev);
    try {
      const res = await fetch(`/api/trips/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "active" }),
      });
      if (!res.ok) {
        fetchTrip();
      }
    } catch {
      fetchTrip();
    }
  }, [trip, tripId, fetchTrip, setTrip]);

  const handleCompleteTrip = useCallback(async () => {
    if (!trip) return;
    setTrip(prev => prev ? { ...prev, status: "completed" } : prev);
    try {
      const res = await fetch(`/api/trips/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "completed" }),
      });
      if (!res.ok) {
        fetchTrip();
      }
    } catch {
      fetchTrip();
    }
  }, [trip, tripId, fetchTrip, setTrip]);

  // Status summary across all days
  const statusSummary = useMemo(() => {
    if (!trip) return { total: 0, confirmed: 0, proposed: 0 };
    const allSlots = trip.slots;
    return {
      total: allSlots.length,
      confirmed: allSlots.filter(
        (s) => s.status === "confirmed" || s.status === "active"
      ).length,
      proposed: allSlots.filter(
        (s) => s.status === "proposed" || s.status === "voted"
      ).length,
    };
  }, [trip]);

  const tripPhoto = trip ? getCityPhoto(trip.city) : undefined;
  const tripName = trip?.name || trip?.destination || "";
  const discoverUrl = trip
    ? `/discover?city=${encodeURIComponent(trip.city)}&tripId=${trip.id}&day=${currentDay}`
    : "/discover";

  // -- Loading --
  if (fetchState === "loading") {
    return (
      <AppShell context="trip" tripName="Loading...">
        <div className="space-y-6">
          <div className="space-y-1">
            <div className="skel h-7 w-48 rounded-full" />
            <div className="skel h-4 w-32 rounded-full mt-2" />
          </div>
          <div className="flex gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="skel h-14 w-20 rounded-lg" />
            ))}
          </div>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex gap-4">
              <div className="w-16 flex flex-col items-center gap-2">
                <div className="skel h-3 w-12 rounded-full" />
                <div className="skel h-3 w-3 rounded-full" />
              </div>
              <div className="flex-1">
                <SlotSkeleton />
              </div>
            </div>
          ))}
        </div>
      </AppShell>
    );
  }

  // -- Error --
  if (fetchState === "error") {
    return (
      <AppShell context="app">
        <div className="py-12">
          <ErrorState message={errorMessage} onRetry={fetchTrip} />
        </div>
      </AppShell>
    );
  }

  // -- Success --
  return (
    <AppShell
      context="trip"
      tripPhoto={tripPhoto}
      tripName={tripName}
    >
      <div className="bg-surface rounded-[22px] border border-ink-800 shadow-lg overflow-hidden">
        <div className="space-y-6 p-5 sm:p-6">
          {/* Back to trips */}
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 font-dm-mono text-xs text-ink-400 uppercase tracking-wider hover:text-terracotta transition-colors focus:outline-none focus:ring-2 focus:ring-terracotta focus:ring-offset-2 focus:ring-offset-surface rounded"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
            <span>Back to trips</span>
          </Link>

          {/* Trip header */}
          <header className="space-y-1">
            <div className="flex items-center justify-between">
              <h1 className="font-sora text-2xl sm:text-3xl font-medium text-ink-100">
                {trip!.destination}
              </h1>
              {myRole === "organizer" && (
                <button
                  onClick={() => setShowSettings(prev => !prev)}
                  className="rounded-lg p-2 text-ink-400 hover:text-ink-100 hover:bg-warm-surface transition-colors"
                  aria-label="Trip settings"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
                  </svg>
                </button>
              )}
            </div>
            <div className="flex items-center gap-3 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
              <span>
                {trip!.city}, {trip!.country}
              </span>
              <span aria-hidden="true" className="text-ink-700">
                |
              </span>
              <span>{totalDays} days</span>
              <span aria-hidden="true" className="text-ink-700">
                |
              </span>
              <span
                className={`transition-colors duration-300 ${confirmPulse ? "text-accent" : ""}`}
              >
                {statusSummary.confirmed}/{statusSummary.total} confirmed
              </span>
            </div>
            {trip!.status === "planning" && myRole === "organizer" && (
              <button
                onClick={handleStartTrip}
                className="mt-3 rounded-lg bg-accent px-4 py-2 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              >
                Start trip
              </button>
            )}
          </header>

          {/* Settings panel */}
          {showSettings && trip && (
            <TripSettings
              trip={trip}
              myRole={myRole!}
              onClose={() => setShowSettings(false)}
              onTripUpdate={fetchTrip}
            />
          )}

          {/* Completion banner — organizer only, shown after end date */}
          {trip!.status === "active" && myRole === "organizer" && new Date(trip!.endDate) < new Date() && (
            <div className="rounded-xl border border-warm-border bg-warm-surface p-4 flex items-center justify-between">
              <div>
                <p className="font-sora text-sm font-medium text-ink-100">Trip complete!</p>
                <p className="font-dm-mono text-xs text-ink-400 mt-0.5">Your trip dates have ended. Ready to wrap up?</p>
              </div>
              <button
                onClick={handleCompleteTrip}
                className="rounded-lg bg-accent px-3 py-1.5 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90 shrink-0 ml-4"
              >
                Mark as done
              </button>
            </div>
          )}

          {/* Day navigation */}
          <DayNavigation
            totalDays={totalDays}
            currentDay={currentDay}
            onDayChange={setCurrentDay}
            startDate={trip!.startDate}
            timezone={trip!.timezone}
          />

          {/* Welcome card -- post-creation feedback */}
          {showWelcome && (
            <WelcomeCard
              city={trip!.city}
              totalSlots={trip!.slots.length}
              totalDays={totalDays}
              onDismiss={() => setShowWelcome(false)}
            />
          )}

          {/* Day header */}
          <div className="flex items-center justify-between">
            <h2 className="font-sora text-lg font-medium text-ink-100">
              Day {currentDay}
            </h2>
            <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
              {slotsForDay.length}{" "}
              {slotsForDay.length === 1 ? "activity" : "activities"}
            </span>
          </div>

          {/* Timeline day view */}
          <DayView
            dayNumber={currentDay}
            slots={slotsForDay}
            timezone={trip!.timezone}
            onSlotAction={handleSlotAction}
            totalDays={totalDays}
          />
        </div>
      </div>

      {/* Add activity FAB — organizer only, labeled pill with scroll collapse */}
      {myRole === "organizer" && (
        <Link
          href={discoverUrl}
          className={`
            fixed z-30 bottom-24 right-5 lg:bottom-8 lg:right-8
            flex items-center justify-center gap-2
            h-14 rounded-full
            bg-accent hover:bg-accent/90 text-white shadow-lg
            transition-[width,padding] duration-200
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2
            ${fabCompact ? "w-14" : "px-5"}
          `}
          aria-label="Add activity"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            aria-hidden="true"
            className="flex-shrink-0"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {!fabCompact && (
            <span className="font-sora text-sm font-medium whitespace-nowrap">
              Add activity
            </span>
          )}
        </Link>
      )}
    </AppShell>
  );
}
