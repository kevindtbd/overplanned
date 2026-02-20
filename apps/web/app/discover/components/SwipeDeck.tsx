"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { ActivityCard } from "./DiscoverFeed";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SwipeDeckProps {
  cards: ActivityCard[];
  userId: string;
  sessionId: string;
  tripId?: string;
  onSwipeRight: (card: ActivityCard) => void;
  onSwipeLeft: (card: ActivityCard) => void;
  onEmpty: () => void;
}

type SwipeDirection = "left" | "right" | null;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SWIPE_THRESHOLD = 80; // px horizontal delta to register swipe
const ROTATION_FACTOR = 0.08; // degrees per px

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

function XIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function HeartIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
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
// Signal writer
// ---------------------------------------------------------------------------

async function writeSwipeSignal(
  direction: "right" | "left",
  card: ActivityCard,
  userId: string,
  sessionId: string,
  tripId: string | undefined
) {
  const signalType =
    direction === "right" ? "discover_swipe_right" : "discover_swipe_left";

  const clientEventId = `swipe_${direction}_${card.id}_${Date.now()}`;

  // Write RawEvent (best-effort)
  fetch("/api/events/raw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      sessionId,
      tripId: tripId ?? null,
      activityNodeId: card.id,
      clientEventId,
      eventType: signalType,
      intentClass: "explicit",
      surface: "swipe_deck",
      payload: { category: card.category, direction },
    }),
  }).catch(() => {});

  // Write BehavioralSignal via Next.js API route
  fetch("/api/signals/behavioral", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      tripId: tripId ?? null,
      activityNodeId: card.id,
      signalType,
      signalValue: direction === "right" ? 1.0 : -1.0,
      tripPhase: "pre_trip",
      rawAction: `swipe_${direction}`,
    }),
  }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Single draggable card
// ---------------------------------------------------------------------------

function DraggableCard({
  card,
  onSwipe,
  isTop,
  stackOffset,
}: {
  card: ActivityCard;
  onSwipe: (direction: "left" | "right") => void;
  isTop: boolean;
  stackOffset: number; // 0 = top card, 1 = second, etc.
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const currentX = useRef(0);
  const isDragging = useRef(false);
  const [dragDelta, setDragDelta] = useState(0);
  const [isAnimatingOut, setIsAnimatingOut] = useState<SwipeDirection>(null);

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isTop) return;
    isDragging.current = true;
    startX.current = e.clientX;
    cardRef.current?.setPointerCapture(e.pointerId);
  }, [isTop]);

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isDragging.current || !isTop) return;
    currentX.current = e.clientX - startX.current;
    setDragDelta(currentX.current);
  }, [isTop]);

  const onPointerUp = useCallback(() => {
    if (!isDragging.current || !isTop) return;
    isDragging.current = false;

    const delta = currentX.current;
    if (Math.abs(delta) >= SWIPE_THRESHOLD) {
      const dir = delta > 0 ? "right" : "left";
      setIsAnimatingOut(dir);
      setTimeout(() => onSwipe(dir), 300);
    } else {
      // Snap back
      setDragDelta(0);
      currentX.current = 0;
    }
  }, [isTop, onSwipe]);

  // Compute transform
  const rotation = isTop ? dragDelta * ROTATION_FACTOR : 0;
  const translateX = isAnimatingOut
    ? isAnimatingOut === "right"
      ? "120vw"
      : "-120vw"
    : isTop
    ? `${dragDelta}px`
    : "0px";

  const scale = isTop ? 1 : 1 - stackOffset * 0.04;
  const translateY = isTop ? "0px" : `${stackOffset * 12}px`;
  const opacity = isAnimatingOut ? 0 : 1;

  // Decision overlay
  const overlayOpacity = isTop ? Math.min(Math.abs(dragDelta) / SWIPE_THRESHOLD, 1) : 0;
  const isRight = dragDelta > 0;

  return (
    <div
      ref={cardRef}
      className="absolute inset-0 select-none touch-none overflow-hidden rounded-2xl border border-warm bg-warm-surface shadow-lg"
      style={{
        transform: `translateX(${translateX}) translateY(${translateY}) rotate(${rotation}deg) scale(${scale})`,
        opacity,
        transition: isDragging.current ? "none" : "transform 0.3s ease, opacity 0.3s ease",
        zIndex: 10 - stackOffset,
        cursor: isTop ? "grab" : "default",
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {/* Image */}
      <div className="relative h-64 w-full overflow-hidden bg-warm-border">
        {card.primaryImageUrl ? (
          <img
            src={card.primaryImageUrl}
            alt={card.name}
            className="h-full w-full object-cover"
            draggable={false}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <TagIcon className="h-10 w-10 text-warm-border" />
          </div>
        )}

        {/* Category pill */}
        <div className="absolute left-3 top-3">
          <span className="rounded-full bg-black/60 px-2.5 py-1 font-dm-mono text-xs text-white backdrop-blur-sm">
            {card.category}
          </span>
        </div>

        {/* Swipe decision overlays */}
        {isTop && (
          <>
            <div
              className="absolute inset-0 flex items-center justify-start pl-6"
              style={{ opacity: isRight ? 0 : overlayOpacity }}
            >
              <div className="rounded-xl border-4 border-red-400 px-3 py-1">
                <span className="font-sora text-2xl font-bold text-red-400">NOPE</span>
              </div>
            </div>
            <div
              className="absolute inset-0 flex items-center justify-end pr-6"
              style={{ opacity: isRight ? overlayOpacity : 0 }}
            >
              <div className="rounded-xl border-4 border-emerald-400 px-3 py-1">
                <span className="font-sora text-2xl font-bold text-emerald-400">YES</span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Card content */}
      <div className="p-4">
        <h3 className="font-sora text-lg font-semibold text-primary">{card.name}</h3>

        {card.neighborhood && (
          <div className="mt-1 flex items-center gap-1 text-secondary">
            <MapPinIcon className="h-3.5 w-3.5" />
            <span className="font-dm-mono text-xs">{card.neighborhood}</span>
          </div>
        )}

        {card.descriptionShort && (
          <p className="mt-2 font-sora text-sm leading-relaxed text-secondary line-clamp-3">
            {card.descriptionShort}
          </p>
        )}

        {card.vibeTags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {card.vibeTags.slice(0, 4).map((vt) => (
              <span
                key={vt.slug}
                className="rounded-full bg-terracotta/10 px-2 py-0.5 font-dm-mono text-xs text-terracotta"
              >
                {vt.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SwipeDeck
// ---------------------------------------------------------------------------

export function SwipeDeck({
  cards,
  userId,
  sessionId,
  tripId,
  onSwipeRight,
  onSwipeLeft,
  onEmpty,
}: SwipeDeckProps) {
  const [deck, setDeck] = useState<ActivityCard[]>(cards);
  const [swipedCount, setSwipedCount] = useState(0);

  // Sync external cards updates (e.g., when feed loads more)
  useEffect(() => {
    setDeck(cards);
  }, [cards]);

  const handleSwipe = useCallback(
    (direction: "left" | "right") => {
      setDeck((prev) => {
        const [top, ...rest] = prev;
        if (!top) return prev;

        // Write signal async
        writeSwipeSignal(direction, top, userId, sessionId, tripId);

        if (direction === "right") {
          onSwipeRight(top);
        } else {
          onSwipeLeft(top);
        }

        if (rest.length === 0) {
          // Notify parent after state update
          setTimeout(onEmpty, 50);
        }

        return rest;
      });
      setSwipedCount((c) => c + 1);
    },
    [userId, sessionId, tripId, onSwipeRight, onSwipeLeft, onEmpty]
  );

  // Button-driven swipe
  const handleButtonSwipe = useCallback(
    (direction: "left" | "right") => {
      if (deck.length === 0) return;
      handleSwipe(direction);
    },
    [deck, handleSwipe]
  );

  if (deck.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-terracotta/10">
          <HeartIcon className="h-6 w-6 text-terracotta" />
        </div>
        <h3 className="font-sora text-lg font-semibold text-primary">
          You&apos;ve seen everything
        </h3>
        <p className="label-mono mt-1">
          {swipedCount} places reviewed &middot; check your shortlist
        </p>
      </div>
    );
  }

  // Render top 3 cards for stacking effect
  const visibleCards = deck.slice(0, 3);

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Progress */}
      <div className="label-mono">
        {swipedCount} reviewed &middot; {deck.length} remaining
      </div>

      {/* Card stack */}
      <div className="relative h-[480px] w-full max-w-sm">
        {[...visibleCards].reverse().map((card, reversedIdx) => {
          const stackOffset = visibleCards.length - 1 - reversedIdx;
          return (
            <DraggableCard
              key={card.id}
              card={card}
              onSwipe={handleSwipe}
              isTop={stackOffset === 0}
              stackOffset={stackOffset}
            />
          );
        })}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-8">
        <button
          onClick={() => handleButtonSwipe("left")}
          className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-red-300 bg-warm-surface text-red-400 shadow-sm transition-all hover:border-red-400 hover:bg-red-50 hover:shadow-md active:scale-95"
          aria-label="Not interested"
        >
          <XIcon className="h-6 w-6" />
        </button>

        <button
          onClick={() => handleButtonSwipe("right")}
          className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-emerald-300 bg-warm-surface text-emerald-500 shadow-sm transition-all hover:border-emerald-400 hover:bg-emerald-50 hover:shadow-md active:scale-95"
          aria-label="Interested"
        >
          <HeartIcon className="h-6 w-6" />
        </button>
      </div>

      {/* Gesture hint */}
      <p className="label-mono text-center">
        swipe right to save &middot; swipe left to skip
      </p>
    </div>
  );
}
