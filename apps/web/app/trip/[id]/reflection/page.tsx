"use client";

// Post-Trip Reflection Page — /trip/[id]/reflection
// Per-slot highlight rating (loved / skipped / missed) + single feedback question.
// Writes BehavioralSignals: post_loved, post_skipped, post_missed, post_disliked.
// Feedback can override slot status (completed → skipped if user says they didn't go).

import { useState, useCallback, useMemo } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { SlotRating, type SlotRatingEvent, type SlotRatingValue } from "./components/SlotRating";

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

// ---------- Mock data (replaced by API/Prisma in production) ----------

const MOCK_TRIP = {
  id: "trip-001",
  destination: "Tokyo",
  city: "Tokyo",
  country: "Japan",
  completedAt: "2026-03-19T23:59:00+09:00",
  totalDays: 5,
};

const MOCK_SLOTS: ReflectionSlot[] = [
  {
    id: "slot-001",
    activityName: "Tsukiji Outer Market",
    imageUrl: "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=800&q=80",
    activityNodeId: "node-001",
    originalStatus: "completed",
  },
  {
    id: "slot-002",
    activityName: "TeamLab Borderless",
    imageUrl: "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=800&q=80",
    activityNodeId: "node-002",
    originalStatus: "completed",
  },
  {
    id: "slot-003",
    activityName: "Shibuya Evening Walk",
    imageUrl: "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=800&q=80",
    activityNodeId: "node-003",
    originalStatus: "skipped",
  },
  {
    id: "slot-004",
    activityName: "Omoide Yokocho",
    imageUrl: "https://images.unsplash.com/photo-1554797589-7241bb691973?w=800&q=80",
    activityNodeId: "node-004",
    originalStatus: "completed",
  },
  {
    id: "slot-005",
    activityName: "Meiji Shrine Morning",
    imageUrl: "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=800&q=80",
    activityNodeId: "node-005",
    originalStatus: "completed",
  },
  {
    id: "slot-006",
    activityName: "Harajuku Backstreets",
    imageUrl: "https://images.unsplash.com/photo-1480796927426-f609979314bd?w=800&q=80",
    activityNodeId: "node-006",
    originalStatus: "completed",
  },
  {
    id: "slot-007",
    activityName: "Akihabara Deep Dive",
    activityNodeId: "node-007",
    originalStatus: "skipped",
  },
  {
    id: "slot-008",
    activityName: "Shinjuku Gyoen Farewell Walk",
    imageUrl: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=800&q=80",
    activityNodeId: "node-008",
    originalStatus: "completed",
  },
];

// ---------- Signal helper ----------

async function sendBehavioralSignal(payload: {
  tripId: string;
  slotId: string;
  activityNodeId?: string;
  signalType: string;
  signalValue: number;
  rawAction: string;
}) {
  try {
    await fetch("/api/signals/behavioral", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        tripPhase: "post_trip",
      }),
    });
  } catch (err) {
    console.error("[reflection] Failed to send signal:", err);
  }
}

// ---------- Component ----------

export default function ReflectionPage({
  params,
}: {
  params: { id: string };
}) {
  const trip = MOCK_TRIP;
  const slots = MOCK_SLOTS;

  const [feedback, setFeedback] = useState<Record<string, SlotFeedback>>({});
  const [freeText, setFreeText] = useState("");
  const [submitted, setSubmitted] = useState(false);

  // Track how many slots have been rated
  const ratedCount = useMemo(
    () => Object.values(feedback).filter((f) => f.rating !== null).length,
    [feedback]
  );

  const handleRate = useCallback(
    (event: SlotRatingEvent) => {
      // Update local state
      const prev = feedback[event.slotId];
      const isSkippedRating = event.rating === "skipped";

      // Find the original slot to check if this overrides status
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

      // Fire behavioral signal
      sendBehavioralSignal({
        tripId: params.id,
        slotId: event.slotId,
        activityNodeId: event.activityNodeId,
        signalType: event.signalType,
        signalValue: event.signalValue,
        rawAction: `reflection_${event.rating}`,
      });

      // If user marks "skipped" on a completed slot, also fire override signal
      if (overridesStatus) {
        sendBehavioralSignal({
          tripId: params.id,
          slotId: event.slotId,
          activityNodeId: event.activityNodeId,
          signalType: "post_skipped",
          signalValue: -1.0,
          rawAction: "reflection_status_override_completed_to_skipped",
        });
      }
    },
    [feedback, slots, params.id]
  );

  const handleSubmit = useCallback(async () => {
    if (submitted) return;
    setSubmitted(true);

    // Send free-text as a post_disliked signal if non-empty
    // (captures "what would you do differently" as negative-signal data)
    if (freeText.trim()) {
      await sendBehavioralSignal({
        tripId: params.id,
        slotId: "", // trip-level feedback, no specific slot
        signalType: "post_disliked",
        signalValue: 0,
        rawAction: `reflection_freetext:${freeText.trim().slice(0, 500)}`,
      });
    }

    // In production: POST to /api/trips/[id]/reflection with full feedback payload
    console.log("[reflection] Submitted:", {
      tripId: params.id,
      feedback,
      freeText: freeText.trim(),
    });
  }, [params.id, feedback, freeText, submitted]);

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
          <h1 className="font-sora text-2xl font-bold text-warm-text-primary">
            Thanks for reflecting
          </h1>
          <p className="font-dm-mono text-sm text-warm-text-secondary max-w-sm">
            Your feedback helps us learn what you love so future trips feel even
            more you.
          </p>
          <a
            href={`/trip/${params.id}`}
            className="
              inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
              bg-terracotta-500 text-white
              font-dm-mono text-sm uppercase tracking-wider
              hover:bg-terracotta-600 transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400 focus-visible:ring-offset-2
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
          <h1 className="font-sora text-2xl sm:text-3xl font-bold text-warm-text-primary">
            How was {trip.destination}?
          </h1>
          <p className="font-dm-mono text-xs text-warm-text-secondary uppercase tracking-wider">
            {trip.totalDays} days -- {slots.length} activities -- Tap to rate
            each highlight
          </p>
        </header>

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
          <div className="flex-1 h-1 bg-warm-border rounded-full overflow-hidden">
            <div
              className="h-full bg-terracotta-500 rounded-full transition-all duration-300"
              style={{
                width: `${slots.length > 0 ? (ratedCount / slots.length) * 100 : 0}%`,
              }}
            />
          </div>
          <span className="font-dm-mono text-xs text-warm-text-secondary shrink-0">
            {ratedCount}/{slots.length}
          </span>
        </div>

        {/* Free-text question */}
        <section className="space-y-3" aria-label="Additional feedback">
          <h2 className="font-sora text-lg font-semibold text-warm-text-primary">
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
              border border-warm-border bg-warm-surface
              font-dm-mono text-sm text-warm-text-primary
              placeholder:text-warm-text-secondary placeholder:opacity-50
              resize-none
              transition-colors duration-150
              focus:border-terracotta-400 focus:outline-none focus:ring-2 focus:ring-terracotta-400/20
            "
          />
          <div className="text-right font-dm-mono text-[10px] text-warm-text-secondary uppercase tracking-wider">
            {freeText.length}/500
          </div>
        </section>

        {/* Submit */}
        <button
          type="button"
          onClick={handleSubmit}
          className="
            w-full py-3 rounded-xl
            bg-terracotta-500 text-white
            font-sora font-semibold text-base
            hover:bg-terracotta-600 transition-colors duration-150
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400 focus-visible:ring-offset-2
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
