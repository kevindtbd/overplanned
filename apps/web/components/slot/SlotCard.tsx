"use client";

// SlotCard — Shared, reusable itinerary slot card.
// Used by Solo (Track 3), Group (Track 4), Mid-Trip (Track 5).
//
// Usage:
//   <SlotCard
//     slot={slotData}
//     onAction={handleBehavioralSignal}
//     showVoting={false}   // Track 4: group voting UI
//     showPivot={false}    // Track 5: pivot swap UI
//     showFlag={false}     // Track 5: flag for review
//   />

import Image from "next/image";
import { useCallback } from "react";
import { VibeChips, type VibeTagDisplay } from "./VibeChips";
import { SlotActions, type SlotActionEvent } from "./SlotActions";

// ---------- Types ----------

export type SlotStatusType =
  | "proposed"
  | "voted"
  | "confirmed"
  | "active"
  | "completed"
  | "skipped";

export type SlotTypeLabel =
  | "anchor"
  | "flex"
  | "meal"
  | "rest"
  | "transit";

export interface SlotData {
  id: string;
  activityName: string;
  /** Unsplash URL for the activity photo */
  imageUrl?: string;
  /** IANA timezone-aware ISO string */
  startTime?: string;
  endTime?: string;
  durationMinutes?: number;
  slotType: SlotTypeLabel;
  status: SlotStatusType;
  isLocked: boolean;
  vibeTags: VibeTagDisplay[];
  /** Slug of the primary vibe tag */
  primaryVibeSlug?: string;
  /** For booking badge display (future) */
  bookingStatus?: "none" | "pending" | "confirmed";
  /** Activity node ID for behavioral signal logging */
  activityNodeId?: string;
}

export interface SlotCardProps {
  slot: SlotData;
  /** Fires a BehavioralSignal-shaped event on confirm/skip/lock */
  onAction: (event: SlotActionEvent) => void;
  /** Trip timezone (IANA) for time display */
  timezone?: string;
  /** Track 4: show group voting controls */
  showVoting?: boolean;
  /** Track 5: show pivot/swap controls */
  showPivot?: boolean;
  /** Track 5: show flag-for-review button */
  showFlag?: boolean;
}

// ---------- Helpers ----------

const STATUS_CONFIG: Record<
  SlotStatusType,
  { label: string; dotClass: string; bgClass: string }
> = {
  proposed: {
    label: "Proposed",
    dotClass: "bg-amber-400",
    bgClass: "bg-amber-50 text-amber-700",
  },
  voted: {
    label: "Voted",
    dotClass: "bg-amber-400",
    bgClass: "bg-amber-50 text-amber-700",
  },
  confirmed: {
    label: "Confirmed",
    dotClass: "bg-emerald-400",
    bgClass: "bg-emerald-50 text-emerald-700",
  },
  active: {
    label: "Active",
    dotClass: "bg-emerald-400",
    bgClass: "bg-emerald-50 text-emerald-700",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-gray-400",
    bgClass: "bg-gray-100 text-gray-500",
  },
  skipped: {
    label: "Skipped",
    dotClass: "bg-gray-400",
    bgClass: "bg-gray-100 text-gray-500",
  },
};

function formatTime(isoString: string, timezone?: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: timezone || undefined,
    });
  } catch {
    return "";
  }
}

function formatDuration(minutes?: number): string {
  if (!minutes) return "";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

// ---------- Component ----------

export function SlotCard({
  slot,
  onAction,
  timezone,
  showVoting = false,
  showPivot = false,
  showFlag = false,
}: SlotCardProps) {
  const statusConfig = STATUS_CONFIG[slot.status];

  const handleAction = useCallback(
    (event: SlotActionEvent) => {
      onAction(event);
    },
    [onAction]
  );

  const timeDisplay = slot.startTime ? formatTime(slot.startTime, timezone) : null;
  const endTimeDisplay = slot.endTime ? formatTime(slot.endTime, timezone) : null;
  const durationDisplay = formatDuration(slot.durationMinutes);

  return (
    <article
      className={`
        group relative rounded-xl border border-warm-border
        bg-warm-surface overflow-hidden
        transition-shadow duration-200
        hover:shadow-md
        ${slot.status === "completed" || slot.status === "skipped" ? "opacity-60" : ""}
      `}
      aria-label={`${slot.activityName} - ${statusConfig.label}`}
    >
      {/* Photo + Status overlay */}
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-warm-background">
        {slot.imageUrl ? (
          <Image
            src={slot.imageUrl}
            alt={slot.activityName}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            loading="lazy"
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <svg
              width="48"
              height="48"
              viewBox="0 0 48 48"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-warm-text-secondary opacity-30"
              aria-hidden="true"
            >
              <rect x="6" y="10" width="36" height="28" rx="3" />
              <circle cx="18" cy="22" r="4" />
              <path d="M6 34l10-8 6 4 10-10 10 8" />
            </svg>
          </div>
        )}

        {/* Status badge — top right */}
        <div className="absolute top-3 right-3">
          <span
            className={`
              inline-flex items-center gap-1.5 px-2 py-1 rounded-full
              font-dm-mono text-[10px] uppercase tracking-wider
              backdrop-blur-sm
              ${statusConfig.bgClass}
            `}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${statusConfig.dotClass}`}
              aria-hidden="true"
            />
            {statusConfig.label}
          </span>
        </div>

        {/* Locked indicator */}
        {slot.isLocked && (
          <div className="absolute top-3 left-3">
            <span
              className="
                inline-flex items-center gap-1 px-2 py-1 rounded-full
                bg-amber-50 text-amber-700
                font-dm-mono text-[10px] uppercase tracking-wider
                backdrop-blur-sm
              "
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="3.5" y="7" width="9" height="7" rx="1" />
                <path d="M5.5 7V5a2.5 2.5 0 015 0v2" />
              </svg>
              Locked
            </span>
          </div>
        )}

        {/* Booking badge placeholder */}
        {slot.bookingStatus && slot.bookingStatus !== "none" && (
          <div className="absolute bottom-3 right-3">
            <span
              className={`
                inline-flex items-center gap-1 px-2 py-1 rounded-full
                font-dm-mono text-[10px] uppercase tracking-wider
                backdrop-blur-sm
                ${
                  slot.bookingStatus === "confirmed"
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-amber-50 text-amber-700"
                }
              `}
            >
              {slot.bookingStatus === "confirmed" ? "Booked" : "Booking Pending"}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Activity name + slot type */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-sora font-semibold text-warm-text-primary text-base leading-tight">
            {slot.activityName}
          </h3>
          <span
            className="
              shrink-0 font-dm-mono text-[10px] uppercase tracking-wider
              text-warm-text-secondary bg-warm-background
              px-1.5 py-0.5 rounded
            "
          >
            {slot.slotType}
          </span>
        </div>

        {/* Time + Duration */}
        {(timeDisplay || durationDisplay) && (
          <div className="flex items-center gap-2 font-dm-mono text-xs text-warm-text-secondary">
            {timeDisplay && (
              <span className="flex items-center gap-1">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="8" cy="8" r="6.5" />
                  <polyline points="8 4.5 8 8 10.5 9.5" />
                </svg>
                <time>{timeDisplay}</time>
                {endTimeDisplay && (
                  <>
                    <span aria-hidden="true">-</span>
                    <time>{endTimeDisplay}</time>
                  </>
                )}
              </span>
            )}
            {timeDisplay && durationDisplay && (
              <span aria-hidden="true" className="text-warm-border">|</span>
            )}
            {durationDisplay && <span>{durationDisplay}</span>}
          </div>
        )}

        {/* Vibe tags */}
        <VibeChips
          tags={slot.vibeTags}
          primarySlug={slot.primaryVibeSlug}
        />

        {/* Actions */}
        <SlotActions
          slotId={slot.id}
          status={slot.status}
          isLocked={slot.isLocked}
          onAction={handleAction}
        />

        {/* Track 4: Group voting placeholder */}
        {showVoting && (
          <div
            className="
              mt-2 p-3 rounded-lg border border-dashed border-warm-border
              font-dm-mono text-[11px] text-warm-text-secondary uppercase tracking-wider
              text-center
            "
            aria-label="Group voting controls (coming soon)"
          >
            Group voting -- Track 4
          </div>
        )}

        {/* Track 5: Pivot / Flag placeholders */}
        {(showPivot || showFlag) && (
          <div className="flex gap-2 mt-2">
            {showPivot && (
              <div
                className="
                  flex-1 p-2 rounded-lg border border-dashed border-warm-border
                  font-dm-mono text-[11px] text-warm-text-secondary uppercase tracking-wider
                  text-center
                "
                aria-label="Pivot swap controls (coming soon)"
              >
                Pivot -- Track 5
              </div>
            )}
            {showFlag && (
              <div
                className="
                  flex-1 p-2 rounded-lg border border-dashed border-warm-border
                  font-dm-mono text-[11px] text-warm-text-secondary uppercase tracking-wider
                  text-center
                "
                aria-label="Flag for review (coming soon)"
              >
                Flag -- Track 5
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
