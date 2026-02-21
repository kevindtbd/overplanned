"use client";

// VisitedMap — Read-only map of completed itinerary slots.
// Shows pins for all visited locations with a connecting path line.
// No interaction beyond pan/zoom — purely for reflection.

import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import type { LatLngTuple } from "leaflet";
import "leaflet/dist/leaflet.css";

import { createPinIcon, PinIcon, type SlotType } from "@/components/map/MapPin";

// ---------- Types ----------

export interface VisitedSlot {
  id: string;
  activityName: string;
  slotType: SlotType | string;
  lat: number;
  lng: number;
  dayIndex: number;
  timeLabel?: string;
  status: "completed" | "skipped";
}

interface VisitedMapProps {
  slots: VisitedSlot[];
  className?: string;
}

// ---------- Bounds helper ----------

function BoundsUpdater({ positions }: { positions: LatLngTuple[] }) {
  const map = useMap();

  useMemo(() => {
    if (positions.length === 0) return;
    map.fitBounds(positions, { padding: [30, 30], maxZoom: 14 });
  }, [positions, map]);

  return null;
}

// ---------- Constants ----------

const DAY_COLORS = [
  "#C4694F", // terracotta
  "#3B82F6", // blue
  "#10B981", // emerald
  "#F59E0B", // amber
  "#8B5CF6", // violet
  "#EC4899", // pink
  "#06B6D4", // cyan
];

// ---------- Component ----------

export function VisitedMap({ slots, className }: VisitedMapProps) {
  // Split by day for polyline coloring
  const dayGroups = useMemo(() => {
    const groups: Record<number, VisitedSlot[]> = {};
    for (const slot of slots) {
      if (!groups[slot.dayIndex]) groups[slot.dayIndex] = [];
      groups[slot.dayIndex].push(slot);
    }
    return groups;
  }, [slots]);

  const allPositions: LatLngTuple[] = useMemo(
    () => slots.map((s) => [s.lat, s.lng] as LatLngTuple),
    [slots]
  );

  // Default center (Tokyo) if no slots
  const center: LatLngTuple = useMemo(() => {
    if (allPositions.length === 0) return [35.6762, 139.6503];
    const avgLat = allPositions.reduce((a, p) => a + p[0], 0) / allPositions.length;
    const avgLng = allPositions.reduce((a, p) => a + p[1], 0) / allPositions.length;
    return [avgLat, avgLng];
  }, [allPositions]);

  if (slots.length === 0) {
    return (
      <div className={`flex items-center justify-center bg-base rounded-xl ${className ?? ""}`}>
        <p className="font-dm-mono text-xs text-ink-400">No visited locations</p>
      </div>
    );
  }

  return (
    <section
      className={`rounded-xl overflow-hidden border border-ink-700 ${className ?? ""}`}
      aria-label="Map of visited locations"
    >
      <MapContainer
        center={center}
        zoom={12}
        className="h-full w-full z-0"
        zoomControl={false}
        scrollWheelZoom={true}
        dragging={true}
        attributionControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <BoundsUpdater positions={allPositions} />

        {/* Day path lines */}
        {Object.entries(dayGroups).map(([dayIdx, daySlots]) => {
          const positions = daySlots.map(
            (s) => [s.lat, s.lng] as LatLngTuple
          );
          const color = DAY_COLORS[Number(dayIdx) % DAY_COLORS.length];
          return (
            <Polyline
              key={`path-${dayIdx}`}
              positions={positions}
              pathOptions={{
                color,
                weight: 2,
                opacity: 0.6,
                dashArray: "6 4",
              }}
            />
          );
        })}

        {/* Slot pins */}
        {slots.map((slot) => (
          <Marker
            key={slot.id}
            position={[slot.lat, slot.lng]}
            icon={createPinIcon(slot.slotType, false)}
          >
            <Popup className="overplanned-popup">
              <div className="p-1">
                <div className="flex items-center gap-2 mb-1">
                  <PinIcon slotType={slot.slotType} size={14} />
                  <span className="font-sora font-semibold text-sm">
                    {slot.activityName}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
                    Day {slot.dayIndex + 1}
                  </span>
                  {slot.timeLabel && (
                    <>
                      <span className="text-ink-700" aria-hidden="true">/</span>
                      <span className="font-dm-mono text-xs text-secondary">
                        {slot.timeLabel}
                      </span>
                    </>
                  )}
                </div>
                <span
                  className={`
                    inline-block mt-1 font-dm-mono text-[10px] uppercase tracking-wider
                    px-1.5 py-0.5 rounded
                    ${
                      slot.status === "completed"
                        ? "bg-success-bg text-success"
                        : "bg-ink-800 text-ink-500"
                    }
                  `}
                >
                  {slot.status}
                </span>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </section>
  );
}
