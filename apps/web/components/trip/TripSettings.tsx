"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { downloadIcsFile } from "@/lib/ics-export";
import type { IcsTripData } from "@/lib/ics-export";
import { toMidnightISO, nightsBetween } from "@/lib/utils/dates";
import { MAX_TRIP_NIGHTS } from "@/lib/constants/trip";
import { LegEditor } from "./LegEditor";

interface TripSettingsProps {
  trip: {
    id: string;
    name: string | null;
    destination: string;
    city: string;
    country: string;
    status: string;
    mode: string;
    startDate: string;
    endDate: string;
    timezone: string;
    legs: Array<{
      id: string;
      city: string;
      country: string;
      timezone: string | null;
      destination: string;
      startDate: string;
      endDate: string;
      position: number;
    }>;
    slots: Array<{
      id: string;
      dayNumber: number;
      sortOrder: number;
      startTime: string | null;
      endTime: string | null;
      durationMinutes: number | null;
      activityNode: { name: string; category: string } | null;
    }>;
  };
  myRole: string;
  onClose: () => void;
  onTripUpdate: (dirtyFields?: Record<string, string>) => void;
}

type ConfirmAction = "archive" | "delete" | null;

export function TripSettings({ trip, myRole, onClose, onTripUpdate }: TripSettingsProps) {
  const router = useRouter();

  // Editable fields
  const [name, setName] = useState(trip.name ?? "");
  const [startDate, setStartDate] = useState(trip.startDate.split("T")[0]);
  const [endDate, setEndDate] = useState(trip.endDate.split("T")[0]);
  const [mode, setMode] = useState(trip.mode);

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const isOrganizer = myRole === "organizer";

  // Compute max end date for the date picker
  const maxEndDate = (() => {
    if (!startDate) return undefined;
    const d = new Date(startDate);
    d.setDate(d.getDate() + MAX_TRIP_NIGHTS);
    return d.toISOString().split("T")[0];
  })();

  // Compute dirty fields
  const getDirtyFields = useCallback(() => {
    const dirty: Record<string, string> = {};
    if (name !== (trip.name ?? "")) dirty.name = name;
    if (startDate !== trip.startDate.split("T")[0])
      dirty.startDate = toMidnightISO(startDate);
    if (endDate !== trip.endDate.split("T")[0])
      dirty.endDate = toMidnightISO(endDate);
    if (mode !== trip.mode) dirty.mode = mode;
    return dirty;
  }, [name, startDate, endDate, mode, trip]);

  const hasDirtyFields = Object.keys(getDirtyFields()).length > 0;

  const handleSave = useCallback(async () => {
    const dirty = getDirtyFields();
    if (Object.keys(dirty).length === 0) {
      onClose();
      return;
    }

    // Client-side date validation before hitting API
    if (dirty.startDate !== undefined || dirty.endDate !== undefined) {
      const mergedStart = dirty.startDate ?? toMidnightISO(trip.startDate);
      const mergedEnd = dirty.endDate ?? toMidnightISO(trip.endDate);
      const nights = nightsBetween(mergedStart, mergedEnd);

      if (nights <= 0) {
        setError("End date must be after start date");
        return;
      }
      if (nights > MAX_TRIP_NIGHTS) {
        setError(`Trip cannot exceed ${MAX_TRIP_NIGHTS} nights`);
        return;
      }
    }

    setSaving(true);
    setError(null);

    try {
      const res = await fetch(`/api/trips/${trip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dirty),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to save changes");
      }

      onTripUpdate(dirty);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }, [getDirtyFields, trip.id, onTripUpdate, onClose]);

  const handleExport = useCallback(() => {
    const tripStart = new Date(trip.startDate);
    const icsData: IcsTripData = {
      id: trip.id,
      name: trip.name || trip.destination,
      startDate: trip.startDate.split("T")[0],
      endDate: trip.endDate.split("T")[0],
      legs: (trip.legs || []).map((leg) => {
        const legStart = new Date(leg.destination ? trip.startDate : trip.startDate);
        const dayOffset = Math.round(
          (new Date(trip.startDate).getTime() - tripStart.getTime()) / (1000 * 60 * 60 * 24)
        );
        return {
          city: leg.city,
          timezone: leg.timezone || "UTC",
          startDate: trip.startDate.split("T")[0],
          endDate: trip.endDate.split("T")[0],
          dayOffset: 0,
        };
      }),
      slots: trip.slots.map((s) => ({
        id: s.id,
        dayNumber: s.dayNumber,
        sortOrder: s.sortOrder,
        startTime: s.startTime,
        endTime: s.endTime,
        durationMinutes: s.durationMinutes,
        activityNode: s.activityNode,
      })),
    };
    // Fallback: if no legs, create a synthetic one from derived fields
    if (icsData.legs.length === 0) {
      icsData.legs = [{
        city: trip.city,
        timezone: trip.timezone || "UTC",
        startDate: trip.startDate.split("T")[0],
        endDate: trip.endDate.split("T")[0],
        dayOffset: 0,
      }];
    }
    downloadIcsFile(icsData);
  }, [trip]);

  const handleArchive = useCallback(async () => {
    setActionLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/trips/${trip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "archived" }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to archive trip");
      }
      onTripUpdate();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive trip");
    } finally {
      setActionLoading(false);
      setConfirmAction(null);
    }
  }, [trip.id, onTripUpdate, onClose]);

  const handleDelete = useCallback(async () => {
    setActionLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/trips/${trip.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to delete trip");
      }
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete trip");
      setActionLoading(false);
      setConfirmAction(null);
    }
  }, [trip.id, router]);

  return (
    <div className="rounded-xl border border-warm-border bg-warm-surface overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-warm-border">
        <h2 className="font-sora text-base font-medium text-ink-100">
          Trip Settings
        </h2>
        <button
          onClick={onClose}
          className="rounded-lg p-2 text-ink-400 hover:text-ink-100 hover:bg-warm-surface transition-colors"
          aria-label="Close settings"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-5 py-3 bg-red-400/10 border-b border-red-400/20">
          <p className="font-dm-mono text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* Editable fields */}
      <div className="px-5 py-4 space-y-4 border-b border-warm-border">
        {/* Trip name */}
        <div className="space-y-1.5">
          <label
            htmlFor="trip-name"
            className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider"
          >
            Trip name
          </label>
          <input
            id="trip-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={trip.destination}
            className="w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2.5 font-sora text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
          />
        </div>

        {/* Dates */}
        <div className="space-y-1.5">
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Dates
          </span>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="start-date" className="sr-only">
                Start date
              </label>
              <input
                id="start-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2.5 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
              />
            </div>
            <div>
              <label htmlFor="end-date" className="sr-only">
                End date
              </label>
              <input
                id="end-date"
                type="date"
                value={endDate}
                max={maxEndDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2.5 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Mode */}
        <div className="space-y-1.5">
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Mode
          </span>
          <div className="flex gap-2">
            {["solo", "group"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-lg px-4 py-2.5 font-sora text-sm font-medium transition-colors min-h-[44px] ${
                  mode === m
                    ? "bg-accent text-white"
                    : "border border-warm-border text-ink-400 hover:text-ink-100 hover:border-ink-600"
                }`}
              >
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Save / Cancel */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2.5 font-sora text-sm font-medium text-ink-400 hover:text-ink-100 transition-colors min-h-[44px]"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !hasDirtyFields}
            className="rounded-lg bg-accent px-4 py-2.5 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>

      {/* Export */}
      <div className="px-5 py-4 border-b border-warm-border">
        <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
          Export
        </span>
        <button
          onClick={handleExport}
          className="mt-2 w-full rounded-lg border border-warm-border px-4 py-2.5 font-sora text-sm font-medium text-ink-100 hover:bg-warm-background transition-colors min-h-[44px] text-left flex items-center gap-2"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          Export to Calendar (.ics)
        </button>
      </div>

      {/* Leg management — organizer only, draft/planning */}
      {isOrganizer && (trip.status === "draft" || trip.status === "planning") && (
        <div className="px-5 py-4 border-b border-warm-border">
          <LegEditor
            tripId={trip.id}
            legs={trip.legs}
            tripStatus={trip.status}
            isOrganizer={isOrganizer}
            onLegsChange={onTripUpdate}
          />
        </div>
      )}

      {/* Danger zone — organizer only, all non-archived statuses */}
      {isOrganizer && trip.status !== "archived" && (
          <div className="px-5 py-4">
            <span className="font-dm-mono text-xs text-red-400 uppercase tracking-wider">
              Danger zone
            </span>
            <div className="mt-2 space-y-2">
              {/* Archive — any non-archived status */}
              {confirmAction === "archive" ? (
                <div className="rounded-lg border border-red-400/30 bg-red-400/5 p-3 space-y-3">
                  <p className="font-sora text-sm text-ink-100">
                    Archive this trip? It will be read-only and hidden from your main dashboard.
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmAction(null)}
                      disabled={actionLoading}
                      className="rounded-lg px-3 py-2 font-sora text-sm text-ink-400 hover:text-ink-100 transition-colors min-h-[44px]"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleArchive}
                      disabled={actionLoading}
                      className="rounded-lg border border-red-400/30 px-3 py-2 font-sora text-sm font-medium text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50 min-h-[44px]"
                    >
                      {actionLoading ? "Archiving..." : "Yes, archive"}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmAction("archive")}
                  className="w-full rounded-lg border border-red-400/30 px-4 py-2.5 font-sora text-sm font-medium text-red-400 hover:bg-red-400/10 transition-colors min-h-[44px] text-left"
                >
                  Archive trip
                </button>
              )}

              {/* Delete — draft and planning only */}
              {(trip.status === "draft" || trip.status === "planning") && (
                <>
                  {confirmAction === "delete" ? (
                    <div className="rounded-lg border border-red-400/30 bg-red-400/5 p-3 space-y-3">
                      <p className="font-sora text-sm text-ink-100">
                        Delete this trip? This cannot be undone.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setConfirmAction(null)}
                          disabled={actionLoading}
                          className="rounded-lg px-3 py-2 font-sora text-sm text-ink-400 hover:text-ink-100 transition-colors min-h-[44px]"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleDelete}
                          disabled={actionLoading}
                          className="rounded-lg border border-red-400/30 px-3 py-2 font-sora text-sm font-medium text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50 min-h-[44px]"
                        >
                          {actionLoading ? "Deleting..." : "Yes, delete"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmAction("delete")}
                      className="w-full rounded-lg border border-red-400/30 px-4 py-2.5 font-sora text-sm font-medium text-red-400 hover:bg-red-400/10 transition-colors min-h-[44px] text-left"
                    >
                      Delete trip
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}
    </div>
  );
}
