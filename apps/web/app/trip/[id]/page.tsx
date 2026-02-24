"use client";

// Trip Detail Page -- /trip/[id]
// Fetches real trip data from GET /api/trips/[id] and renders
// DayNavigation + DayView with actual slots.

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { DayNavigation } from "@/components/trip/DayNavigation";
import { DayView } from "@/components/trip/DayView";
import { WelcomeCard } from "@/components/trip/WelcomeCard";
import { MemberAvatars } from "@/components/trip/MemberAvatars";
import { InviteButton } from "@/components/trip/InviteButton";
import { ShareButton } from "@/components/trip/ShareButton";
import { PackingList } from "@/components/trip/PackingList";
import { TripChat } from "@/components/trip/TripChat";
import { ExpenseTracker } from "@/components/trip/ExpenseTracker";
import { MoodPulse } from "@/components/trip/MoodPulse";
import { type SlotData } from "@/components/slot/SlotCard";
import { type SlotActionEvent } from "@/components/slot/SlotActions";
import { TripSettings } from "@/components/trip/TripSettings";
import { InviteCrewCard } from "@/components/trip/InviteCrewCard";
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
    voteState: slot.voteState,
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
  const router = useRouter();
  const tripId = params.id;

  const { trip, setTrip, myRole, myUserId, hasReflected, fetchState, errorMessage, fetchTrip } =
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

  // -- Invite crew card dismiss --
  const [inviteDismissed, setInviteDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return sessionStorage.getItem(`dismiss-invite-${tripId}`) === "1";
  });

  // -- Toast notification --
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 3000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  // -- Settings panel --
  const [showSettings, setShowSettings] = useState(false);
  const [showTripMenu, setShowTripMenu] = useState(false);
  const [archiveConfirm, setArchiveConfirm] = useState(false);

  // -- Chat drawer --
  const [chatOpen, setChatOpen] = useState(false);
  const [sharedSlotRef, setSharedSlotRef] = useState<{
    id: string; name: string; category: string; dayNumber: number;
  } | null>(null);

  const handleShareToChat = useCallback(
    (slot: { id: string; name: string; category: string; dayNumber: number }) => {
      setSharedSlotRef(slot);
      setChatOpen(true);
    },
    []
  );

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

  const handleArchiveTrip = useCallback(async () => {
    if (!trip) return;
    try {
      const res = await fetch(`/api/trips/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "archived" }),
      });
      if (res.ok) {
        router.push("/dashboard");
      }
    } catch {
      // silently fail
    }
  }, [trip, tripId, router]);

  const handleVote = useCallback(
    async (slotId: string, vote: string) => {
      if (!trip) return;
      try {
        await fetch(`/api/trips/${trip.id}/vote`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slotId, vote }),
        });
      } finally {
        fetchTrip();
      }
    },
    [trip, fetchTrip]
  );

  const handleTripUpdate = useCallback((dirtyFields?: Record<string, string>) => {
    fetchTrip();
    if (dirtyFields?.mode) {
      setToastMessage(`Switched to ${dirtyFields.mode} mode`);
      // Clear invite dismiss flag so card re-appears after mode toggle
      sessionStorage.removeItem(`dismiss-invite-${tripId}`);
      setInviteDismissed(false);
    }
  }, [fetchTrip, tripId]);

  const handleDeleteTrip = useCallback(async () => {
    if (!trip) return;
    try {
      const res = await fetch(`/api/trips/${tripId}`, { method: "DELETE" });
      if (res.ok) {
        router.push("/dashboard");
      }
    } catch {
      // silently fail
    }
  }, [trip, tripId, router]);

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
            className="inline-flex items-center gap-2 font-dm-mono text-xs text-ink-400 uppercase tracking-wider hover:text-accent transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-surface rounded"
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
            <div className="flex items-center justify-between gap-3">
              <h1 className="font-sora text-2xl sm:text-3xl font-medium text-ink-100 min-w-0 truncate">
                {trip!.destination}
              </h1>
              <div className="flex items-center gap-2 shrink-0">
                {/* Member avatars — group trips with 2+ joined members */}
                {trip!.mode === "group" && trip!.members && (
                  <MemberAvatars members={trip!.members} />
                )}

                {/* Chat toggle — group trips */}
                {trip!.mode === "group" && (
                  <button
                    onClick={() => setChatOpen(true)}
                    className="rounded-lg p-2 text-ink-400 hover:text-ink-100 hover:bg-surface transition-colors"
                    aria-label="Open trip chat"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                    </svg>
                  </button>
                )}

                {/* Invite button — group organizer, planning or active */}
                {trip!.mode === "group" &&
                  myRole === "organizer" &&
                  (trip!.status === "planning" || trip!.status === "active") && (
                    <InviteButton tripId={trip!.id} />
                  )}

                {/* Share button — any status that's meaningful to share */}
                {(trip!.status === "planning" ||
                  trip!.status === "active" ||
                  trip!.status === "completed") && (
                  <ShareButton tripId={trip!.id} />
                )}

                {myRole === "organizer" && (
                  <div className="relative">
                    <button
                      onClick={() => setShowTripMenu(prev => !prev)}
                      className="rounded-lg p-2 text-ink-400 hover:text-ink-100 hover:bg-surface transition-colors"
                      aria-label="Trip menu"
                    >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <circle cx="12" cy="5" r="1" />
                      <circle cx="12" cy="12" r="1" />
                      <circle cx="12" cy="19" r="1" />
                    </svg>
                  </button>
                  {showTripMenu && (
                    <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-ink-700 bg-surface shadow-lg z-20 overflow-hidden">
                      <button
                        onClick={() => { setShowTripMenu(false); setShowSettings(prev => !prev); }}
                        className="w-full px-4 py-3 text-left font-sora text-sm text-ink-100 hover:bg-surface transition-colors flex items-center gap-2"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <circle cx="12" cy="12" r="3" />
                          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
                        </svg>
                        Settings
                      </button>
                      <div className="border-t border-ink-700" />
                      {!archiveConfirm ? (
                        <button
                          onClick={() => setArchiveConfirm(true)}
                          className="w-full px-4 py-3 text-left font-sora text-sm text-red-400 hover:bg-red-400/5 transition-colors flex items-center gap-2"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <polyline points="21 8 21 21 3 21 3 8" />
                            <rect x="1" y="3" width="22" height="5" />
                            <line x1="10" y1="12" x2="14" y2="12" />
                          </svg>
                          Archive trip
                        </button>
                      ) : (
                        <div className="px-4 py-3 space-y-2">
                          <p className="font-dm-mono text-xs text-ink-400">Are you sure?</p>
                          <div className="flex gap-2">
                            <button
                              onClick={() => setArchiveConfirm(false)}
                              className="rounded-lg px-3 py-1.5 font-sora text-xs text-ink-400 hover:text-ink-100 transition-colors"
                            >
                              No
                            </button>
                            <button
                              onClick={handleArchiveTrip}
                              className="rounded-lg px-3 py-1.5 font-sora text-xs font-medium text-red-400 border border-red-400/30 hover:bg-red-400/10 transition-colors"
                            >
                              Yes, archive
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              </div>
            </div>
            <div className="flex items-center gap-3 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
              {trip!.mode === "group" && (
                <>
                  <span className="bg-accent text-white font-dm-mono text-[10px] uppercase rounded-full px-2 py-0.5">
                    Group
                  </span>
                  <span aria-hidden="true" className="text-ink-700">|</span>
                </>
              )}
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
              onTripUpdate={handleTripUpdate}
            />
          )}

          {/* Completion banner — organizer only, shown after end date */}
          {trip!.status === "active" && myRole === "organizer" && new Date(trip!.endDate) < new Date() && (
            <div className="rounded-xl border border-ink-700 bg-surface p-4 flex items-center justify-between">
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

          {/* Invite crew card — group organizer with <2 joined members, not dismissed */}
          {trip!.mode === "group" &&
            myRole === "organizer" &&
            (trip!.members?.filter((m) => m.status === "joined").length ?? 0) < 2 &&
            !inviteDismissed && (
              <InviteCrewCard
                tripId={trip!.id}
                onDismiss={() => {
                  sessionStorage.setItem(`dismiss-invite-${tripId}`, "1");
                  setInviteDismissed(true);
                }}
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
          {/* Mood pulse — active trips only, auto-hides */}
          {trip!.status === "active" && myUserId && (
            <MoodPulse
              tripId={trip!.id}
              tripStatus={trip!.status}
              energyProfile={trip!.energyProfile}
            />
          )}

          <DayView
            dayNumber={currentDay}
            slots={slotsForDay}
            timezone={trip!.timezone}
            onSlotAction={handleSlotAction}
            totalDays={totalDays}
            showVoting={trip!.mode === "group" && (trip!.status === "planning" || trip!.status === "active")}
            tripId={trip!.id}
            myUserId={myUserId}
            onVote={handleVote}
            showPivot={trip!.mode === "group" && (trip!.status === "planning" || trip!.status === "active")}
            onPivotCreated={fetchTrip}
            onShareToChat={trip!.mode === "group" ? handleShareToChat : undefined}
          />

          {/* Packing list — active or completed trips only */}
          {(trip!.status === "active" || trip!.status === "completed") && (
            <PackingList
              tripId={trip!.id}
              packingList={trip!.packingList}
              onUpdate={fetchTrip}
              currentUserId={myUserId ?? undefined}
              members={trip!.members?.filter(m => m.status === "joined")}
            />
          )}

          {/* Expense tracker — group trips only */}
          {trip!.mode === "group" && trip!.members && myUserId && (
            <ExpenseTracker
              tripId={trip!.id}
              currentUserId={myUserId}
              currency={trip!.currency ?? "USD"}
              members={trip!.members.filter(m => m.status === "joined")}
            />
          )}

          {/* Reflection link card — completed trips, not yet reflected */}
          {trip!.status === "completed" && !hasReflected && (
            <div className="rounded-xl border border-ink-700 bg-surface p-5">
              <h3 className="font-sora text-base font-semibold text-ink-100">
                How was your trip?
              </h3>
              <p className="mt-1 font-dm-mono text-xs text-ink-400">
                Share your thoughts and help us plan better next time
              </p>
              <Link
                href={`/trip/${trip!.id}/reflection`}
                className="
                  mt-4 inline-flex items-center gap-2 rounded-lg
                  bg-accent px-5 py-2.5
                  font-dm-mono text-sm text-white uppercase tracking-wider
                  hover:bg-accent/90 transition-colors duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2
                "
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
                Share reflection
              </Link>
            </div>
          )}
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

      {/* Toast notification */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 rounded-lg bg-ink-100 px-4 py-2.5 shadow-lg">
          <p className="font-dm-mono text-sm text-white">{toastMessage}</p>
        </div>
      )}

      {/* Trip chat drawer — group trips */}
      {trip!.mode === "group" && myUserId && (
        <TripChat
          tripId={trip!.id}
          isOpen={chatOpen}
          onClose={() => setChatOpen(false)}
          currentUserId={myUserId}
          sharedSlotRef={sharedSlotRef}
          onClearSharedSlot={() => setSharedSlotRef(null)}
        />
      )}
    </AppShell>
  );
}
