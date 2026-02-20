"use client";

/**
 * MapView — Primary map visualization component.
 *
 * Desktop: sidebar list (left) + Leaflet map canvas (right)
 * Mobile: full-screen map with bottom sheet on pin tap
 *
 * Pins are colored by slotType via MapPin.
 * Day filter controls which slots are visible.
 *
 * Usage:
 *   <MapView
 *     slots={itinerarySlots}
 *     tripId="trip-123"
 *     totalDays={5}
 *   />
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import type { Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";

import { createPinIcon, PinIcon, type SlotType } from "./MapPin";
import SlotBottomSheet from "./SlotBottomSheet";
import { eventEmitter } from "@/lib/events";

/** Shape of a slot rendered on the map. */
export interface MapSlot {
  id: string;
  activityNodeId: string;
  name: string;
  slotType: SlotType | string;
  lat: number;
  lng: number;
  dayIndex: number;
  timeLabel?: string;
  description?: string;
  address?: string;
  imageUrl?: string;
}

interface MapViewProps {
  slots: MapSlot[];
  tripId: string;
  totalDays: number;
  initialCenter?: [number, number];
  initialZoom?: number;
  onSlotConfirm?: (slotId: string) => void;
  onSlotSkip?: (slotId: string) => void;
}

/** Helper to recenter the map when filtered slots change. */
function MapBoundsUpdater({ slots }: { slots: MapSlot[] }) {
  const map = useMap();

  useEffect(() => {
    if (slots.length === 0) return;

    const bounds = slots.map((s) => [s.lat, s.lng] as [number, number]);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }, [slots, map]);

  return null;
}

export default function MapView({
  slots,
  tripId,
  totalDays,
  initialCenter = [35.6762, 139.6503], // Tokyo default
  initialZoom = 13,
  onSlotConfirm,
  onSlotSkip,
}: MapViewProps) {
  const [activeDay, setActiveDay] = useState(0);
  const [selectedSlot, setSelectedSlot] = useState<MapSlot | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  // Filter slots by selected day
  const visibleSlots = useMemo(
    () => slots.filter((s) => s.dayIndex === activeDay),
    [slots, activeDay]
  );

  // Day labels for the filter
  const dayLabels = useMemo(
    () => Array.from({ length: totalDays }, (_, i) => `Day ${i + 1}`),
    [totalDays]
  );

  const handlePinClick = useCallback(
    (slot: MapSlot) => {
      setSelectedSlot(slot);

      eventEmitter.emit({
        eventType: "card_tap",
        intentClass: "explicit",
        tripId,
        slotId: slot.id,
        activityNodeId: slot.activityNodeId,
        payload: {
          activityNodeId: slot.activityNodeId,
          position: visibleSlots.indexOf(slot),
          source: "map",
        },
      });
    },
    [tripId, visibleSlots]
  );

  const handleSidebarClick = useCallback(
    (slot: MapSlot) => {
      setSelectedSlot(slot);

      // Pan map to the slot
      if (mapRef.current) {
        mapRef.current.setView([slot.lat, slot.lng], 15, { animate: true });
      }

      eventEmitter.emit({
        eventType: "card_tap",
        intentClass: "explicit",
        tripId,
        slotId: slot.id,
        activityNodeId: slot.activityNodeId,
        payload: {
          activityNodeId: slot.activityNodeId,
          position: visibleSlots.indexOf(slot),
          source: "feed",
        },
      });
    },
    [tripId, visibleSlots]
  );

  const handleDayChange = useCallback(
    (dayIndex: number) => {
      setActiveDay(dayIndex);
      setSelectedSlot(null);

      eventEmitter.emit({
        eventType: "tab_switch",
        intentClass: "explicit",
        tripId,
        payload: {
          fromTab: `day-${activeDay}`,
          toTab: `day-${dayIndex}`,
        },
      });
    },
    [tripId, activeDay]
  );

  // Emit screen_view on mount
  useEffect(() => {
    eventEmitter.emit({
      eventType: "screen_view",
      intentClass: "implicit",
      tripId,
      payload: {
        screenName: "map_view",
      },
    });
  }, [tripId]);

  return (
    <div className="flex flex-col h-full w-full">
      {/* Day filter bar */}
      <nav
        className="flex items-center gap-2 px-4 py-3 bg-warm-surface border-b border-warm
                   overflow-x-auto scrollbar-none"
        role="tablist"
        aria-label="Day filter"
      >
        {dayLabels.map((label, i) => (
          <button
            key={i}
            role="tab"
            aria-selected={activeDay === i}
            aria-controls="map-panel"
            onClick={() => handleDayChange(i)}
            className={`
              shrink-0 px-4 py-1.5 rounded-full text-sm font-medium
              transition-colors duration-150
              ${
                activeDay === i
                  ? "bg-terracotta text-white"
                  : "bg-warm-background text-secondary hover:text-primary hover:bg-warm-border"
              }
            `}
          >
            <span className="font-dm-mono text-xs uppercase tracking-wider">
              {label}
            </span>
          </button>
        ))}
      </nav>

      {/* Main content: sidebar + map */}
      <div id="map-panel" role="tabpanel" className="flex flex-1 min-h-0">
        {/* Sidebar — desktop only */}
        <aside
          className="hidden lg:flex flex-col w-80 border-r border-warm bg-warm-surface
                     overflow-y-auto"
          aria-label="Itinerary slots"
        >
          {visibleSlots.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-secondary text-sm">No slots for this day</p>
            </div>
          ) : (
            <ul className="p-3 space-y-2">
              {visibleSlots.map((slot, idx) => (
                <li key={slot.id}>
                  <button
                    onClick={() => handleSidebarClick(slot)}
                    className={`
                      w-full text-left p-3 rounded-xl transition-colors duration-150
                      border
                      ${
                        selectedSlot?.id === slot.id
                          ? "bg-terracotta-50 border-terracotta-200"
                          : "bg-warm-background border-warm hover:bg-warm-border"
                      }
                    `}
                    aria-label={`View ${slot.name} on map`}
                    aria-pressed={selectedSlot?.id === slot.id}
                  >
                    <div className="flex items-start gap-3">
                      {/* Index badge */}
                      <span
                        className="shrink-0 flex items-center justify-center w-6 h-6
                                   rounded-full bg-warm-border font-dm-mono text-xs text-secondary"
                      >
                        {idx + 1}
                      </span>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <PinIcon slotType={slot.slotType} size={14} />
                          <h4 className="font-sora font-medium text-sm text-primary truncate">
                            {slot.name}
                          </h4>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
                            {slot.slotType}
                          </span>
                          {slot.timeLabel && (
                            <>
                              <span className="text-warm-border" aria-hidden="true">
                                /
                              </span>
                              <span className="font-dm-mono text-xs text-secondary">
                                {slot.timeLabel}
                              </span>
                            </>
                          )}
                        </div>
                        {slot.address && (
                          <p className="text-xs text-secondary mt-1 truncate">
                            {slot.address}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Map canvas */}
        <div className="flex-1 relative">
          <MapContainer
            center={initialCenter}
            zoom={initialZoom}
            className="h-full w-full z-0"
            ref={mapRef}
            zoomControl={false}
            attributionControl={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <MapBoundsUpdater slots={visibleSlots} />

            {visibleSlots.map((slot) => (
              <Marker
                key={slot.id}
                position={[slot.lat, slot.lng]}
                icon={createPinIcon(slot.slotType, selectedSlot?.id === slot.id)}
                eventHandlers={{
                  click: () => handlePinClick(slot),
                }}
              >
                {/* Desktop popup */}
                <Popup className="overplanned-popup">
                  <div className="p-1">
                    <div className="flex items-center gap-2 mb-1">
                      <PinIcon slotType={slot.slotType} size={14} />
                      <span className="font-sora font-semibold text-sm">
                        {slot.name}
                      </span>
                    </div>
                    <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
                      {slot.slotType}
                      {slot.timeLabel ? ` / ${slot.timeLabel}` : ""}
                    </span>
                    {slot.description && (
                      <p className="text-xs text-secondary mt-1 line-clamp-2">
                        {slot.description}
                      </p>
                    )}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>

          {/* Slot count badge — mobile */}
          <div
            className="absolute top-3 right-3 z-10 lg:hidden
                       px-3 py-1.5 rounded-full bg-warm-surface border border-warm
                       shadow-sm"
            aria-live="polite"
          >
            <span className="font-dm-mono text-xs text-secondary">
              {visibleSlots.length} slot{visibleSlots.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      </div>

      {/* Mobile bottom sheet */}
      <SlotBottomSheet
        slot={selectedSlot}
        onClose={() => setSelectedSlot(null)}
        onConfirm={onSlotConfirm}
        onSkip={onSlotSkip}
      />
    </div>
  );
}
