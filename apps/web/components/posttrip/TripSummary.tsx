"use client";

// TripSummary — Post-trip summary card showing trip stats at a glance.
// Rendered at the top of the reflection page.

// ---------- Types ----------

export interface TripSummaryData {
  destination: string;
  country: string;
  totalDays: number;
  totalSlots: number;
  completedSlots: number;
  skippedSlots: number;
  lovedSlots: number;
  startDate?: string;
  endDate?: string;
  coverImageUrl?: string;
}

interface TripSummaryProps {
  trip: TripSummaryData;
}

// ---------- Helpers ----------

function formatDateRange(start?: string, end?: string): string {
  if (!start || !end) return "";
  try {
    const opts: Intl.DateTimeFormatOptions = {
      month: "short",
      day: "numeric",
    };
    const s = new Date(start).toLocaleDateString("en-US", opts);
    const e = new Date(end).toLocaleDateString("en-US", {
      ...opts,
      year: "numeric",
    });
    return `${s} - ${e}`;
  } catch {
    return "";
  }
}

// ---------- Stat pill ----------

function StatPill({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: "terracotta" | "emerald" | "amber" | "gray";
}) {
  const colorMap = {
    terracotta: "bg-terracotta-50 text-terracotta-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    gray: "bg-gray-100 text-gray-600",
  };

  return (
    <div className={`flex flex-col items-center px-3 py-2 rounded-lg ${colorMap[color]}`}>
      <span className="font-sora font-bold text-lg leading-none">{value}</span>
      <span className="font-dm-mono text-[10px] uppercase tracking-wider mt-1">
        {label}
      </span>
    </div>
  );
}

// ---------- Component ----------

export function TripSummary({ trip }: TripSummaryProps) {
  const dateRange = formatDateRange(trip.startDate, trip.endDate);
  const completionRate =
    trip.totalSlots > 0
      ? Math.round((trip.completedSlots / trip.totalSlots) * 100)
      : 0;

  return (
    <article
      className="rounded-xl border border-warm-border bg-warm-surface overflow-hidden"
      aria-label={`Trip summary for ${trip.destination}`}
    >
      {/* Cover image */}
      {trip.coverImageUrl && (
        <div className="relative h-40 w-full overflow-hidden bg-warm-background">
          <img
            src={trip.coverImageUrl}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
          />
          {/* Gradient overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-warm-surface/90 to-transparent" />
        </div>
      )}

      <div className={`p-5 space-y-4 ${trip.coverImageUrl ? "-mt-10 relative" : ""}`}>
        {/* Destination header */}
        <div className="space-y-1">
          <h2 className="font-sora text-2xl font-bold text-warm-text-primary">
            {trip.destination}
          </h2>
          <div className="flex items-center gap-2">
            <span className="font-dm-mono text-xs text-warm-text-secondary uppercase tracking-wider">
              {trip.country}
            </span>
            {dateRange && (
              <>
                <span className="text-warm-border" aria-hidden="true">/</span>
                <span className="font-dm-mono text-xs text-warm-text-secondary">
                  {dateRange}
                </span>
              </>
            )}
          </div>
        </div>

        {/* Completion bar */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-dm-mono text-[10px] text-warm-text-secondary uppercase tracking-wider">
              Trip completion
            </span>
            <span className="font-dm-mono text-xs text-warm-text-primary font-medium">
              {completionRate}%
            </span>
          </div>
          <div className="h-1.5 bg-warm-border rounded-full overflow-hidden">
            <div
              className="h-full bg-terracotta-500 rounded-full transition-all duration-500"
              style={{ width: `${completionRate}%` }}
            />
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-4 gap-2">
          <StatPill label="Days" value={trip.totalDays} color="terracotta" />
          <StatPill label="Done" value={trip.completedSlots} color="emerald" />
          <StatPill label="Skipped" value={trip.skippedSlots} color="amber" />
          <StatPill label="Loved" value={trip.lovedSlots} color="terracotta" />
        </div>
      </div>
    </article>
  );
}
