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
  /** Total days in the trip (for move-to-day dropdown) */
  totalDays?: number;
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

// Dot color by slot type (not status) per design spec
function getTimelineDotClass(slotType: SlotData["slotType"]): string {
  switch (slotType) {
    case "anchor":
      return "bg-accent border-accent/30";
    case "flex":
      return "bg-transparent border-ink-500";
    case "meal":
      return "bg-warning border-warning/30";
    case "rest":
      return "bg-success border-success/30";
    case "transit":
      return "bg-ink-500 border-ink-600";
    default:
      return "bg-ink-700 border-ink-800";
  }
}

function EmptyDayState({ dayNumber }: { dayNumber: number }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center mb-4">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.5"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </div>
      <h3 className="font-sora text-base font-medium text-ink-100">
        No plans yet for Day {dayNumber}
      </h3>
      <p className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mt-1">
        Browse and add activities
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
  totalDays,
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
                <span className="font-dm-mono text-xs text-ink-400 mb-2 text-center">
                  {timeMarker}
                </span>
              ) : (
                <span className="font-dm-mono text-xs text-ink-400 mb-2 opacity-40">
                  --:--
                </span>
              )}

              {/* Timeline dot */}
              <div
                className={`
                  w-3 h-3 rounded-full border-2 shrink-0
                  ${getTimelineDotClass(slot.slotType)}
                `}
                aria-hidden="true"
              />

              {/* Connecting line */}
              {!isLast && (
                <div
                  className="w-px flex-1 min-h-[2rem] bg-ink-700"
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
                compact
                showVoting={showVoting}
                showPivot={showPivot}
                showFlag={showFlag}
                totalDays={totalDays}
                currentDay={dayNumber}
                slotIndex={index}
                totalSlotsInDay={sortedSlots.length}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
