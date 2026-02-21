"use client";

// Trip Detail Page -- /trip/[id]
// Fetches real trip data from GET /api/trips/[id] and renders
// DayNavigation + DayView with actual slots.

import { useState, useCallback, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { DayNavigation } from "@/components/trip/DayNavigation";
import { DayView } from "@/components/trip/DayView";
import { type SlotData } from "@/components/slot/SlotCard";
import { type SlotActionEvent } from "@/components/slot/SlotActions";
import { SlotSkeleton, ErrorState } from "@/components/states";
import { getCityPhoto } from "@/lib/city-photos";

// ---------- Types for API response ----------

interface ApiSlot {
  id: string;
  dayNumber: number;
  sortOrder: number;
  slotType: string;
  status: string;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number | null;
  isLocked: boolean;
  activityNode: {
    id: string;
    name: string;
    category: string;
    latitude: number;
    longitude: number;
    priceLevel: number | null;
    primaryImageUrl?: string | null;
  } | null;
}

interface ApiTrip {
  id: string;
  name: string | null;
  destination: string;
  city: string;
  country: string;
  timezone: string;
  startDate: string;
  endDate: string;
  mode: string;
  status: string;
  planningProgress: number;
  slots: ApiSlot[];
  members: {
    id: string;
    userId: string;
    role: string;
    status: string;
    joinedAt: string;
    user: {
      id: string;
      name: string | null;
      avatarUrl: string | null;
    };
  }[];
}

type FetchState = "loading" | "error" | "success";

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

  const [trip, setTrip] = useState<ApiTrip | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [errorMessage, setErrorMessage] = useState("Failed to load trip");
  const [currentDay, setCurrentDay] = useState(1);

  const fetchTrip = useCallback(async () => {
    setFetchState("loading");
    try {
      const res = await fetch(`/api/trips/${tripId}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (res.status === 404) {
          throw new Error("Trip not found");
        }
        if (res.status === 403) {
          throw new Error("You do not have access to this trip");
        }
        throw new Error(data.error || "Failed to load trip");
      }
      const { trip: tripData, myRole: role } = await res.json();
      setTrip(tripData);
      setMyRole(role);
      setFetchState("success");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load trip"
      );
      setFetchState("error");
    }
  }, [tripId]);

  useEffect(() => {
    fetchTrip();
  }, [fetchTrip]);

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
    [fetchTrip]
  );

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
    ? `/discover?city=${encodeURIComponent(trip.city)}&tripId=${trip.id}`
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
            <h1 className="font-sora text-2xl sm:text-3xl font-medium text-ink-100">
              {trip!.destination}
            </h1>
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
              <span>
                {statusSummary.confirmed}/{statusSummary.total} confirmed
              </span>
            </div>
          </header>

          {/* Day navigation */}
          <DayNavigation
            totalDays={totalDays}
            currentDay={currentDay}
            onDayChange={setCurrentDay}
            startDate={trip!.startDate}
            timezone={trip!.timezone}
          />

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
          />
        </div>
      </div>

      {/* Add activity FAB — organizer only */}
      {myRole === "organizer" && (
        <Link
          href={discoverUrl}
          className="
            fixed z-30
            bottom-24 right-5
            lg:bottom-8 lg:right-8
            w-14 h-14 rounded-full
            bg-accent hover:bg-accent/90
            text-white shadow-lg
            flex items-center justify-center
            transition-all duration-150
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          "
          aria-label="Add activity"
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </Link>
      )}
    </AppShell>
  );
}
