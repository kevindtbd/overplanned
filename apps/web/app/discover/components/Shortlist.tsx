"use client";

import { useCallback } from "react";
import type { ActivityCard } from "./DiscoverFeed";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ShortlistProps {
  items: ActivityCard[];
  userId: string;
  sessionId: string;
  tripId?: string;
  onRemove: (card: ActivityCard) => void;
  onAddToTrip?: (card: ActivityCard) => void;
}

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

function BookmarkIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      stroke="currentColor"
      strokeWidth={0}
    >
      <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
    </svg>
  );
}

function XIcon({ className }: { className?: string }) {
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
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
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
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function TagIcon({ className }: { className?: string }) {
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
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Signal helpers
// ---------------------------------------------------------------------------

async function writeShortlistSignal(
  action: "shortlist_add" | "shortlist_remove",
  card: ActivityCard,
  userId: string,
  sessionId: string,
  tripId: string | undefined
) {
  const clientEventId = `sl_${action}_${card.id}_${Date.now()}`;

  // RawEvent
  fetch("/api/events/raw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      sessionId,
      tripId: tripId ?? null,
      activityNodeId: card.id,
      clientEventId,
      eventType: action,
      intentClass: "explicit",
      surface: "shortlist",
      payload: { category: card.category },
    }),
  }).catch(() => {});

  // BehavioralSignal
  const signalType =
    action === "shortlist_add" ? "discover_shortlist" : "discover_remove";

  fetch("/api/signals/behavioral", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      tripId: tripId ?? null,
      activityNodeId: card.id,
      signalType,
      signalValue: action === "shortlist_add" ? 1.0 : -0.5,
      tripPhase: "pre_trip",
      rawAction: action,
    }),
  }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Price display
// ---------------------------------------------------------------------------

function PriceDots({ level }: { level: number | null }) {
  if (!level) return null;
  return (
    <span className="font-dm-mono text-xs text-secondary">
      {"$".repeat(level)}
      <span className="opacity-30">{"$".repeat(Math.max(0, 4 - level))}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Shortlist item row
// ---------------------------------------------------------------------------

function ShortlistItem({
  card,
  onRemove,
  onAddToTrip,
}: {
  card: ActivityCard;
  onRemove: (card: ActivityCard) => void;
  onAddToTrip?: (card: ActivityCard) => void;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-warm bg-warm-surface p-3 transition-colors hover:border-terracotta/30">
      {/* Thumbnail */}
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-warm-border">
        {card.primaryImageUrl ? (
          <img
            src={card.primaryImageUrl}
            alt={card.name}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <TagIcon className="h-5 w-5 text-warm-border" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <h4 className="font-sora text-sm font-semibold text-primary line-clamp-1">
          {card.name}
        </h4>

        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {card.neighborhood && (
            <div className="flex items-center gap-1 text-secondary">
              <MapPinIcon className="h-3 w-3 shrink-0" />
              <span className="font-dm-mono text-xs">{card.neighborhood}</span>
            </div>
          )}
          <span className="font-dm-mono text-xs text-secondary">{card.category}</span>
          <PriceDots level={card.priceLevel} />
        </div>

        {/* Vibe tags */}
        {card.vibeTags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {card.vibeTags.slice(0, 3).map((vt) => (
              <span
                key={vt.slug}
                className="rounded-full bg-terracotta/10 px-1.5 py-0.5 font-dm-mono text-xs text-terracotta"
              >
                {vt.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <button
          onClick={() => onRemove(card)}
          className="flex h-7 w-7 items-center justify-center rounded-full text-secondary transition-colors hover:bg-warm-border hover:text-primary"
          aria-label={`Remove ${card.name} from shortlist`}
        >
          <XIcon className="h-4 w-4" />
        </button>

        {onAddToTrip && (
          <button
            onClick={() => onAddToTrip(card)}
            className="flex h-7 w-7 items-center justify-center rounded-full bg-terracotta/10 text-terracotta transition-colors hover:bg-terracotta hover:text-white"
            aria-label={`Add ${card.name} to trip`}
          >
            <PlusIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shortlist component
// ---------------------------------------------------------------------------

export function Shortlist({
  items,
  userId,
  sessionId,
  tripId,
  onRemove,
  onAddToTrip,
}: ShortlistProps) {
  const handleRemove = useCallback(
    (card: ActivityCard) => {
      writeShortlistSignal("shortlist_remove", card, userId, sessionId, tripId);
      onRemove(card);
    },
    [userId, sessionId, tripId, onRemove]
  );

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-terracotta/10">
          <BookmarkIcon className="h-5 w-5 text-terracotta" />
        </div>
        <h3 className="font-sora text-base font-semibold text-primary">
          Your shortlist is empty
        </h3>
        <p className="label-mono mt-1">
          save places you want to visit
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookmarkIcon className="h-4 w-4 text-terracotta" />
          <h2 className="font-sora text-base font-semibold text-primary">Shortlist</h2>
          <span className="rounded-full bg-terracotta/10 px-2 py-0.5 font-dm-mono text-xs text-terracotta">
            {items.length}
          </span>
        </div>

        {onAddToTrip && (
          <p className="label-mono">tap + to add to trip</p>
        )}
      </div>

      {/* Items */}
      <div className="space-y-2">
        {items.map((card) => (
          <ShortlistItem
            key={card.id}
            card={card}
            onRemove={handleRemove}
            onAddToTrip={onAddToTrip}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hook — manages shortlist state + signals
// ---------------------------------------------------------------------------

export function useShortlist(
  userId: string,
  sessionId: string,
  tripId?: string
) {
  // We rely on parent state, but expose the signal writer for use
  // by DiscoverFeed/SwipeDeck callers
  const add = useCallback(
    (card: ActivityCard) => {
      writeShortlistSignal("shortlist_add", card, userId, sessionId, tripId);
    },
    [userId, sessionId, tripId]
  );

  const remove = useCallback(
    (card: ActivityCard) => {
      writeShortlistSignal("shortlist_remove", card, userId, sessionId, tripId);
    },
    [userId, sessionId, tripId]
  );

  return { add, remove };
}
