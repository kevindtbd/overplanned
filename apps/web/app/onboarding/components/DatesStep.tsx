"use client";

import { useState, useEffect } from "react";

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  );
}

interface DatesStepProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
}

export function DatesStep({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: DatesStepProps) {
  const [tripLength, setTripLength] = useState<number | null>(null);

  const today = new Date().toISOString().split("T")[0];

  useEffect(() => {
    if (startDate && endDate) {
      const start = new Date(startDate);
      const end = new Date(endDate);
      const diff = Math.ceil(
        (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
      );
      setTripLength(diff > 0 ? diff : null);
    } else {
      setTripLength(null);
    }
  }, [startDate, endDate]);

  return (
    <div className="mx-auto w-full max-w-md">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        When are you going?
      </h2>
      <p className="label-mono mt-2">pick your travel dates</p>

      <div className="mt-6 space-y-4">
        <div>
          <label
            htmlFor="start-date"
            className="label-mono mb-1.5 block"
          >
            start date
          </label>
          <div className="relative">
            <CalendarIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary" />
            <input
              id="start-date"
              type="date"
              value={startDate}
              min={today}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="w-full rounded-lg border border-ink-700 bg-surface py-3 pl-10 pr-4 font-dm-mono text-sm text-primary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="end-date"
            className="label-mono mb-1.5 block"
          >
            end date
          </label>
          <div className="relative">
            <CalendarIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary" />
            <input
              id="end-date"
              type="date"
              value={endDate}
              min={startDate || today}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="w-full rounded-lg border border-ink-700 bg-surface py-3 pl-10 pr-4 font-dm-mono text-sm text-primary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
          </div>
        </div>
      </div>

      {tripLength !== null && tripLength > 0 && (
        <div className="mt-4 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
          <span className="label-mono">trip length</span>
          <p className="mt-1 font-sora text-lg font-medium text-primary">
            {tripLength} {tripLength === 1 ? "night" : "nights"}
          </p>
        </div>
      )}
    </div>
  );
}
