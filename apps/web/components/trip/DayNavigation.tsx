"use client";

// DayNavigation — Swipeable (mobile) or tabbed (desktop) day selector.
// Supports optional multi-city leg grouping.
// Usage:
//   <DayNavigation
//     totalDays={5}
//     currentDay={1}
//     onDayChange={setCurrentDay}
//     startDate="2026-03-15"
//     timezone="Asia/Tokyo"
//     legs={[
//       { id: "leg-1", city: "Tokyo", dayCount: 3 },
//       { id: "leg-2", city: "Kyoto", dayCount: 2 },
//     ]}
//   />

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface LegInfo {
  id: string;
  city: string;
  dayCount: number;
}

interface DayNavigationProps {
  totalDays: number;
  currentDay: number;
  onDayChange: (day: number) => void;
  /** Trip start date ISO string — used to show actual dates on tabs */
  startDate: string;
  timezone?: string;
  /** Optional leg info for multi-city trips — groups day pills by leg */
  legs?: LegInfo[];
}

function formatDayLabel(startDate: string, dayNumber: number, timezone?: string): string {
  try {
    const date = new Date(startDate);
    date.setDate(date.getDate() + (dayNumber - 1));
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      timeZone: timezone || undefined,
    });
  } catch {
    return `Day ${dayNumber}`;
  }
}

/** Build leg groups with absolute day numbers from leg info */
function buildLegGroups(legs: LegInfo[]): { leg: LegInfo; startDay: number; days: number[] }[] {
  const groups: { leg: LegInfo; startDay: number; days: number[] }[] = [];
  let dayOffset = 0;
  for (const leg of legs) {
    const days = Array.from({ length: leg.dayCount }, (_, i) => dayOffset + i + 1);
    groups.push({ leg, startDay: dayOffset + 1, days });
    dayOffset += leg.dayCount;
  }
  return groups;
}

export function DayNavigation({
  totalDays,
  currentDay,
  onDayChange,
  startDate,
  timezone,
  legs,
}: DayNavigationProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef<number>(0);
  const [swiping, setSwiping] = useState(false);

  const days = Array.from({ length: totalDays }, (_, i) => i + 1);
  const tabRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  const legGroups = useMemo(() => (legs ? buildLegGroups(legs) : null), [legs]);

  const handlePrev = useCallback(() => {
    if (currentDay > 1) onDayChange(currentDay - 1);
  }, [currentDay, onDayChange]);

  const handleNext = useCallback(() => {
    if (currentDay < totalDays) onDayChange(currentDay + 1);
  }, [currentDay, totalDays, onDayChange]);

  // Touch swipe handling for mobile
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    setSwiping(true);
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!swiping) return;
      const deltaX = e.changedTouches[0].clientX - touchStartX.current;
      const threshold = 50;

      if (deltaX < -threshold && currentDay < totalDays) {
        onDayChange(currentDay + 1);
      } else if (deltaX > threshold && currentDay > 1) {
        onDayChange(currentDay - 1);
      }
      setSwiping(false);
    },
    [swiping, currentDay, totalDays, onDayChange]
  );

  useEffect(() => {
    const activeTab = tabRefs.current.get(currentDay);
    if (activeTab) {
      activeTab.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  }, [currentDay]);

  /** Render a single day tab button */
  function renderDayTab(day: number) {
    const isActive = day === currentDay;
    const label = formatDayLabel(startDate, day, timezone);

    return (
      <button
        key={day}
        ref={(el) => {
          if (el) tabRefs.current.set(day, el);
          else tabRefs.current.delete(day);
        }}
        type="button"
        role="tab"
        aria-selected={isActive}
        aria-label={`Day ${day}, ${label}`}
        onClick={() => onDayChange(day)}
        className={`
          shrink-0
          px-[18px] py-[11px]
          text-[13px] font-sora
          border-b-2
          transition-colors duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
          ${
            isActive
              ? "text-accent font-medium border-accent"
              : "text-ink-400 font-normal border-transparent hover:text-ink-300"
          }
        `}
      >
        <span className="whitespace-nowrap">
          Day {day}
          <span className="font-dm-mono text-[10px] uppercase tracking-wider opacity-80 ml-1.5">
            {label}
          </span>
        </span>
      </button>
    );
  }

  return (
    <nav
      className="w-full"
      role="navigation"
      aria-label="Day navigation"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div className="flex items-center gap-2">
        {/* Prev arrow */}
        <button
          type="button"
          onClick={handlePrev}
          disabled={currentDay <= 1}
          className="
            shrink-0 p-2 rounded-lg
            text-ink-400 hover:text-ink-100
            hover:bg-surface
            transition-colors duration-150
            disabled:opacity-30 disabled:cursor-not-allowed
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
          "
          aria-label="Previous day"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="12 15 7 10 12 5" />
          </svg>
        </button>

        {/* Day tabs — horizontal scrollable strip, optionally grouped by leg */}
        <div
          ref={scrollRef}
          className="
            flex-1 overflow-x-auto scrollbar-none
            flex items-end gap-0
            scroll-smooth
            overscroll-x-contain
          "
          role="tablist"
          aria-label="Trip days"
        >
          {legGroups ? (
            legGroups.map((group, groupIdx) => (
              <div key={group.leg.id} className="flex items-end">
                {/* Separator between leg groups */}
                {groupIdx > 0 && (
                  <div className="w-px h-6 bg-warm-border mx-1 shrink-0" />
                )}
                {/* Leg group: city label + day tabs */}
                <div className="flex flex-col">
                  <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400 px-2 pb-1">
                    {group.leg.city}
                  </span>
                  <div className="flex gap-0">
                    {group.days.map((day) => renderDayTab(day))}
                  </div>
                </div>
              </div>
            ))
          ) : (
            days.map((day) => renderDayTab(day))
          )}
        </div>

        {/* Next arrow */}
        <button
          type="button"
          onClick={handleNext}
          disabled={currentDay >= totalDays}
          className="
            shrink-0 p-2 rounded-lg
            text-ink-400 hover:text-ink-100
            hover:bg-surface
            transition-colors duration-150
            disabled:opacity-30 disabled:cursor-not-allowed
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
          "
          aria-label="Next day"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="8 5 13 10 8 15" />
          </svg>
        </button>
      </div>

      {/* Mobile swipe hint */}
      <p className="mt-1 text-center font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider sm:hidden">
        Swipe to change day
      </p>
    </nav>
  );
}
