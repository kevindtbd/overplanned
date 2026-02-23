"use client";

// Diary Detail Page -- /diary/[id]
// Shows a backfilled trip with venue list, photos, enrichment controls.
// Not a planner: flat venue list, no day-by-day timeline, no FAB.

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { CardSkeleton, ErrorState } from "@/components/states";

// ---------- Types ----------

interface BackfillVenue {
  id: string;
  extractedName: string;
  extractedCategory: string | null;
  extractedDate: string | null;
  isResolved: boolean;
  isQuarantined: boolean;
  flagged: boolean;
  wouldReturn: boolean | null;
  activityNode: {
    name: string;
    neighborhood: string | null;
    priceLevel: number | null;
    category: string;
  } | null;
  photos: {
    id: string;
    signedUrl: string;
    exifLat: number | null;
    exifLng: number | null;
  }[];
}

interface BackfillTripDetail {
  id: string;
  city: string;
  country: string;
  startDate: string | null;
  endDate: string | null;
  contextTag: string | null;
  tripNote: string | null;
  status: string;
  venues: BackfillVenue[];
}

// ---------- Constants ----------

const CONTEXT_OPTIONS = [
  { value: "solo", label: "Solo" },
  { value: "partner", label: "Partner" },
  { value: "family", label: "Family" },
  { value: "friends", label: "Friends" },
  { value: "work", label: "Work" },
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  dining: "Dining",
  drinks: "Drinks",
  culture: "Culture",
  outdoors: "Outdoors",
  active: "Active",
  entertainment: "Entertainment",
  shopping: "Shopping",
  experience: "Experience",
  nightlife: "Nightlife",
  wellness: "Wellness",
};

// ---------- Icons ----------

function HeartIcon({ filled, className }: { filled: boolean; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

function PlusIcon({ className }: { className?: string }) {
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
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function MapPinIcon({ className }: { className?: string }) {
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
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
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

// ---------- Helpers ----------

function formatDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = {
    month: "long",
    day: "numeric",
    year: "numeric",
  };
  const startStr = s.toLocaleDateString("en-US", { month: "long", day: "numeric" });
  const endStr = e.toLocaleDateString("en-US", opts);
  return `${startStr} - ${endStr}`;
}

function priceLabel(level: number | null): string {
  if (!level) return "";
  return "$".repeat(Math.min(level, 4));
}

// ---------- VenueCard ----------

function VenueCard({
  venue,
  onToggleWouldReturn,
  onPhotoUpload,
}: {
  venue: BackfillVenue;
  onToggleWouldReturn: (venueId: string, value: boolean) => void;
  onPhotoUpload: (venueId: string) => void;
}) {
  const displayName = venue.activityNode?.name ?? venue.extractedName;
  const category = venue.activityNode?.category ?? venue.extractedCategory;
  const isResolved = venue.isResolved && venue.activityNode;

  return (
    <div
      className={`rounded-xl border p-4 ${
        venue.flagged
          ? "border-ink-700/50 bg-warm-surface/50"
          : "border-warm-border bg-warm-surface"
      }`}
      data-testid="venue-card"
    >
      {/* Venue header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h4
            className={`font-sora text-sm font-medium ${
              isResolved ? "text-ink-100" : "text-ink-400"
            }`}
          >
            {displayName}
          </h4>

          {/* Meta row */}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {category && (
              <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
                {CATEGORY_LABELS[category] || category}
              </span>
            )}
            {isResolved && venue.activityNode?.neighborhood && (
              <span className="font-dm-mono text-[10px] text-ink-500">
                {venue.activityNode.neighborhood}
              </span>
            )}
            {isResolved && venue.activityNode?.priceLevel && (
              <span className="font-dm-mono text-[10px] text-ink-400">
                {priceLabel(venue.activityNode.priceLevel)}
              </span>
            )}
            {venue.extractedDate && (
              <span className="font-dm-mono text-[10px] text-ink-500">
                {venue.extractedDate}
              </span>
            )}
          </div>

          {/* Unresolved label */}
          {!isResolved && !venue.flagged && (
            <p className="mt-1 font-dm-mono text-[10px] text-ink-500">
              Not in our database yet
            </p>
          )}

          {/* Quarantined label */}
          {venue.flagged && (
            <p className="mt-1 font-dm-mono text-[10px] text-ink-500">
              We couldn't verify this one
            </p>
          )}
        </div>

        {/* Would return toggle -- resolved venues only */}
        {isResolved && !venue.flagged && (
          <button
            onClick={() => onToggleWouldReturn(venue.id, !venue.wouldReturn)}
            className={`flex-shrink-0 p-1.5 rounded-lg transition-colors ${
              venue.wouldReturn
                ? "text-accent"
                : "text-ink-500 hover:text-ink-400"
            }`}
            aria-label={
              venue.wouldReturn
                ? `Remove would return for ${displayName}`
                : `Mark would return for ${displayName}`
            }
            data-testid="would-return-toggle"
          >
            <HeartIcon filled={!!venue.wouldReturn} className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Photos */}
      {venue.photos.length > 0 && (
        <div className="mt-3 flex gap-2 overflow-x-auto">
          {venue.photos.slice(0, 4).map((photo) => (
            <div
              key={photo.id}
              className="relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg"
            >
              <img
                src={photo.signedUrl}
                alt={`Photo of ${displayName}`}
                className="h-full w-full object-cover"
              />
              {photo.exifLat && photo.exifLng && (
                <span className="absolute bottom-0.5 right-0.5" title="Location detected">
                  <MapPinIcon className="h-3 w-3 text-white drop-shadow" />
                </span>
              )}
            </div>
          ))}
          {venue.photos.length > 4 && (
            <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-lg bg-warm-background">
              <span className="font-dm-mono text-xs text-ink-400">
                +{venue.photos.length - 4}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Photo upload button -- resolved venues only */}
      {isResolved && !venue.flagged && (
        <button
          onClick={() => onPhotoUpload(venue.id)}
          className="mt-2 inline-flex items-center gap-1 font-dm-mono text-[10px] text-ink-400 hover:text-accent transition-colors"
          data-testid="photo-upload-btn"
        >
          <PlusIcon className="h-3 w-3" />
          Add photo
        </button>
      )}
    </div>
  );
}

// ---------- Main Page ----------

export default function DiaryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [trip, setTrip] = useState<BackfillTripDetail | null>(null);
  const [fetchState, setFetchState] = useState<"loading" | "error" | "success">(
    "loading"
  );
  const [errorMessage, setErrorMessage] = useState("Failed to load diary");
  const [tripNote, setTripNote] = useState("");
  const [isSavingNote, setIsSavingNote] = useState(false);

  // Hidden file input for photo upload
  const [uploadVenueId, setUploadVenueId] = useState<string | null>(null);

  const fetchTrip = useCallback(async () => {
    setFetchState("loading");
    try {
      const res = await fetch(`/api/backfill/trips/${id}`);
      if (!res.ok) {
        if (res.status === 404) throw new Error("Trip not found");
        if (res.status === 403) throw new Error("Access denied");
        throw new Error("Failed to load diary");
      }
      const data = await res.json();
      setTrip(data.trip);
      setTripNote(data.trip.tripNote || "");
      setFetchState("success");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load diary"
      );
      setFetchState("error");
    }
  }, [id]);

  useEffect(() => {
    fetchTrip();
  }, [fetchTrip]);

  // Context tag update
  async function handleContextTag(tag: string) {
    if (!trip) return;
    const newTag = trip.contextTag === tag ? null : tag;

    // Optimistic update
    setTrip({ ...trip, contextTag: newTag });

    try {
      const res = await fetch(`/api/backfill/trips/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contextTag: newTag }),
      });
      if (!res.ok) {
        // Revert
        setTrip((prev) => (prev ? { ...prev, contextTag: trip.contextTag } : prev));
      }
    } catch {
      setTrip((prev) => (prev ? { ...prev, contextTag: trip.contextTag } : prev));
    }
  }

  // Trip note auto-save on blur
  async function handleNoteSave() {
    if (!trip || tripNote === (trip.tripNote || "")) return;
    setIsSavingNote(true);
    try {
      await fetch(`/api/backfill/trips/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tripNote: tripNote.trim() || null }),
      });
      setTrip((prev) =>
        prev ? { ...prev, tripNote: tripNote.trim() || null } : prev
      );
    } catch {
      // Silent fail on auto-save
    } finally {
      setIsSavingNote(false);
    }
  }

  // Would return toggle
  async function handleWouldReturn(venueId: string, value: boolean) {
    if (!trip) return;

    // Optimistic update
    setTrip({
      ...trip,
      venues: trip.venues.map((v) =>
        v.id === venueId ? { ...v, wouldReturn: value } : v
      ),
    });

    try {
      const res = await fetch(`/api/backfill/venues/${venueId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wouldReturn: value }),
      });
      if (!res.ok) {
        // Revert
        setTrip((prev) =>
          prev
            ? {
                ...prev,
                venues: prev.venues.map((v) =>
                  v.id === venueId ? { ...v, wouldReturn: !value } : v
                ),
              }
            : prev
        );
      }
    } catch {
      setTrip((prev) =>
        prev
          ? {
              ...prev,
              venues: prev.venues.map((v) =>
                v.id === venueId ? { ...v, wouldReturn: !value } : v
              ),
            }
          : prev
      );
    }
  }

  // Photo upload
  async function handlePhotoUpload(venueId: string) {
    setUploadVenueId(venueId);
    // Trigger file input click
    const input = document.getElementById("photo-file-input") as HTMLInputElement;
    if (input) {
      input.value = "";
      input.click();
    }
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !uploadVenueId || !trip) return;

    // Client-side validation
    if (file.size > 10 * 1024 * 1024) {
      alert("Photo must be under 10MB");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/api/backfill/venues/${uploadVenueId}/photos`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || "Failed to upload photo");
        return;
      }

      // Refresh trip data to show new photo
      await fetchTrip();
    } catch {
      alert("Failed to upload photo");
    } finally {
      setUploadVenueId(null);
    }
  }

  // Sort venues: chronological if dates, alphabetical by category otherwise
  const sortedVenues = trip
    ? [...trip.venues].sort((a, b) => {
        if (a.extractedDate && b.extractedDate) {
          return a.extractedDate.localeCompare(b.extractedDate);
        }
        const catA = a.extractedCategory || "zzz";
        const catB = b.extractedCategory || "zzz";
        return catA.localeCompare(catB);
      })
    : [];

  return (
    <AppShell context="app">
      {/* Hidden file input for photo uploads */}
      <input
        id="photo-file-input"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/heic"
        className="hidden"
        onChange={handleFileSelected}
      />

      {/* Back button */}
      <button
        onClick={() => router.push("/dashboard")}
        className="flex items-center gap-1.5 text-ink-400 hover:text-ink-300 transition-colors mb-6"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        <span className="font-dm-mono text-xs">Back to dashboard</span>
      </button>

      {/* Loading */}
      {fetchState === "loading" && (
        <div className="space-y-4">
          <CardSkeleton className="h-24" />
          <CardSkeleton className="h-40" />
        </div>
      )}

      {/* Error */}
      {fetchState === "error" && (
        <ErrorState message={errorMessage} onRetry={fetchTrip} />
      )}

      {/* Content */}
      {fetchState === "success" && trip && (
        <div className="space-y-6">
          {/* Header */}
          <header>
            <h1 className="font-sora text-2xl font-medium text-ink-100 sm:text-3xl">
              {trip.city}
            </h1>
            <p className="mt-0.5 font-dm-mono text-sm text-ink-400">
              {trip.country}
            </p>
            {trip.startDate && trip.endDate ? (
              <p className="mt-1 font-dm-mono text-xs text-ink-500">
                {formatDateRange(trip.startDate, trip.endDate)}
              </p>
            ) : (
              <p className="mt-1 font-dm-mono text-xs text-ink-500">
                Dates unknown
              </p>
            )}

            {/* Processing badge */}
            {trip.status === "processing" && (
              <span className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-accent/10 px-3 py-1 font-dm-mono text-[10px] uppercase tracking-wider text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                Processing
              </span>
            )}
          </header>

          {/* Context tag selector */}
          <div>
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-500 mb-2">
              Trip context
            </p>
            <div className="flex flex-wrap gap-2">
              {CONTEXT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleContextTag(opt.value)}
                  className={`rounded-full px-3 py-1.5 font-dm-mono text-xs transition-colors ${
                    trip.contextTag === opt.value
                      ? "bg-accent text-white"
                      : "bg-warm-surface border border-warm-border text-ink-400 hover:border-accent/30"
                  }`}
                  data-testid={`context-tag-${opt.value}`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Venue list */}
          <section>
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-500 mb-3">
              Places ({sortedVenues.filter((v) => !v.flagged).length})
            </p>
            <div className="space-y-3">
              {sortedVenues.map((venue) => (
                <VenueCard
                  key={venue.id}
                  venue={venue}
                  onToggleWouldReturn={handleWouldReturn}
                  onPhotoUpload={handlePhotoUpload}
                />
              ))}
              {sortedVenues.length === 0 && trip.status === "complete" && (
                <p className="text-sm text-ink-500 py-8 text-center">
                  No venues were extracted from your trip description.
                </p>
              )}
            </div>
          </section>

          {/* Trip note */}
          <section>
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-500 mb-2">
              Anything you'd do differently?
            </p>
            <textarea
              value={tripNote}
              onChange={(e) => setTripNote(e.target.value)}
              onBlur={handleNoteSave}
              placeholder="Optional -- what worked, what didn't, what you'd change next time"
              rows={3}
              className="w-full rounded-xl border-[1.5px] border-ink-700 bg-input py-3 px-4 font-sora text-sm text-primary placeholder:text-secondary/60 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 resize-none"
              data-testid="trip-note"
            />
            {isSavingNote && (
              <p className="mt-1 font-dm-mono text-[10px] text-ink-500">
                Saving...
              </p>
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
