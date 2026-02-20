"use client";

// Trip Detail Page — /trip/[id]
// Shows DayNavigation + DayView for the selected trip.
// Currently uses mock data; will be replaced with server-side fetch from Prisma.

import { useState, useCallback, useMemo } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { DayNavigation } from "@/components/trip/DayNavigation";
import { DayView } from "@/components/trip/DayView";
import { type SlotData } from "@/components/slot/SlotCard";
import { type SlotActionEvent } from "@/components/slot/SlotActions";

// ---------- Mock data (replaced by API/Prisma in production) ----------

const MOCK_TRIP = {
  id: "trip-001",
  destination: "Tokyo",
  city: "Tokyo",
  country: "Japan",
  timezone: "Asia/Tokyo",
  startDate: "2026-03-15T00:00:00+09:00",
  endDate: "2026-03-19T00:00:00+09:00",
  totalDays: 5,
  status: "active" as const,
};

const MOCK_SLOTS: Record<number, SlotData[]> = {
  1: [
    {
      id: "slot-001",
      activityName: "Tsukiji Outer Market",
      imageUrl: "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=800&q=80",
      startTime: "2026-03-15T09:00:00+09:00",
      endTime: "2026-03-15T11:00:00+09:00",
      durationMinutes: 120,
      slotType: "anchor",
      status: "confirmed",
      isLocked: false,
      vibeTags: [
        { slug: "local-favorite", name: "Local Favorite" },
        { slug: "morning-ritual", name: "Morning Ritual" },
        { slug: "street-food", name: "Street Food" },
      ],
      primaryVibeSlug: "local-favorite",
      activityNodeId: "node-001",
    },
    {
      id: "slot-002",
      activityName: "TeamLab Borderless",
      imageUrl: "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=800&q=80",
      startTime: "2026-03-15T13:00:00+09:00",
      endTime: "2026-03-15T15:30:00+09:00",
      durationMinutes: 150,
      slotType: "anchor",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "immersive", name: "Immersive" },
        { slug: "worth-the-hype", name: "Worth the Hype" },
      ],
      primaryVibeSlug: "immersive",
      activityNodeId: "node-002",
    },
    {
      id: "slot-003",
      activityName: "Shibuya Evening Walk",
      imageUrl: "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=800&q=80",
      startTime: "2026-03-15T18:00:00+09:00",
      endTime: "2026-03-15T19:30:00+09:00",
      durationMinutes: 90,
      slotType: "flex",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "night-vibes", name: "Night Vibes" },
        { slug: "iconic", name: "Iconic" },
      ],
      primaryVibeSlug: "night-vibes",
      activityNodeId: "node-003",
    },
    {
      id: "slot-004",
      activityName: "Omoide Yokocho",
      imageUrl: "https://images.unsplash.com/photo-1554797589-7241bb691973?w=800&q=80",
      startTime: "2026-03-15T20:00:00+09:00",
      endTime: "2026-03-15T21:30:00+09:00",
      durationMinutes: 90,
      slotType: "meal",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "hole-in-the-wall", name: "Hole in the Wall" },
        { slug: "late-night", name: "Late Night" },
        { slug: "local-favorite", name: "Local Favorite" },
      ],
      primaryVibeSlug: "hole-in-the-wall",
      activityNodeId: "node-004",
    },
  ],
  2: [
    {
      id: "slot-005",
      activityName: "Meiji Shrine Morning",
      imageUrl: "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=800&q=80",
      startTime: "2026-03-16T08:00:00+09:00",
      endTime: "2026-03-16T09:30:00+09:00",
      durationMinutes: 90,
      slotType: "anchor",
      status: "confirmed",
      isLocked: true,
      vibeTags: [
        { slug: "peaceful", name: "Peaceful" },
        { slug: "cultural", name: "Cultural" },
      ],
      primaryVibeSlug: "peaceful",
      activityNodeId: "node-005",
    },
    {
      id: "slot-006",
      activityName: "Harajuku Backstreets",
      imageUrl: "https://images.unsplash.com/photo-1480796927426-f609979314bd?w=800&q=80",
      startTime: "2026-03-16T11:00:00+09:00",
      endTime: "2026-03-16T13:00:00+09:00",
      durationMinutes: 120,
      slotType: "flex",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "quirky", name: "Quirky" },
        { slug: "shopping", name: "Shopping" },
        { slug: "instagram-worthy", name: "Instagram Worthy" },
        { slug: "youth-culture", name: "Youth Culture" },
        { slug: "street-fashion", name: "Street Fashion" },
      ],
      primaryVibeSlug: "quirky",
      activityNodeId: "node-006",
    },
  ],
  3: [],
  4: [
    {
      id: "slot-007",
      activityName: "Akihabara Deep Dive",
      startTime: "2026-03-18T14:00:00+09:00",
      endTime: "2026-03-18T17:00:00+09:00",
      durationMinutes: 180,
      slotType: "flex",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "niche", name: "Niche" },
        { slug: "iconic", name: "Iconic" },
      ],
      primaryVibeSlug: "niche",
      activityNodeId: "node-007",
    },
  ],
  5: [
    {
      id: "slot-008",
      activityName: "Shinjuku Gyoen Farewell Walk",
      imageUrl: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=800&q=80",
      startTime: "2026-03-19T10:00:00+09:00",
      endTime: "2026-03-19T12:00:00+09:00",
      durationMinutes: 120,
      slotType: "anchor",
      status: "proposed",
      isLocked: false,
      vibeTags: [
        { slug: "peaceful", name: "Peaceful" },
        { slug: "scenic", name: "Scenic" },
      ],
      primaryVibeSlug: "scenic",
      activityNodeId: "node-008",
    },
  ],
};

// ---------- Component ----------

export default function TripDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [currentDay, setCurrentDay] = useState(1);

  // In production, fetch trip + slots from API using params.id
  const trip = MOCK_TRIP;
  const slotsForDay = useMemo(
    () => MOCK_SLOTS[currentDay] || [],
    [currentDay]
  );

  const handleSlotAction = useCallback(
    (event: SlotActionEvent) => {
      // In production: POST to /api/behavioral-signals
      // {
      //   userId: session.user.id,
      //   tripId: params.id,
      //   slotId: event.slotId,
      //   signalType: event.signalType,
      //   signalValue: event.signalValue,
      //   tripPhase: "pre_trip",
      //   rawAction: event.action,
      //   surface: "day_view",
      // }
      console.log("[BehavioralSignal]", {
        tripId: params.id,
        ...event,
        surface: "day_view",
      });
    },
    [params.id]
  );

  // Count slots per status for summary
  const statusSummary = useMemo(() => {
    const allSlots = Object.values(MOCK_SLOTS).flat();
    return {
      total: allSlots.length,
      confirmed: allSlots.filter((s) => s.status === "confirmed").length,
      proposed: allSlots.filter(
        (s) => s.status === "proposed" || s.status === "voted"
      ).length,
    };
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Trip header */}
        <header className="space-y-1">
          <h1 className="font-sora text-2xl sm:text-3xl font-bold text-warm-text-primary">
            {trip.destination}
          </h1>
          <div className="flex items-center gap-3 font-dm-mono text-xs text-warm-text-secondary uppercase tracking-wider">
            <span>{trip.city}, {trip.country}</span>
            <span aria-hidden="true" className="text-warm-border">|</span>
            <span>{trip.totalDays} days</span>
            <span aria-hidden="true" className="text-warm-border">|</span>
            <span>
              {statusSummary.confirmed}/{statusSummary.total} confirmed
            </span>
          </div>
        </header>

        {/* Day navigation */}
        <DayNavigation
          totalDays={trip.totalDays}
          currentDay={currentDay}
          onDayChange={setCurrentDay}
          startDate={trip.startDate}
          timezone={trip.timezone}
        />

        {/* Day header */}
        <div className="flex items-center justify-between">
          <h2 className="font-sora text-lg font-semibold text-warm-text-primary">
            Day {currentDay}
          </h2>
          <span className="font-dm-mono text-xs text-warm-text-secondary uppercase tracking-wider">
            {slotsForDay.length} {slotsForDay.length === 1 ? "activity" : "activities"}
          </span>
        </div>

        {/* Timeline day view */}
        <DayView
          dayNumber={currentDay}
          slots={slotsForDay}
          timezone={trip.timezone}
          onSlotAction={handleSlotAction}
        />
      </div>
    </AppShell>
  );
}
