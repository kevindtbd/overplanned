"use client";

// Post-Trip Memory Page -- /trip/[id]/memory
// Permanent read-only page for completed/archived trips.
// Assembles: TripSummary, PhotoStrip, VisitedMap, reflection summary, share, re-engage CTA.

import { useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { AppShell } from "@/components/layout/AppShell";
import { TripSummary, type TripSummaryData } from "@/components/posttrip/TripSummary";
import { PhotoStrip, type PhotoStripSlot } from "@/components/posttrip/PhotoStrip";
import type { VisitedSlot } from "@/components/posttrip/VisitedMap";
import { useTripDetail, type ReflectionSummary } from "@/lib/hooks/useTripDetail";
import { getCityPhoto } from "@/lib/city-photos";
import { ErrorState } from "@/components/states";

// Dynamic import for VisitedMap -- Leaflet requires window/document
const VisitedMap = dynamic(
  () =>
    import("@/components/posttrip/VisitedMap").then((mod) => ({
      default: mod.VisitedMap,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-64 bg-base rounded-xl border border-ink-700">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Loading map
          </span>
        </div>
      </div>
    ),
  }
);

// ---------- Types ----------

interface ShareState {
  loading: boolean;
  shareUrl: string | null;
  error: string | null;
}

// ---------- Section divider ----------

function SectionDivider() {
  return <div className="border-t border-warm-border" />;
}

// ---------- Map section (collapsible) ----------

function MapSection({
  slots,
  expanded,
  onToggle,
}: {
  slots: VisitedSlot[];
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <section className="space-y-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center justify-between w-full group"
        aria-expanded={expanded}
        aria-controls="visited-map-section"
      >
        <h2 className="font-sora text-lg font-semibold text-ink-100">
          Where You Went
        </h2>
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-ink-400 transition-transform duration-200 group-hover:text-ink-100 ${
            expanded ? "rotate-180" : ""
          }`}
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {expanded && (
        <div id="visited-map-section">
          {slots.length > 0 ? (
            <VisitedMap slots={slots} className="h-72 sm:h-80" />
          ) : (
            <div className="flex items-center justify-center h-40 bg-base rounded-xl border border-ink-700">
              <p className="font-dm-mono text-xs text-ink-400">
                No visited locations to display
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ---------- Photo strip wrapper (handles empty state) ----------

function PhotoStripSection({
  tripId,
  slots,
}: {
  tripId: string;
  slots: PhotoStripSlot[];
}) {
  if (slots.length === 0) {
    return (
      <section className="space-y-3">
        <h2 className="font-sora text-lg font-semibold text-ink-100">
          Trip Photos
        </h2>
        <div className="rounded-xl border border-warm-border bg-warm-surface p-5 flex flex-col items-center gap-3">
          <svg
            width="32"
            height="32"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-ink-400"
            aria-hidden="true"
          >
            <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
          <p className="font-dm-mono text-xs text-ink-400 text-center">
            Add photos from your trip
          </p>
        </div>
      </section>
    );
  }

  return <PhotoStrip tripId={tripId} slots={slots} />;
}

// ---------- Reflection summary section ----------

function ReflectionSection({
  tripId,
  summary,
  hasReflected,
}: {
  tripId: string;
  summary: ReflectionSummary | null;
  hasReflected: boolean;
}) {
  if (!hasReflected || !summary) {
    return (
      <section className="space-y-3">
        <h2 className="font-sora text-lg font-semibold text-ink-100">
          Your Reflection
        </h2>
        <div className="rounded-xl border border-warm-border bg-warm-surface p-5 space-y-3">
          <p className="font-dm-mono text-sm text-ink-400">
            You have not reflected on this trip yet. It takes about 60 seconds
            and helps us plan better next time.
          </p>
          <Link
            href={`/trip/${tripId}/reflection`}
            className="
              inline-flex items-center gap-2 rounded-lg
              bg-[#C4694F] px-5 py-2.5
              font-dm-mono text-sm text-white uppercase tracking-wider
              hover:bg-[#C4694F]/90 transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2
            "
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
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            Reflect on your trip
          </Link>
        </div>
      </section>
    );
  }

  const totalRated = summary.lovedCount + summary.skippedCount + summary.missedCount;

  return (
    <section className="space-y-3">
      <h2 className="font-sora text-lg font-semibold text-ink-100">
        Your Reflection
      </h2>
      <div className="rounded-xl border border-warm-border bg-warm-surface p-5 space-y-4">
        {/* Rating pills */}
        <div className="flex items-center gap-3 flex-wrap">
          {summary.lovedCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-light font-dm-mono text-xs uppercase tracking-wider">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="text-[#C4694F]"
                aria-hidden="true"
              >
                <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
              </svg>
              <span className="text-ink-100">{summary.lovedCount} loved</span>
            </span>
          )}
          {summary.skippedCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-ink-800 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
              {summary.skippedCount} skipped
            </span>
          )}
          {summary.missedCount > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warning-bg font-dm-mono text-xs text-warning uppercase tracking-wider">
              {summary.missedCount} missed
            </span>
          )}
          {totalRated > 0 && (
            <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
              {totalRated} rated total
            </span>
          )}
        </div>

        {/* Feedback text */}
        {summary.feedback && (
          <div className="space-y-1.5">
            <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
              Your notes
            </p>
            <p className="font-sora text-sm text-ink-100 leading-relaxed">
              {summary.feedback}
            </p>
          </div>
        )}

        {/* Edit link */}
        <Link
          href={`/trip/${tripId}/reflection`}
          className="inline-flex items-center gap-1.5 font-dm-mono text-xs text-[#C4694F] uppercase tracking-wider hover:text-[#C4694F]/80 transition-colors"
        >
          Edit reflection
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </Link>
      </div>
    </section>
  );
}

// ---------- Share section ----------

function ShareSection({
  tripId,
  shareState,
  onCreateShare,
}: {
  tripId: string;
  shareState: ShareState;
  onCreateShare: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!shareState.shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareState.shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silent fallback for older browsers
    }
  }, [shareState.shareUrl]);

  return (
    <section className="space-y-3">
      <h2 className="font-sora text-lg font-semibold text-ink-100">
        Share This Trip
      </h2>
      {shareState.shareUrl ? (
        <div className="rounded-xl border border-warm-border bg-warm-surface p-4 space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={shareState.shareUrl}
              className="flex-1 px-3 py-2 rounded-lg border border-ink-700 bg-surface font-dm-mono text-xs text-ink-100 truncate"
              aria-label="Share link"
            />
            <button
              type="button"
              onClick={handleCopy}
              className="shrink-0 rounded-lg px-3 py-2 border border-warm-border bg-surface font-dm-mono text-xs text-ink-100 uppercase tracking-wider hover:bg-warm-surface transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="font-dm-mono text-[10px] text-ink-400">
            Anyone with this link can view a summary of your trip
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-warm-border bg-warm-surface p-5 space-y-3">
          <p className="font-dm-mono text-sm text-ink-400">
            Create a shareable link so friends can see where you went
          </p>
          {shareState.error && (
            <p className="font-dm-mono text-xs text-error" role="alert">
              {shareState.error}
            </p>
          )}
          <button
            type="button"
            onClick={onCreateShare}
            disabled={shareState.loading}
            className="
              inline-flex items-center gap-2 rounded-lg
              border border-warm-border bg-surface px-5 py-2.5
              font-dm-mono text-sm text-ink-100 uppercase tracking-wider
              hover:bg-warm-surface transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2
              disabled:opacity-40 disabled:cursor-not-allowed
            "
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
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
            {shareState.loading ? "Creating link..." : "Share this trip"}
          </button>
        </div>
      )}
    </section>
  );
}

// ---------- Main page component ----------

export default function MemoryPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tripId = params.id;

  const {
    trip,
    hasReflected,
    reflectionSummary,
    fetchState,
    errorMessage,
    fetchTrip,
  } = useTripDetail(tripId);

  const [mapExpanded, setMapExpanded] = useState(true);
  const [shareState, setShareState] = useState<ShareState>({
    loading: false,
    shareUrl: null,
    error: null,
  });

  // Redirect if trip is not completed/archived
  const shouldRedirect =
    fetchState === "success" &&
    trip &&
    trip.status !== "completed" &&
    trip.status !== "archived";

  if (shouldRedirect) {
    router.replace(`/trip/${tripId}`);
    return null;
  }

  // Build TripSummary data from trip + reflectionSummary
  const summaryData: TripSummaryData | null = useMemo(() => {
    if (!trip) return null;
    const totalDays = Math.max(
      Math.ceil(
        (new Date(trip.endDate).getTime() -
          new Date(trip.startDate).getTime()) /
          (1000 * 60 * 60 * 24)
      ),
      1
    );
    return {
      destination: trip.destination || trip.legs?.[0]?.destination || "",
      country: trip.country || trip.legs?.[0]?.country || "",
      totalDays,
      totalSlots: trip.slots.length,
      completedSlots: trip.slots.filter(
        (s) => s.status === "completed" || s.status === "confirmed"
      ).length,
      skippedSlots: trip.slots.filter((s) => s.status === "skipped").length,
      lovedSlots: reflectionSummary?.lovedCount ?? 0,
      startDate: trip.startDate,
      endDate: trip.endDate,
      coverImageUrl: getCityPhoto(trip.city, 1200, 80),
    };
  }, [trip, reflectionSummary]);

  // Build PhotoStrip slots (completed/confirmed slots only)
  const photoSlots: PhotoStripSlot[] = useMemo(() => {
    if (!trip) return [];
    return trip.slots
      .filter(
        (s) => s.status === "completed" || s.status === "confirmed"
      )
      .map((s) => ({
        slotId: s.id,
        activityName: s.activityNode?.name ?? "Unnamed Activity",
        imageUrl: s.activityNode?.primaryImageUrl ?? undefined,
      }));
  }, [trip]);

  // Build VisitedMap slots (completed + skipped with coordinates)
  const mapSlots: VisitedSlot[] = useMemo(() => {
    if (!trip) return [];
    return trip.slots
      .filter(
        (s) =>
          (s.status === "completed" ||
            s.status === "confirmed" ||
            s.status === "skipped") &&
          s.activityNode?.latitude != null &&
          s.activityNode?.longitude != null
      )
      .map((s) => ({
        id: s.id,
        activityName: s.activityNode?.name ?? "Unnamed Activity",
        slotType: s.slotType,
        lat: s.activityNode!.latitude,
        lng: s.activityNode!.longitude,
        dayIndex: s.dayNumber - 1,
        timeLabel: s.startTime ?? undefined,
        status: s.status === "skipped" ? "skipped" : ("completed" as const),
      }));
  }, [trip]);

  // Share handler
  const handleCreateShare = useCallback(async () => {
    setShareState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await fetch(`/api/trips/${tripId}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to create share link");
      }
      const { shareUrl } = await res.json();
      setShareState({ loading: false, shareUrl, error: null });
    } catch (err) {
      setShareState({
        loading: false,
        shareUrl: null,
        error:
          err instanceof Error ? err.message : "Failed to create share link",
      });
    }
  }, [tripId]);

  const tripPhoto = trip ? getCityPhoto(trip.city) : undefined;
  const tripName = trip?.name || trip?.destination || "";

  // ---------- Loading ----------
  if (fetchState === "loading") {
    return (
      <AppShell context="trip" tripName="Loading...">
        <div className="max-w-2xl mx-auto space-y-6 pb-12">
          <div className="skel h-40 w-full rounded-xl" />
          <div className="skel h-6 w-48 rounded-full" />
          <div className="flex gap-3 overflow-hidden">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="skel h-36 w-36 rounded-xl shrink-0" />
            ))}
          </div>
          <div className="skel h-64 w-full rounded-xl" />
        </div>
      </AppShell>
    );
  }

  // ---------- Error ----------
  if (fetchState === "error") {
    return (
      <AppShell context="app">
        <div className="py-12">
          <ErrorState message={errorMessage} onRetry={fetchTrip} />
        </div>
      </AppShell>
    );
  }

  if (!trip || !summaryData) return null;

  return (
    <AppShell context="trip" tripPhoto={tripPhoto} tripName={tripName}>
      <div className="max-w-2xl mx-auto pb-12">
        <div className="bg-surface rounded-[22px] border border-ink-800 shadow-lg overflow-hidden">
          <div className="space-y-6 p-5 sm:p-6">
            {/* Back to trips */}
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 font-dm-mono text-xs text-ink-400 uppercase tracking-wider hover:text-terracotta transition-colors focus:outline-none focus:ring-2 focus:ring-terracotta focus:ring-offset-2 focus:ring-offset-surface rounded"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              <span>Back to trips</span>
            </Link>

            {/* 1. TripSummary hero */}
            <TripSummary trip={summaryData} />

            <SectionDivider />

            {/* 2. Photo strip */}
            <PhotoStripSection tripId={tripId} slots={photoSlots} />

            <SectionDivider />

            {/* 3. Visited map (collapsible, expanded by default) */}
            <MapSection
              slots={mapSlots}
              expanded={mapExpanded}
              onToggle={() => setMapExpanded((prev) => !prev)}
            />

            <SectionDivider />

            {/* 4. Reflection summary */}
            <ReflectionSection
              tripId={tripId}
              summary={reflectionSummary}
              hasReflected={hasReflected}
            />

            <SectionDivider />

            {/* 5. Share section */}
            <ShareSection
              tripId={tripId}
              shareState={shareState}
              onCreateShare={handleCreateShare}
            />

            <SectionDivider />

            {/* 6. "Ready for the next one?" re-engage CTA */}
            <section className="text-center space-y-3 py-2">
              <h2 className="font-sora text-lg font-semibold text-ink-100">
                Ready for the next one?
              </h2>
              <p className="font-dm-mono text-xs text-ink-400">
                Your travel profile has been updated based on this trip
              </p>
              <Link
                href="/explore"
                className="
                  inline-flex items-center gap-2 rounded-lg
                  bg-[#C4694F] px-6 py-3
                  font-sora text-sm font-medium text-white
                  hover:bg-[#C4694F]/90 transition-colors duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C4694F] focus-visible:ring-offset-2
                "
              >
                Find somewhere new
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
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              </Link>
            </section>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
