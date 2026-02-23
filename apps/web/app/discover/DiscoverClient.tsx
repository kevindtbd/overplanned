"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { DiscoverFeed, type ActivityCard } from "./components/DiscoverFeed";
import { SwipeDeck } from "./components/SwipeDeck";
import { Shortlist, useShortlist } from "./components/Shortlist";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViewMode = "feed" | "swipe" | "shortlist";

interface DiscoverClientProps {
  userId: string;
  city: string;
  tripId?: string;
  day?: number;
}

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

function GridIcon({ className }: { className?: string }) {
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
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  );
}

function LayersIcon({ className }: { className?: string }) {
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
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function BookmarkIcon({ className }: { className?: string }) {
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
      <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
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

// ---------------------------------------------------------------------------
// Session ID (stable per client session, not persisted)
// ---------------------------------------------------------------------------

function useSessionId(): string {
  return useMemo(() => {
    if (typeof crypto !== "undefined") {
      return crypto.randomUUID();
    }
    return `sess_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  }, []);
}

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

function TabBar({
  mode,
  shortlistCount,
  onChange,
}: {
  mode: ViewMode;
  shortlistCount: number;
  onChange: (m: ViewMode) => void;
}) {
  const tabs: { key: ViewMode; label: string; icon: React.ReactNode }[] = [
    {
      key: "feed",
      label: "Browse",
      icon: <GridIcon className="h-4 w-4" />,
    },
    {
      key: "swipe",
      label: "Swipe",
      icon: <LayersIcon className="h-4 w-4" />,
    },
    {
      key: "shortlist",
      label: "Saved",
      icon: <BookmarkIcon className="h-4 w-4" />,
    },
  ];

  return (
    <div className="flex gap-1 rounded-xl bg-surface p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 font-dm-mono text-xs transition-colors ${
            mode === tab.key
              ? "bg-accent text-white shadow-sm"
              : "text-secondary hover:text-primary"
          }`}
        >
          {tab.icon}
          <span>{tab.label}</span>
          {tab.key === "shortlist" && shortlistCount > 0 && (
            <span
              className={`flex h-4 min-w-4 items-center justify-center rounded-full px-1 font-dm-mono text-xs ${
                mode === "shortlist"
                  ? "bg-white/30 text-white"
                  : "bg-accent text-white"
              }`}
            >
              {shortlistCount}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main client component
// ---------------------------------------------------------------------------

export default function DiscoverClient({
  userId,
  city,
  tripId,
  day,
}: DiscoverClientProps) {
  const sessionId = useSessionId();

  const [viewMode, setViewMode] = useState<ViewMode>("feed");
  const [shortlist, setShortlist] = useState<ActivityCard[]>([]);
  const [shortlistIds, setShortlistIds] = useState<Set<string>>(new Set());
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Swipe deck uses a snapshot of the current feed cards
  const [swipeDeckCards, setSwipeDeckCards] = useState<ActivityCard[]>([]);
  const [swipeDeckReady, setSwipeDeckReady] = useState(false);

  const { add: signalAdd, remove: signalRemove } = useShortlist(userId, sessionId, tripId);

  // Behavioral signals context — cold start heuristic: no signals until user has swiped
  const hasSignals = shortlist.length > 0 || swipeDeckCards.length > 0;

  // For personalization: track categories based on shortlist + swipe rights
  const confirmedCategories = useMemo(() => {
    const cats = shortlist.map((c) => c.category);
    return [...new Set(cats)];
  }, [shortlist]);

  // Track explicitly skipped (swipe left) categories in a session
  const [skippedCategories, setSkippedCategories] = useState<string[]>([]);

  const handleShortlistAdd = useCallback(
    (card: ActivityCard) => {
      if (shortlistIds.has(card.id)) return;
      signalAdd(card);
      setShortlist((prev) => [card, ...prev]);
      setShortlistIds((prev) => new Set(prev).add(card.id));
    },
    [shortlistIds, signalAdd]
  );

  const handleShortlistRemove = useCallback(
    (card: ActivityCard) => {
      signalRemove(card);
      setShortlist((prev) => prev.filter((c) => c.id !== card.id));
      setShortlistIds((prev) => {
        const next = new Set(prev);
        next.delete(card.id);
        return next;
      });
    },
    [signalRemove]
  );

  const handleCardSelect = useCallback((card: ActivityCard) => {
    // For now open shortlist CTA — in future routes to /discover/[slug]
    handleShortlistAdd(card);
  }, [handleShortlistAdd]);

  const handleFeedShortlist = useCallback(
    (card: ActivityCard, isShortlisted: boolean) => {
      if (isShortlisted) {
        handleShortlistAdd(card);
      } else {
        handleShortlistRemove(card);
      }
    },
    [handleShortlistAdd, handleShortlistRemove]
  );

  const handleSwipeRight = useCallback(
    (card: ActivityCard) => {
      handleShortlistAdd(card);
    },
    [handleShortlistAdd]
  );

  const handleSwipeLeft = useCallback((card: ActivityCard) => {
    setSkippedCategories((prev) =>
      prev.includes(card.category) ? prev : [...prev, card.category]
    );
  }, []);

  const handleSwipeEmpty = useCallback(() => {
    setSwipeDeckReady(false);
  }, []);

  // When switching to swipe mode, load cards from the API
  const handleModeChange = useCallback(
    (mode: ViewMode) => {
      setViewMode(mode);
      if (mode === "swipe" && !swipeDeckReady) {
        fetch(`/api/discover/feed?city=${encodeURIComponent(city)}&limit=30`)
          .then((r) => r.json())
          .then((data: { nodes: ActivityCard[] }) => {
            // Exclude already shortlisted cards
            const fresh = data.nodes.filter((n) => !shortlistIds.has(n.id));
            setSwipeDeckCards(fresh);
            setSwipeDeckReady(true);
          })
          .catch(() => {
            setSwipeDeckCards([]);
            setSwipeDeckReady(true);
          });
      }
    },
    [city, shortlistIds, swipeDeckReady]
  );

  return (
    <div className="min-h-screen bg-base">
      {/* Top bar */}
      <div className="sticky top-0 z-20 border-b border-ink-700 bg-base/90 backdrop-blur-sm">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => window.history.back()}
              className="flex h-8 w-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-surface hover:text-primary"
              aria-label="Go back"
            >
              <ArrowLeftIcon className="h-4 w-4" />
            </button>
            <div className="flex-1">
              <h1 className="font-sora text-base font-semibold text-primary">Discover</h1>
              <p className="label-mono">{city}</p>
            </div>
            {tripId && (
              <Link
                href={`/trip/${tripId}`}
                className="inline-flex items-center gap-1.5 font-dm-mono text-xs text-ink-400 uppercase tracking-wider hover:text-accent transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to trip
              </Link>
            )}
          </div>

          <div className="mt-3">
            <TabBar
              mode={viewMode}
              shortlistCount={shortlist.length}
              onChange={handleModeChange}
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-2xl px-4 py-5">
        {viewMode === "feed" && (
          <DiscoverFeed
            city={city}
            userId={userId}
            sessionId={sessionId}
            hasSignals={hasSignals}
            confirmedCategories={confirmedCategories}
            skippedCategories={skippedCategories}
            onCardSelect={handleCardSelect}
            onShortlist={handleFeedShortlist}
            shortlistedIds={shortlistIds}
          />
        )}

        {viewMode === "swipe" && (
          <div className="py-4">
            {!swipeDeckReady ? (
              <div className="flex flex-col items-center py-16 gap-3">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-ink-700 border-t-accent" />
                <p className="label-mono">Loading cards...</p>
              </div>
            ) : (
              <SwipeDeck
                cards={swipeDeckCards}
                userId={userId}
                sessionId={sessionId}
                tripId={tripId}
                onSwipeRight={handleSwipeRight}
                onSwipeLeft={handleSwipeLeft}
                onEmpty={handleSwipeEmpty}
              />
            )}
          </div>
        )}

        {viewMode === "shortlist" && (
          <Shortlist
            items={shortlist}
            userId={userId}
            sessionId={sessionId}
            tripId={tripId}
            onRemove={handleShortlistRemove}
            onAddToTrip={tripId ? async (card) => {
              try {
                const res = await fetch(`/api/trips/${tripId}/slots`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ activityNodeId: card.id, dayNumber: day ?? 1 }),
                });
                if (res.ok) {
                  // Remove from shortlist after successfully adding to trip
                  handleShortlistRemove(card);
                  setToastMessage(`Added to Day ${day ?? 1}`);
                  setTimeout(() => setToastMessage(null), 5000);
                } else {
                  const data = await res.json().catch(() => ({}));
                  console.error("Failed to add to trip:", data.error);
                }
              } catch (err) {
                console.error("Failed to add to trip:", err);
              }
            } : undefined}
          />
        )}
      </div>

      {/* Success toast */}
      {toastMessage && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-40 rounded-xl bg-warm-surface border border-warm-border px-4 py-3 shadow-lg font-sora text-sm text-ink-100 flex items-center gap-3">
          <span>{toastMessage}</span>
          {tripId && (
            <Link href={`/trip/${tripId}`} className="font-medium text-accent hover:text-accent/80 whitespace-nowrap">
              Back to trip
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
