"use client";

// DayView — Timeline layout for a single day of the trip.
// Renders SlotCards vertically with time markers and connecting lines.
//
// Usage:
//   <DayView
//     dayNumber={1}
//     slots={slotsForDay}
//     timezone="Asia/Tokyo"
//     onSlotAction={handleBehavioralSignal}
//   />

import { SlotCard, type SlotData } from "@/components/slot/SlotCard";
import { type SlotActionEvent } from "@/components/slot/SlotActions";

interface DayViewProps {
  dayNumber: number;
  slots: SlotData[];
  timezone?: string;
  onSlotAction: (event: SlotActionEvent) => void;
  /** Track 4: enable group voting on all slots */
  showVoting?: boolean;
  /** Track 5: enable pivot controls on all slots */
  showPivot?: boolean;
  /** Track 5: enable flag controls on all slots */
  showFlag?: boolean;
}

function formatTimeMarker(isoString: string, timezone?: string): string {
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

// Status color for the timeline dot
function getTimelineDotClass(status: SlotData["status"]): string {
  switch (status) {
    case "confirmed":
    case "active":
      return "bg-emerald-400 border-emerald-200";
    case "proposed":
    case "voted":
      return "bg-amber-400 border-amber-200";
    case "completed":
    case "skipped":
      return "bg-gray-400 border-gray-200";
    default:
      return "bg-warm-border border-warm-background";
  }
}

function EmptyDayState({ dayNumber }: { dayNumber: number }) {
  return (
    <div
      className="
        flex flex-col items-center justify-center
        py-16 px-6
        rounded-xl border-2 border-dashed border-warm-border
        bg-warm-surface
      "
    >
      <svg
        width="48"
        height="48"
        viewBox="0 0 48 48"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-warm-text-secondary opacity-40 mb-4"
        aria-hidden="true"
      >
        <rect x="8" y="8" width="32" height="32" rx="4" />
        <line x1="8" y1="16" x2="40" y2="16" />
        <line x1="16" y1="8" x2="16" y2="16" />
        <line x1="32" y1="8" x2="32" y2="16" />
        <line x1="20" y1="26" x2="28" y2="26" />
        <line x1="24" y1="22" x2="24" y2="30" />
      </svg>
      <h3 className="font-sora text-base font-semibold text-warm-text-primary mb-1">
        No plans yet for Day {dayNumber}
      </h3>
      <p className="font-dm-mono text-xs text-warm-text-secondary uppercase tracking-wider">
        Activities will appear here once generated
      </p>
    </div>
  );
}

export function DayView({
  dayNumber,
  slots,
  timezone,
  onSlotAction,
  showVoting = false,
  showPivot = false,
  showFlag = false,
}: DayViewProps) {
  // Sort slots by sortOrder (already from DB) or startTime fallback
  const sortedSlots = [...slots].sort((a, b) => {
    if (a.startTime && b.startTime) {
      return new Date(a.startTime).getTime() - new Date(b.startTime).getTime();
    }
    return 0;
  });

  if (sortedSlots.length === 0) {
    return <EmptyDayState dayNumber={dayNumber} />;
  }

  return (
    <div
      className="relative"
      role="list"
      aria-label={`Day ${dayNumber} itinerary`}
    >
      {sortedSlots.map((slot, index) => {
        const timeMarker = slot.startTime
          ? formatTimeMarker(slot.startTime, timezone)
          : null;
        const isLast = index === sortedSlots.length - 1;

        return (
          <div
            key={slot.id}
            role="listitem"
            className="relative flex gap-4"
          >
            {/* Timeline column */}
            <div className="flex flex-col items-center shrink-0 w-16 sm:w-20">
              {/* Time label */}
              {timeMarker ? (
                <span className="font-dm-mono text-xs text-warm-text-secondary mb-2 text-center">
                  {timeMarker}
                </span>
              ) : (
                <span className="font-dm-mono text-xs text-warm-text-secondary mb-2 opacity-40">
                  --:--
                </span>
              )}

              {/* Timeline dot */}
              <div
                className={`
                  w-3 h-3 rounded-full border-2 shrink-0
                  ${getTimelineDotClass(slot.status)}
                `}
                aria-hidden="true"
              />

              {/* Connecting line */}
              {!isLast && (
                <div
                  className="w-px flex-1 min-h-[2rem] bg-warm-border"
                  aria-hidden="true"
                />
              )}
            </div>

            {/* Slot card */}
            <div className="flex-1 pb-6">
              <SlotCard
                slot={slot}
                onAction={onSlotAction}
                timezone={timezone}
                showVoting={showVoting}
                showPivot={showPivot}
                showFlag={showFlag}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
