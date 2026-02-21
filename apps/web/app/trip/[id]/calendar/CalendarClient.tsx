"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ActivityNodeSummary {
  id: string;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
  category: string;
}

interface SlotSummary {
  id: string;
  dayNumber: number;
  sortOrder: number;
  slotType: string;
  status: string;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number | null;
  isLocked: boolean;
  activityNode: ActivityNodeSummary | null;
}

interface TripCalendarData {
  id: string;
  destination: string;
  city: string;
  timezone: string;
  startDate: string;
  endDate: string;
  slots: SlotSummary[];
}

interface CalendarClientProps {
  trip: TripCalendarData;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function endOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function isBetweenInclusive(date: Date, start: Date, end: Date): boolean {
  const d = date.getTime();
  return d >= start.getTime() && d <= end.getTime();
}

function formatMonthYear(date: Date): string {
  return date.toLocaleString("en-US", { month: "long", year: "numeric" });
}

function formatDayNumber(date: Date): number {
  return date.getDate();
}

// Map a calendar date to a trip day number (1-indexed)
function dateToDayNumber(date: Date, tripStart: Date): number {
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.floor((date.getTime() - tripStart.getTime()) / msPerDay) + 1;
}

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

function ChevronLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ChevronRightIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
    <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

function LockIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0110 0v4" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Slot type color mapping
// ---------------------------------------------------------------------------

const SLOT_TYPE_COLORS: Record<string, string> = {
  anchor: "bg-terracotta/80",
  flex: "bg-terracotta/40",
  meal: "bg-amber-400/70",
  break: "bg-warm-border",
  transit: "bg-blue-300/60",
};

// ---------------------------------------------------------------------------
// Day cell
// ---------------------------------------------------------------------------

interface DayCellSlot {
  name: string;
  slotType: string;
  isLocked: boolean;
}

function DayCell({
  date,
  dayNumber,
  isCurrentMonth,
  isTripDay,
  isToday,
  slotCount,
  firstSlot,
  onClick,
}: {
  date: Date;
  dayNumber: number | null;
  isCurrentMonth: boolean;
  isTripDay: boolean;
  isToday: boolean;
  slotCount: number;
  firstSlot: DayCellSlot | null;
  onClick?: () => void;
}) {
  const isClickable = isTripDay && !!onClick;

  return (
    <button
      onClick={onClick}
      disabled={!isClickable}
      className={`
        relative flex min-h-[72px] flex-col rounded-lg border p-1.5 text-left transition-colors
        ${isTripDay
          ? "border-terracotta/30 bg-terracotta/5 hover:bg-terracotta/10 cursor-pointer"
          : "border-warm bg-warm-surface cursor-default"
        }
        ${isToday ? "ring-2 ring-terracotta ring-inset" : ""}
        ${!isCurrentMonth ? "opacity-40" : ""}
      `}
    >
      {/* Day number */}
      <span
        className={`font-dm-mono text-xs font-medium ${
          isToday ? "text-terracotta" : isTripDay ? "text-primary" : "text-secondary"
        }`}
      >
        {date.getDate()}
      </span>

      {/* Trip day indicator */}
      {isTripDay && dayNumber !== null && (
        <span className="mt-0.5 font-dm-mono text-[10px] text-terracotta/70">
          Day {dayNumber}
        </span>
      )}

      {/* First slot preview */}
      {firstSlot && (
        <div className="mt-1 flex items-center gap-0.5">
          <div
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              SLOT_TYPE_COLORS[firstSlot.slotType] ?? "bg-terracotta/40"
            }`}
          />
          {firstSlot.isLocked && (
            <LockIcon className="h-2 w-2 shrink-0 text-secondary" />
          )}
          <span className="truncate font-dm-mono text-[10px] leading-tight text-primary">
            {firstSlot.name}
          </span>
        </div>
      )}

      {/* Slot count badge */}
      {slotCount > 1 && (
        <span className="mt-0.5 font-dm-mono text-[10px] text-secondary">
          +{slotCount - 1} more
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Month grid
// ---------------------------------------------------------------------------

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function MonthGrid({
  month,
  tripStart,
  tripEnd,
  slotsByDay,
  onDayClick,
}: {
  month: Date;
  tripStart: Date;
  tripEnd: Date;
  slotsByDay: Map<number, SlotSummary[]>;
  onDayClick: (dayNumber: number) => void;
}) {
  const today = new Date();
  const monthStart = startOfMonth(month);
  const monthEnd = endOfMonth(month);

  // Build calendar grid starting from Sunday of the week containing monthStart
  const gridStart = new Date(monthStart);
  gridStart.setDate(gridStart.getDate() - gridStart.getDay());

  const cells: Date[] = [];
  const cursor = new Date(gridStart);
  // 6 weeks max
  while (cursor <= monthEnd || cells.length % 7 !== 0) {
    cells.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
    if (cells.length > 42) break;
  }

  return (
    <div>
      {/* Weekday headers */}
      <div className="mb-1 grid grid-cols-7 gap-1">
        {WEEKDAY_LABELS.map((d) => (
          <div key={d} className="py-1 text-center font-dm-mono text-xs text-secondary">
            {d}
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((date, idx) => {
          const isCurrentMonth = date.getMonth() === month.getMonth();
          const isTripDay = isBetweenInclusive(date, tripStart, tripEnd);
          const isToday = isSameDay(date, today);

          let dayNumber: number | null = null;
          let daySlots: SlotSummary[] = [];

          if (isTripDay) {
            dayNumber = dateToDayNumber(date, tripStart);
            daySlots = slotsByDay.get(dayNumber) ?? [];
          }

          const firstSlot = daySlots[0]
            ? {
                name: daySlots[0].activityNode?.name ?? daySlots[0].slotType,
                slotType: daySlots[0].slotType,
                isLocked: daySlots[0].isLocked,
              }
            : null;

          return (
            <DayCell
              key={idx}
              date={date}
              dayNumber={dayNumber}
              isCurrentMonth={isCurrentMonth}
              isTripDay={isTripDay}
              isToday={isToday}
              slotCount={daySlots.length}
              firstSlot={firstSlot}
              onClick={
                isTripDay && dayNumber !== null
                  ? () => onDayClick(dayNumber!)
                  : undefined
              }
            />
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

function SlotLegend() {
  const items = [
    { label: "Anchor", color: "bg-terracotta/80" },
    { label: "Flex", color: "bg-terracotta/40" },
    { label: "Meal", color: "bg-amber-400/70" },
    { label: "Break", color: "bg-warm-border" },
    { label: "Transit", color: "bg-blue-300/60" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5">
          <div className={`h-2.5 w-2.5 rounded-full ${item.color}`} />
          <span className="font-dm-mono text-xs text-secondary">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CalendarClient
// ---------------------------------------------------------------------------

export default function CalendarClient({ trip }: CalendarClientProps) {
  const router = useRouter();

  const tripStart = useMemo(() => new Date(trip.startDate), [trip.startDate]);
  const tripEnd = useMemo(() => new Date(trip.endDate), [trip.endDate]);

  // Month state — default to the month containing trip start
  const [currentMonth, setCurrentMonth] = useState<Date>(
    () => new Date(tripStart.getFullYear(), tripStart.getMonth(), 1)
  );

  // Index slots by dayNumber
  const slotsByDay = useMemo(() => {
    const map = new Map<number, SlotSummary[]>();
    for (const slot of trip.slots) {
      const arr = map.get(slot.dayNumber) ?? [];
      arr.push(slot);
      map.set(slot.dayNumber, arr);
    }
    return map;
  }, [trip.slots]);

  const totalDays = useMemo(() => {
    const msPerDay = 24 * 60 * 60 * 1000;
    return Math.round((tripEnd.getTime() - tripStart.getTime()) / msPerDay) + 1;
  }, [tripStart, tripEnd]);

  const totalSlots = trip.slots.filter(
    (s) => s.slotType !== "rest" && s.slotType !== "transit"
  ).length;

  function prevMonth() {
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1));
  }

  function nextMonth() {
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1));
  }

  function handleDayClick(dayNumber: number) {
    router.push(`/trip/${trip.id}?day=${dayNumber}`);
  }

  async function handleDownloadIcs() {
    const link = document.createElement("a");
    link.href = `${process.env.NEXT_PUBLIC_API_URL ?? ""}/trips/${trip.id}/calendar.ics`;
    link.download = `${trip.city.toLowerCase().replace(/\s+/g, "-")}-itinerary.ics`;
    link.click();
  }

  return (
    <div className="min-h-screen bg-app">
      {/* Top bar */}
      <div className="sticky top-0 z-10 border-b border-warm bg-app/90 backdrop-blur-sm">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push(`/trip/${trip.id}`)}
              className="flex h-8 w-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-warm-surface hover:text-primary"
              aria-label="Back to trip"
            >
              <ArrowLeftIcon className="h-4 w-4" />
            </button>
            <div className="flex-1">
              <h1 className="font-sora text-base font-semibold text-primary">
                {trip.destination}
              </h1>
              <p className="label-mono">
                {totalDays} days &middot; {totalSlots} activities
              </p>
            </div>

            <button
              onClick={handleDownloadIcs}
              className="flex items-center gap-1.5 rounded-lg border border-warm bg-warm-surface px-3 py-1.5 font-dm-mono text-xs text-secondary transition-colors hover:border-terracotta/40 hover:text-primary"
              title="Download .ics calendar file"
            >
              <DownloadIcon className="h-3.5 w-3.5" />
              <span>.ics</span>
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-4 py-5 space-y-5">
        {/* Month navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={prevMonth}
            className="flex h-8 w-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-warm-surface hover:text-primary"
            aria-label="Previous month"
          >
            <ChevronLeftIcon className="h-4 w-4" />
          </button>

          <h2 className="font-sora text-base font-semibold text-primary">
            {formatMonthYear(currentMonth)}
          </h2>

          <button
            onClick={nextMonth}
            className="flex h-8 w-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-warm-surface hover:text-primary"
            aria-label="Next month"
          >
            <ChevronRightIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Calendar grid */}
        <MonthGrid
          month={currentMonth}
          tripStart={tripStart}
          tripEnd={tripEnd}
          slotsByDay={slotsByDay}
          onDayClick={handleDayClick}
        />

        {/* Legend */}
        <div className="rounded-xl border border-warm bg-warm-surface p-3">
          <SlotLegend />
        </div>

        {/* Trip overview strip */}
        <div>
          <h3 className="mb-3 font-sora text-sm font-semibold text-primary">
            Trip at a glance
          </h3>
          <div className="space-y-1">
            {Array.from({ length: totalDays }, (_, i) => i + 1).map((day) => {
              const daySlots = slotsByDay.get(day) ?? [];
              const date = addDays(tripStart, day - 1);
              const dateLabel = date.toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
              });

              return (
                <button
                  key={day}
                  onClick={() => handleDayClick(day)}
                  className="group flex w-full items-start gap-3 rounded-lg border border-warm bg-warm-surface px-3 py-2.5 text-left transition-colors hover:border-terracotta/30 hover:bg-terracotta/5"
                >
                  {/* Day label */}
                  <div className="w-20 shrink-0">
                    <div className="font-dm-mono text-xs font-medium text-terracotta">
                      Day {day}
                    </div>
                    <div className="font-dm-mono text-xs text-secondary">{dateLabel}</div>
                  </div>

                  {/* Slot summary */}
                  <div className="min-w-0 flex-1">
                    {daySlots.length === 0 ? (
                      <p className="font-dm-mono text-xs text-secondary">No activities yet</p>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {daySlots.slice(0, 4).map((slot) => (
                          <div key={slot.id} className="flex items-center gap-1">
                            <div
                              className={`h-1.5 w-1.5 rounded-full ${
                                SLOT_TYPE_COLORS[slot.slotType] ?? "bg-terracotta/40"
                              }`}
                            />
                            <span className="font-dm-mono text-xs text-primary line-clamp-1 max-w-[120px]">
                              {slot.activityNode?.name ?? slot.slotType}
                            </span>
                          </div>
                        ))}
                        {daySlots.length > 4 && (
                          <span className="font-dm-mono text-xs text-secondary">
                            +{daySlots.length - 4} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Slot count */}
                  <div className="shrink-0">
                    <span className="rounded-full bg-terracotta/10 px-2 py-0.5 font-dm-mono text-xs text-terracotta">
                      {daySlots.length}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
