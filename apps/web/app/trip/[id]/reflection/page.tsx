"use client";

// Post-Trip Reflection Page — /trip/[id]/reflection
// Per-slot highlight rating (loved / skipped / missed) + single feedback question.
// Writes BehavioralSignals: post_loved, post_skipped, post_missed, post_disliked.
// Feedback can override slot status (completed → skipped if user says they didn't go).

import { useState, useCallback, useMemo, useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { SlotRating, type SlotRatingEvent, type SlotRatingValue } from "./components/SlotRating";
import { VIBE_CHIP_MAP, type VibeOption } from "@/lib/validations/reflection";

// ---------- Types ----------

interface ReflectionSlot {
  id: string;
  activityName: string;
  imageUrl?: string;
  activityNodeId?: string;
  originalStatus: "completed" | "skipped" | "confirmed" | "proposed";
}

interface SlotFeedback {
  rating: SlotRatingValue;
  overrideStatus?: "skipped"; // post-trip can override completed → skipped
}

// ---------- Component ----------

export default function ReflectionPage({
  params,
}: {
  params: { id: string };
}) {
  const [trip, setTrip] = useState<{
    id: string;
    destination: string;
    city: string;
    country: string;
    totalDays: number;
  } | null>(null);
  const [slots, setSlots] = useState<ReflectionSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [feedback, setFeedback] = useState<Record<string, SlotFeedback>>({});
  const [freeText, setFreeText] = useState("");
  const [selectedVibe, setSelectedVibe] = useState<VibeOption | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`/api/trips/${params.id}`);
        if (!res.ok) throw new Error("Failed to load trip");
        const { trip: tripData } = await res.json();

        const totalDays = Math.max(
          Math.ceil(
            (new Date(tripData.endDate).getTime() -
              new Date(tripData.startDate).getTime()) /
              (1000 * 60 * 60 * 24)
          ),
          1
        );

        setTrip({
          id: tripData.id,
          destination: tripData.legs?.[0]?.destination ?? tripData.legs?.[0]?.city ?? "",
          city: tripData.legs?.[0]?.city ?? "",
          country: tripData.legs?.[0]?.country ?? "",
          totalDays,
        });

        setSlots(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (tripData.slots ?? []).map((s: any) => ({
            id: s.id,
            activityName: s.activityNode?.name ?? "Unnamed Activity",
            imageUrl: s.activityNode?.primaryImageUrl ?? undefined,
            activityNodeId: s.activityNode?.id,
            originalStatus: s.status as ReflectionSlot["originalStatus"],
          }))
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trip");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.id]);

  // Track how many slots have been rated
  const ratedCount = useMemo(
    () => Object.values(feedback).filter((f) => f.rating !== null).length,
    [feedback]
  );

  const handleRate = useCallback(
    (event: SlotRatingEvent) => {
      const isSkippedRating = event.rating === "skipped";

      // Check if this rating overrides the slot's original completed status
      const slot = slots.find((s) => s.id === event.slotId);
      const overridesStatus =
        isSkippedRating && slot?.originalStatus === "completed";

      setFeedback((prev) => ({
        ...prev,
        [event.slotId]: {
          rating: event.rating,
          overrideStatus: overridesStatus ? "skipped" : undefined,
        },
      }));
    },
    [slots]
  );

  const handleSubmit = useCallback(async () => {
    if (submitted) return;
    setSubmitted(true);

    try {
      // Transform Record<slotId, SlotFeedback> into the array format
      // that the Zod schema expects: [{ slotId, rating }]
      const ratingsArray = Object.entries(feedback).map(([slotId, fb]) => ({
        slotId,
        rating: fb.rating,
      }));

      const response = await fetch(`/api/trips/${params.id}/reflection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ratings: ratingsArray,
          ...(freeText.trim() ? { feedback: freeText.trim() } : {}),
          ...(selectedVibe ? { vibe: selectedVibe } : {}),
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit reflection");
      }
    } catch (err) {
      console.error("[reflection] Failed to submit:", err);
      setSubmitted(false);
    }
  }, [params.id, feedback, freeText, selectedVibe, submitted]);

  // ---------- Loading state ----------
  if (loading) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
          <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Loading reflection
          </span>
        </div>
      </AppShell>
    );
  }

  // ---------- Error state ----------
  if (error || !trip) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[60vh] text-center gap-4">
          <p className="font-sora text-lg font-semibold text-ink-100">
            Could not load trip
          </p>
          <p className="font-dm-mono text-sm text-ink-400">{error}</p>
          <a
            href="/dashboard"
            className="
              inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
              bg-accent text-white
              font-dm-mono text-sm uppercase tracking-wider
              hover:bg-accent/90 transition-colors duration-150
            "
          >
            Back to dashboard
          </a>
        </div>
      </AppShell>
    );
  }

  // ---------- Submitted state ----------
  if (submitted) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
            <svg
              width="32"
              height="32"
              viewBox="0 0 32 32"
              fill="none"
              stroke="#059669"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="7 17 13 23 25 9" />
            </svg>
          </div>
          <h1 className="font-sora text-2xl font-bold text-ink-100">
            Thanks for reflecting
          </h1>
          <p className="font-dm-mono text-sm text-ink-400 max-w-sm">
            Your feedback helps us learn what you love so future trips feel even
            more you.
          </p>
          <a
            href={`/trip/${params.id}`}
            className="
              inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
              bg-accent text-white
              font-dm-mono text-sm uppercase tracking-wider
              hover:bg-accent/90 transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
            "
          >
            Back to trip
          </a>
        </div>
      </AppShell>
    );
  }

  // ---------- Main reflection form ----------
  return (
    <AppShell>
      <div className="space-y-8 max-w-2xl mx-auto pb-12">
        {/* Header */}
        <header className="space-y-2">
          <h1 className="font-sora text-2xl sm:text-3xl font-bold text-ink-100">
            How was {trip.destination}?
          </h1>
          <p className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            {trip.totalDays} days -- {slots.length} activities -- Tap to rate
            each highlight
          </p>
        </header>

        {/* Trip-level vibe */}
        <section className="space-y-3" aria-label="Overall trip vibe">
          <h2 className="font-sora text-lg font-semibold text-ink-100">
            How was the overall vibe?
          </h2>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Trip vibe rating">
            {(Object.entries(VIBE_CHIP_MAP) as [VibeOption, typeof VIBE_CHIP_MAP[VibeOption]][]).map(
              ([key, chip]) => {
                const isSelected = selectedVibe === key;
                return (
                  <button
                    key={key}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setSelectedVibe(isSelected ? null : key)}
                    className={`
                      font-dm-mono text-sm px-4 py-2 rounded-full
                      border transition-colors duration-150
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
                      ${
                        isSelected
                          ? "bg-[#C4694F] text-white border-[#C4694F]"
                          : "bg-warm-surface text-ink-200 border-warm-border hover:border-[#C4694F]"
                      }
                    `}
                  >
                    {chip.label}
                  </button>
                );
              }
            )}
          </div>
        </section>

        {/* Per-slot ratings */}
        <section className="space-y-3" aria-label="Rate your activities">
          {slots.map((slot) => (
            <SlotRating
              key={slot.id}
              slotId={slot.id}
              activityNodeId={slot.activityNodeId}
              activityName={slot.activityName}
              imageUrl={slot.imageUrl}
              initialRating={feedback[slot.id]?.rating ?? null}
              onRate={handleRate}
            />
          ))}
        </section>

        {/* Progress indicator */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-1 bg-ink-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all duration-300"
              style={{
                width: `${slots.length > 0 ? (ratedCount / slots.length) * 100 : 0}%`,
              }}
            />
          </div>
          <span className="font-dm-mono text-xs text-ink-400 shrink-0">
            {ratedCount}/{slots.length}
          </span>
        </div>

        {/* Free-text question */}
        <section className="space-y-3" aria-label="Additional feedback">
          <h2 className="font-sora text-lg font-semibold text-ink-100">
            What would you do differently?
          </h2>
          <textarea
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder="Anything you'd change, skip, or spend more time on..."
            maxLength={500}
            rows={3}
            className="
              w-full px-4 py-3 rounded-xl
              border border-ink-700 bg-surface
              font-dm-mono text-sm text-ink-100
              placeholder:text-ink-400 placeholder:opacity-50
              resize-none
              transition-colors duration-150
              focus:border-accent-muted focus:outline-none focus:ring-2 focus:ring-accent-muted/20
            "
          />
          <div className="text-right font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
            {freeText.length}/500
          </div>
        </section>

        {/* Submit */}
        <button
          type="button"
          onClick={handleSubmit}
          className="
            w-full py-3 rounded-xl
            bg-accent text-white
            font-sora font-semibold text-base
            hover:bg-accent/90 transition-colors duration-150
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
            disabled:opacity-40 disabled:cursor-not-allowed
          "
          disabled={ratedCount === 0}
        >
          Submit Reflection
        </button>
      </div>
    </AppShell>
  );
}
