"use client";

import { useState, useEffect } from "react";

// ---------- Config ----------

type NotifField =
  | "tripReminders"
  | "morningBriefing"
  | "groupActivity"
  | "postTripPrompt"
  | "checkinReminder"
  | "citySeeded"
  | "inspirationNudges"
  | "productUpdates";

type NotifGroup = {
  heading: string;
  items: { field: NotifField; label: string }[];
};

const NOTIF_GROUPS: NotifGroup[] = [
  {
    heading: "Trip activity",
    items: [
      { field: "tripReminders", label: "Reminders before upcoming trips" },
      { field: "morningBriefing", label: "Daily plans for active trips" },
      { field: "groupActivity", label: "When trip members make changes" },
      { field: "postTripPrompt", label: "Review prompts after trips end" },
      { field: "checkinReminder", label: "Check-in prompts during active trips" },
    ],
  },
  {
    heading: "Discovery",
    items: [
      { field: "citySeeded", label: "When new cities are added" },
      { field: "inspirationNudges", label: "Destination ideas based on your style" },
    ],
  },
  {
    heading: "Product",
    items: [
      { field: "productUpdates", label: "Feature announcements and news" },
    ],
  },
];

// ---------- Types ----------

type NotifsState = Record<NotifField, boolean>;

const DEFAULTS: NotifsState = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  checkinReminder: false,
  citySeeded: true,
  inspirationNudges: false,
  productUpdates: false,
};

// ---------- Component ----------

export function NotificationsSection() {
  const [notifs, setNotifs] = useState<NotifsState>(DEFAULTS);
  const [preTripDaysBefore, setPreTripDaysBefore] = useState(3);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/notifications");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setNotifs(data);
          setPreTripDaysBefore(data.preTripDaysBefore ?? 3);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  async function toggle(field: NotifField) {
    const prev = notifs[field];
    const next = !prev;

    // Optimistic update
    setNotifs((s) => ({ ...s, [field]: next }));

    try {
      const res = await fetch("/api/settings/notifications", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: next }),
      });
      if (!res.ok) throw new Error();
    } catch {
      // Revert on failure
      setNotifs((s) => ({ ...s, [field]: prev }));
    }
  }

  async function handleDaysChange(value: number) {
    const prev = preTripDaysBefore;
    setPreTripDaysBefore(value);
    try {
      const res = await fetch("/api/settings/notifications", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preTripDaysBefore: value }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setPreTripDaysBefore(prev);
    }
  }

  return (
    <section aria-labelledby="notifications-heading">
      <h2 id="notifications-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Notifications
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-6">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="h-4 w-48 bg-warm-border rounded" />
                <div className="h-6 w-10 bg-warm-border rounded-full" />
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load notification preferences.</p>
        ) : (
          NOTIF_GROUPS.map((group) => (
            <div key={group.heading}>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-3">
                {group.heading}
              </h3>
              <div className="space-y-3">
                {group.items.map(({ field, label }) => (
                  <div key={field}>
                    <div className="flex items-center justify-between">
                      <span className="font-sora text-sm text-ink-200">{label}</span>
                      <button
                        role="switch"
                        aria-checked={notifs[field]}
                        onClick={() => toggle(field)}
                        className={`
                          relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full
                          border-2 border-transparent transition-colors
                          ${notifs[field] ? "bg-accent" : "bg-ink-500"}
                        `}
                      >
                        <span
                          aria-hidden="true"
                          className={`
                            pointer-events-none inline-block h-5 w-5 rounded-full bg-white
                            shadow-sm transition-transform
                            ${notifs[field] ? "translate-x-4" : "translate-x-0"}
                          `}
                        />
                      </button>
                    </div>
                    {field === "tripReminders" && notifs.tripReminders && (
                      <div className="mt-2">
                        <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-2">
                          Remind me before trips
                        </span>
                        <div className="flex gap-2">
                          {[
                            { value: 1, label: "1 day" },
                            { value: 3, label: "3 days" },
                            { value: 7, label: "1 week" },
                          ].map(({ value, label: pillLabel }) => (
                            <label key={value} className={`
                              flex items-center px-3 py-1.5 rounded-lg border cursor-pointer
                              font-sora text-sm transition-colors
                              ${preTripDaysBefore === value
                                ? "border-accent bg-accent/10 text-ink-100"
                                : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                              }
                            `}>
                              <input
                                type="radio"
                                name="preTripDaysBefore"
                                value={value}
                                checked={preTripDaysBefore === value}
                                onChange={() => handleDaysChange(value)}
                                className="sr-only"
                              />
                              {pillLabel}
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
