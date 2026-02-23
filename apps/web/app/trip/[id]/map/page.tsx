/**
 * /trip/[id]/map — Map view page for a trip's itinerary.
 *
 * Loads itinerary slots for the trip and renders them on an interactive
 * Leaflet map with day filtering and slot detail interactions.
 *
 * Server component that fetches trip data via Prisma (auth-gated, IDOR-checked),
 * then delegates to the client-side MapView for interactivity.
 */

import type { Metadata } from "next";
import dynamic from "next/dynamic";
import Link from "next/link";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { redirect } from "next/navigation";

// Dynamic import for MapView since Leaflet requires window/document
const MapView = dynamic(
  () => import("@/components/map/MapView"),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full bg-base">
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
              fill="var(--accent)"
              opacity="0.3"
            />
            <circle cx="16" cy="13" r="4" fill="var(--accent)" opacity="0.5" />
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

async function getTripData(tripId: string) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    redirect("/auth/signin");
  }

  const userId = (session.user as { id: string }).id;

  // IDOR check — caller must be a joined member of this trip
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { status: true },
  });

  if (!membership || membership.status !== "joined") {
    redirect("/dashboard");
  }

  const trip = await prisma.trip.findUnique({
    where: { id: tripId },
    select: {
      id: true,
      name: true,
      startDate: true,
      endDate: true,
      legs: {
        select: { destination: true, city: true },
        orderBy: { position: "asc" },
        take: 1,
      },
      slots: {
        orderBy: [{ dayNumber: "asc" }, { sortOrder: "asc" }],
        select: {
          id: true,
          dayNumber: true,
          sortOrder: true,
          slotType: true,
          startTime: true,
          activityNode: {
            select: {
              id: true,
              name: true,
              category: true,
              latitude: true,
              longitude: true,
              address: true,
              descriptionShort: true,
            },
          },
        },
      },
    },
  });

  if (!trip) {
    redirect("/dashboard");
  }

  const totalDays = Math.max(
    Math.ceil(
      (new Date(trip.endDate).getTime() - new Date(trip.startDate).getTime()) /
        (1000 * 60 * 60 * 24)
    ),
    1
  );

  // Compute map center from the average of all geocoded slot coordinates
  const slotsWithCoords = trip.slots.filter(
    (s) => s.activityNode?.latitude && s.activityNode?.longitude
  );
  const center: [number, number] =
    slotsWithCoords.length > 0
      ? [
          slotsWithCoords.reduce(
            (sum, s) => sum + s.activityNode!.latitude,
            0
          ) / slotsWithCoords.length,
          slotsWithCoords.reduce(
            (sum, s) => sum + s.activityNode!.longitude,
            0
          ) / slotsWithCoords.length,
        ]
      : [0, 0];

  return {
    id: trip.id,
    name: trip.name || (trip.legs[0]?.destination ?? trip.legs[0]?.city ?? ""),
    totalDays,
    center,
    slots: trip.slots
      .filter((s) => s.activityNode)
      .map((s) => ({
        id: s.id,
        activityNodeId: s.activityNode!.id,
        name: s.activityNode!.name,
        slotType: s.slotType.toLowerCase() as "dining" | "culture" | "outdoors",
        lat: s.activityNode!.latitude,
        lng: s.activityNode!.longitude,
        dayIndex: s.dayNumber - 1, // MapView uses 0-indexed days
        timeLabel: s.startTime
          ? new Date(s.startTime).toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })
          : undefined,
        description: s.activityNode!.descriptionShort ?? undefined,
        address: s.activityNode!.address ?? undefined,
      })),
  };
}

export default async function TripMapPage({
  params,
}: {
  params: { id: string };
}) {
  const trip = await getTripData(params.id);

  return (
    <div className="flex flex-col h-screen bg-base">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 bg-surface border-b border-ink-700">
        <div className="flex items-center gap-3">
          <Link
            href={`/trip/${params.id}`}
            className="flex items-center justify-center w-8 h-8 rounded-lg
                       bg-base border border-ink-700
                       hover:bg-ink-700 transition-colors duration-150"
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
          initialCenter={trip.center}
          initialZoom={13}
        />
      </main>
    </div>
  );
}
