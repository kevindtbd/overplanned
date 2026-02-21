"use client";

// DayNavigation — Swipeable (mobile) or tabbed (desktop) day selector.
// Usage:
//   <DayNavigation
//     totalDays={5}
//     currentDay={1}
//     onDayChange={setCurrentDay}
//     startDate="2026-03-15"
//     timezone="Asia/Tokyo"
//   />

import { useCallback, useRef, useState } from "react";

interface DayNavigationProps {
  totalDays: number;
  currentDay: number;
  onDayChange: (day: number) => void;
  /** Trip start date ISO string — used to show actual dates on tabs */
  startDate: string;
  timezone?: string;
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

export function DayNavigation({
  totalDays,
  currentDay,
  onDayChange,
  startDate,
  timezone,
}: DayNavigationProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef<number>(0);
  const [swiping, setSwiping] = useState(false);

  const days = Array.from({ length: totalDays }, (_, i) => i + 1);

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

        {/* Day tabs — scrollable on mobile, full display on desktop */}
        <div
          ref={scrollRef}
          className="
            flex-1 overflow-x-auto scrollbar-hide
            flex gap-1 sm:gap-2
            snap-x snap-mandatory
            scroll-smooth
          "
          role="tablist"
          aria-label="Trip days"
        >
          {days.map((day) => {
            const isActive = day === currentDay;
            const label = formatDayLabel(startDate, day, timezone);

            return (
              <button
                key={day}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-label={`Day ${day}, ${label}`}
                onClick={() => onDayChange(day)}
                className={`
                  snap-start shrink-0
                  flex flex-col items-center gap-0.5
                  px-3 py-2 rounded-lg
                  transition-all duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
                  ${
                    isActive
                      ? "bg-accent text-white shadow-sm"
                      : "bg-surface text-ink-400 hover:bg-base hover:text-ink-100 border border-ink-700"
                  }
                `}
              >
                <span className="font-sora text-sm font-semibold">
                  Day {day}
                </span>
                <span className="font-dm-mono text-[10px] uppercase tracking-wider opacity-80">
                  {label}
                </span>
              </button>
            );
          })}
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
