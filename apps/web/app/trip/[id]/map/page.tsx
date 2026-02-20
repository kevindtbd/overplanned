/**
 * /trip/[id]/map — Map view page for a trip's itinerary.
 *
 * Loads itinerary slots for the trip and renders them on an interactive
 * Leaflet map with day filtering and slot detail interactions.
 *
 * Server component that fetches trip data, then delegates to the
 * client-side MapView for interactivity.
 */

import type { Metadata } from "next";
import dynamic from "next/dynamic";
import Link from "next/link";

// Dynamic import for MapView since Leaflet requires window/document
const MapView = dynamic(
  () => import("@/components/map/MapView"),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full bg-warm-background">
        <div className="flex flex-col items-center gap-3">
          <svg
            width="32"
            height="32"
            viewBox="0 0 32 32"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="animate-pulse"
            aria-hidden="true"
          >
            <path
              d="M16 2C9.373 2 4 7.373 4 14c0 9 12 16 12 16s12-7 12-16c0-6.627-5.373-12-12-12z"
              fill="var(--color-terracotta)"
              opacity="0.3"
            />
            <circle cx="16" cy="13" r="4" fill="var(--color-terracotta)" opacity="0.5" />
          </svg>
          <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
            Loading map
          </span>
        </div>
      </div>
    ),
  }
);

export const metadata: Metadata = {
  title: "Trip Map | Overplanned",
};

/**
 * In a real implementation this would fetch from the database via Prisma.
 * For now, define the data shape and use a placeholder fetch.
 */
async function getTripData(tripId: string) {
  // TODO: Replace with actual Prisma query
  // const trip = await prisma.trip.findUnique({
  //   where: { id: tripId },
  //   include: {
  //     itinerarySlots: {
  //       include: { activityNode: true },
  //       orderBy: [{ dayIndex: "asc" }, { sortOrder: "asc" }],
  //     },
  //   },
  // });

  return {
    id: tripId,
    name: "Tokyo Adventure",
    totalDays: 3,
    slots: [
      {
        id: "slot-1",
        activityNodeId: "an-1",
        name: "Tsukiji Outer Market",
        slotType: "dining" as const,
        lat: 35.6654,
        lng: 139.7707,
        dayIndex: 0,
        timeLabel: "08:00",
        description: "Fresh sushi breakfast at the legendary fish market. Walk the narrow alleys for tamagoyaki and fresh uni.",
        address: "4-16-2 Tsukiji, Chuo City",
      },
      {
        id: "slot-2",
        activityNodeId: "an-2",
        name: "TeamLab Borderless",
        slotType: "culture" as const,
        lat: 35.6267,
        lng: 139.7840,
        dayIndex: 0,
        timeLabel: "11:00",
        description: "Immersive digital art museum. Allow 2-3 hours to fully explore.",
        address: "Azabudai Hills, Minato City",
      },
      {
        id: "slot-3",
        activityNodeId: "an-3",
        name: "Shinjuku Gyoen",
        slotType: "outdoors" as const,
        lat: 35.6852,
        lng: 139.7100,
        dayIndex: 0,
        timeLabel: "15:00",
        description: "Sprawling garden with Japanese, English, and French landscape sections.",
        address: "11 Naitomachi, Shinjuku City",
      },
      {
        id: "slot-4",
        activityNodeId: "an-4",
        name: "Afuri Ramen",
        slotType: "dining" as const,
        lat: 35.6580,
        lng: 139.7030,
        dayIndex: 1,
        timeLabel: "12:00",
        description: "Yuzu shio ramen with a clear, citrus-forward broth.",
        address: "1-1-7 Ebisu, Shibuya City",
      },
      {
        id: "slot-5",
        activityNodeId: "an-5",
        name: "Meiji Jingu",
        slotType: "culture" as const,
        lat: 35.6764,
        lng: 139.6993,
        dayIndex: 1,
        timeLabel: "14:00",
        description: "Serene Shinto shrine surrounded by an ancient forest in the heart of Shibuya.",
        address: "1-1 Yoyogikamizonocho, Shibuya City",
      },
      {
        id: "slot-6",
        activityNodeId: "an-6",
        name: "Yanaka District Walk",
        slotType: "outdoors" as const,
        lat: 35.7260,
        lng: 139.7670,
        dayIndex: 2,
        timeLabel: "10:00",
        description: "Old-town Tokyo. Temple cats, craft shops, and the famous Yanaka Ginza shopping street.",
        address: "Yanaka, Taito City",
      },
    ],
  };
}

export default async function TripMapPage({
  params,
}: {
  params: { id: string };
}) {
  const trip = await getTripData(params.id);

  return (
    <div className="flex flex-col h-screen bg-warm-background">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 bg-warm-surface border-b border-warm">
        <div className="flex items-center gap-3">
          <Link
            href={`/trip/${params.id}`}
            className="flex items-center justify-center w-8 h-8 rounded-lg
                       bg-warm-background border border-warm
                       hover:bg-warm-border transition-colors duration-150"
            aria-label="Back to trip"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M10 12L6 8l4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
          <div>
            <h1 className="font-sora font-semibold text-primary text-base leading-tight">
              {trip.name}
            </h1>
            <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
              Map View
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="hidden sm:flex items-center gap-3">
          {[
            { type: "dining", label: "Dining" },
            { type: "culture", label: "Culture" },
            { type: "outdoors", label: "Outdoors" },
          ].map(({ type, label }) => (
            <div key={type} className="flex items-center gap-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{
                  backgroundColor:
                    type === "dining"
                      ? "#DC2626"
                      : type === "culture"
                      ? "#2563EB"
                      : "#16A34A",
                }}
                aria-hidden="true"
              />
              <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
                {label}
              </span>
            </div>
          ))}
        </div>
      </header>

      {/* Map */}
      <main className="flex-1 min-h-0">
        <MapView
          slots={trip.slots}
          tripId={trip.id}
          totalDays={trip.totalDays}
          initialCenter={[35.6762, 139.6503]}
          initialZoom={13}
        />
      </main>
    </div>
  );
}
