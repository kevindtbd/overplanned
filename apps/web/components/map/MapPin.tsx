"use client";

/**
 * MapPin — Custom SVG map marker colored by slot type.
 *
 * Slot type color mapping:
 *   dining   -> #DC2626 (red)
 *   culture  -> #2563EB (blue)
 *   outdoors -> #16A34A (green)
 *   default  -> #C4694F (terracotta)
 *
 * Usage:
 *   <MapPin slotType="dining" label="Ramen Nagi" isActive={false} />
 */

import L from "leaflet";

export type SlotType = "dining" | "culture" | "outdoors" | "nightlife" | "shopping" | "transit";

const SLOT_COLORS: Record<string, string> = {
  dining: "#DC2626",
  culture: "#2563EB",
  outdoors: "#16A34A",
  nightlife: "#7C3AED",
  shopping: "#D97706",
  transit: "#6B7280",
};

const DEFAULT_COLOR = "#C4694F";

function getSlotColor(slotType: string): string {
  return SLOT_COLORS[slotType] ?? DEFAULT_COLOR;
}

/**
 * Generate an SVG pin icon as a data URI for Leaflet markers.
 * The pin is a teardrop shape with an inner circle.
 */
export function createPinIcon(
  slotType: string,
  isActive = false
): L.DivIcon {
  const color = getSlotColor(slotType);
  const size = isActive ? 40 : 30;
  const anchorY = isActive ? 40 : 30;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 32" fill="none">
      <path d="M12 0C5.373 0 0 5.373 0 12c0 9 12 20 12 20s12-11 12-20C24 5.373 18.627 0 12 0z"
            fill="${color}"
            stroke="${isActive ? "#FFFFFF" : "none"}"
            stroke-width="${isActive ? 2 : 0}"
            opacity="${isActive ? 1 : 0.85}" />
      <circle cx="12" cy="11" r="4.5" fill="white" opacity="0.9" />
    </svg>
  `.trim();

  return L.divIcon({
    html: svg,
    className: "overplanned-map-pin",
    iconSize: [size, size],
    iconAnchor: [size / 2, anchorY],
    popupAnchor: [0, -anchorY + 4],
  });
}

/** SVG pin for use in React (sidebar list items, legends). */
export function PinIcon({
  slotType,
  size = 16,
  className = "",
}: {
  slotType: string;
  size?: number;
  className?: string;
}) {
  const color = getSlotColor(slotType);

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 32"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M12 0C5.373 0 0 5.373 0 12c0 9 12 20 12 20s12-11 12-20C24 5.373 18.627 0 12 0z"
        fill={color}
      />
      <circle cx="12" cy="11" r="4.5" fill="white" opacity="0.9" />
    </svg>
  );
}
