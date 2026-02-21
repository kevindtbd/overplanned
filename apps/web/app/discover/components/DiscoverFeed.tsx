"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ActivityCard {
  id: string;
  name: string;
  city: string;
  category: string;
  subcategory: string | null;
  priceLevel: number | null;
  convergenceScore: number | null;
  authorityScore: number | null;
  descriptionShort: string | null;
  primaryImageUrl: string | null;
  neighborhood: string | null;
  vibeTags: { slug: string; name: string; score: number }[];
}

interface FeedSection {
  title: string;
  subtitle: string;
  items: ActivityCard[];
}

interface DiscoverFeedProps {
  city: string;
  userId: string;
  sessionId: string;
  hasSignals: boolean;
  confirmedCategories: string[];
  skippedCategories: string[];
  onCardSelect: (card: ActivityCard) => void;
  onShortlist: (card: ActivityCard, isShortlisted: boolean) => void;
  shortlistedIds: Set<string>;
}

// ---------------------------------------------------------------------------
// Category display helpers
// ---------------------------------------------------------------------------

const CATEGORY_LABELS: Record<string, string> = {
  dining: "Dining",
  drinks: "Drinks",
  culture: "Culture",
  outdoors: "Outdoors",
  active: "Active",
  entertainment: "Entertainment",
  shopping: "Shopping",
  experience: "Experiences",
  nightlife: "Nightlife",
  group_activity: "Group Activities",
  wellness: "Wellness",
};

const ALL_CATEGORIES = Object.keys(CATEGORY_LABELS);

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

function BookmarkIcon({ filled, className }: { filled?: boolean; className?: string }) {
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
      <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
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

function TrendingIcon({ className }: { className?: string }) {
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
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function StarIcon({ className }: { className?: string }) {
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
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Price dots
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
// Single activity card
// ---------------------------------------------------------------------------

function ActivityCardTile({
  card,
  position,
  userId,
  sessionId,
  onSelect,
  onShortlist,
  isShortlisted,
  impressionLogged,
}: {
  card: ActivityCard;
  position: number;
  userId: string;
  sessionId: string;
  onSelect: (card: ActivityCard) => void;
  onShortlist: (card: ActivityCard, shortlisted: boolean) => void;
  isShortlisted: boolean;
  impressionLogged: boolean;
}) {
  const tileRef = useRef<HTMLDivElement>(null);
  const loggedRef = useRef(impressionLogged);

  // Intersection observer for impression tracking
  useEffect(() => {
    if (loggedRef.current) return;
    const el = tileRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !loggedRef.current) {
          loggedRef.current = true;
          // Fire-and-forget impression event
          const clientEventId = `imp_${card.id}_${sessionId}_${position}`;
          fetch("/api/events/raw", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              userId,
              sessionId,
              activityNodeId: card.id,
              clientEventId,
              eventType: "discover_impression",
              intentClass: "implicit",
              surface: "discover_feed",
              payload: {
                position,
                category: card.category,
                convergenceScore: card.convergenceScore,
                authorityScore: card.authorityScore,
              },
            }),
          }).catch(() => {
            // Impression logging is best-effort — swallow errors
          });
        }
      },
      { threshold: 0.5 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [card.id, card.category, card.convergenceScore, card.authorityScore, position, userId, sessionId]);

  return (
    <div
      ref={tileRef}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-ink-700 bg-surface transition-all duration-200 hover:border-accent/40 hover:shadow-md"
      onClick={() => onSelect(card)}
    >
      {/* Image */}
      <div className="relative h-44 w-full overflow-hidden bg-ink-700">
        {card.primaryImageUrl ? (
          <img
            src={card.primaryImageUrl}
            alt={card.name}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <TagIcon className="h-8 w-8 text-ink-700" />
          </div>
        )}

        {/* Category pill overlay */}
        <div className="absolute left-2 top-2">
          <span className="inline-flex items-center rounded-full bg-black/60 px-2 py-0.5 font-dm-mono text-xs text-white backdrop-blur-sm">
            {CATEGORY_LABELS[card.category] ?? card.category}
          </span>
        </div>

        {/* Shortlist button */}
        <button
          className={`absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full backdrop-blur-sm transition-colors ${
            isShortlisted
              ? "bg-accent text-white"
              : "bg-black/40 text-white hover:bg-accent"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onShortlist(card, !isShortlisted);
          }}
          aria-label={isShortlisted ? "Remove from shortlist" : "Add to shortlist"}
        >
          <BookmarkIcon filled={isShortlisted} className="h-4 w-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col gap-1 p-3">
        <h3 className="font-sora text-sm font-semibold leading-snug text-primary line-clamp-2">
          {card.name}
        </h3>

        {card.neighborhood && (
          <div className="flex items-center gap-1 text-secondary">
            <MapPinIcon className="h-3 w-3 shrink-0" />
            <span className="font-dm-mono text-xs">{card.neighborhood}</span>
          </div>
        )}

        {card.descriptionShort && (
          <p className="mt-1 font-sora text-xs leading-relaxed text-secondary line-clamp-2">
            {card.descriptionShort}
          </p>
        )}

        {/* Footer row */}
        <div className="mt-auto flex items-center justify-between pt-2">
          <PriceDots level={card.priceLevel} />
          {card.convergenceScore != null && (
            <span className="font-dm-mono text-xs text-secondary">
              {Math.round(card.convergenceScore * 100)}% match
            </span>
          )}
        </div>

        {/* Vibe tags */}
        {card.vibeTags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.vibeTags.slice(0, 3).map((vt) => (
              <span
                key={vt.slug}
                className="rounded-full bg-accent/10 px-2 py-0.5 font-dm-mono text-xs text-accent"
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
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
        {icon}
      </div>
      <div>
        <h2 className="font-sora text-base font-semibold text-primary">{title}</h2>
        <p className="label-mono mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Category browsing strip
// ---------------------------------------------------------------------------

function CategoryStrip({
  selectedCategory,
  onSelect,
}: {
  selectedCategory: string | null;
  onSelect: (cat: string | null) => void;
}) {
  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
      <button
        onClick={() => onSelect(null)}
        className={`shrink-0 rounded-full border px-3 py-1.5 font-dm-mono text-xs transition-colors ${
          selectedCategory === null
            ? "border-accent bg-accent text-white"
            : "border-ink-700 bg-surface text-secondary hover:border-accent/40 hover:text-primary"
        }`}
      >
        All
      </button>
      {ALL_CATEGORIES.map((cat) => (
        <button
          key={cat}
          onClick={() => onSelect(cat === selectedCategory ? null : cat)}
          className={`shrink-0 rounded-full border px-3 py-1.5 font-dm-mono text-xs transition-colors ${
            selectedCategory === cat
              ? "border-accent bg-accent text-white"
              : "border-ink-700 bg-surface text-secondary hover:border-accent/40 hover:text-primary"
          }`}
        >
          {CATEGORY_LABELS[cat]}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-ink-700 bg-surface">
      <div className="h-44 animate-pulse bg-ink-700" />
      <div className="space-y-2 p-3">
        <div className="h-4 w-3/4 animate-pulse rounded bg-ink-700" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-ink-700" />
        <div className="h-3 w-full animate-pulse rounded bg-ink-700" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DiscoverFeed
// ---------------------------------------------------------------------------

export function DiscoverFeed({
  city,
  userId,
  sessionId,
  hasSignals,
  confirmedCategories,
  skippedCategories,
  onCardSelect,
  onShortlist,
  shortlistedIds,
}: DiscoverFeedProps) {
  const [sections, setSections] = useState<FeedSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loggedImpressions, setLoggedImpressions] = useState<Set<string>>(new Set());

  // Build rules-based personalized feed from raw ActivityNodes
  const buildSections = useCallback(
    (raw: ActivityCard[]): FeedSection[] => {
      if (!hasSignals) {
        // Cold start — sort trending first, then editorial picks, then by category
        const trending = [...raw]
          .filter((n) => n.convergenceScore != null)
          .sort((a, b) => (b.convergenceScore ?? 0) - (a.convergenceScore ?? 0))
          .slice(0, 8);

        const editorial = [...raw]
          .filter((n) => n.authorityScore != null && !trending.find((t) => t.id === n.id))
          .sort((a, b) => (b.authorityScore ?? 0) - (a.authorityScore ?? 0))
          .slice(0, 6);

        return [
          {
            title: `Trending in ${city}`,
            subtitle: "highest convergence from local signals",
            items: trending,
          },
          {
            title: "Editorial picks",
            subtitle: "highest authority from curated sources",
            items: editorial,
          },
        ];
      }

      // Returning user — boost confirmed categories, demote skipped
      const boostedCats = new Set(confirmedCategories);
      const demotedCats = new Set(skippedCategories);

      const scored = raw.map((n) => {
        let score = n.convergenceScore ?? 0;
        if (boostedCats.has(n.category)) score += 0.3;
        if (demotedCats.has(n.category)) score -= 0.5;
        return { ...n, _personalScore: score };
      });

      const forYou = scored
        .filter((n) => !demotedCats.has(n.category))
        .sort((a, b) => b._personalScore - a._personalScore)
        .slice(0, 10);

      const explore = scored
        .filter((n) => !forYou.find((f) => f.id === n.id) && !demotedCats.has(n.category))
        .sort((a, b) => (b.authorityScore ?? 0) - (a.authorityScore ?? 0))
        .slice(0, 8);

      return [
        {
          title: "For you",
          subtitle: "based on your travel patterns",
          items: forYou,
        },
        {
          title: "Worth exploring",
          subtitle: "highly rated by local sources",
          items: explore,
        },
      ];
    },
    [city, hasSignals, confirmedCategories, skippedCategories]
  );

  useEffect(() => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({ city, limit: "60" });
    if (selectedCategory) params.set("category", selectedCategory);

    fetch(`/api/discover/feed?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Feed fetch failed: ${r.status}`);
        return r.json();
      })
      .then((data: { nodes: ActivityCard[] }) => {
        setSections(buildSections(data.nodes));
      })
      .catch((err: Error) => {
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }, [city, selectedCategory, buildSections]);

  const markImpression = useCallback((id: string) => {
    setLoggedImpressions((prev) => new Set(prev).add(id));
  }, []);

  return (
    <div className="space-y-8">
      {/* Category browsing strip */}
      <div className="sticky top-14 z-10 -mx-4 bg-base/90 px-4 py-3 backdrop-blur-sm">
        <CategoryStrip
          selectedCategory={selectedCategory}
          onSelect={setSelectedCategory}
        />
      </div>

      {loading && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-ink-700 bg-surface p-6 text-center">
          <p className="font-dm-mono text-xs text-secondary">Could not load feed. Try again later.</p>
        </div>
      )}

      {!loading &&
        !error &&
        sections.map((section) => (
          <section key={section.title}>
            <SectionHeader
              icon={
                section.title.startsWith("Trending") ? (
                  <TrendingIcon className="h-4 w-4" />
                ) : section.title.startsWith("Editorial") ? (
                  <StarIcon className="h-4 w-4" />
                ) : (
                  <TagIcon className="h-4 w-4" />
                )
              }
              title={section.title}
              subtitle={section.subtitle}
            />
            {section.items.length === 0 ? (
              <p className="font-dm-mono text-xs text-secondary">Nothing here yet.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {section.items.map((card, position) => (
                  <ActivityCardTile
                    key={card.id}
                    card={card}
                    position={position}
                    userId={userId}
                    sessionId={sessionId}
                    onSelect={onCardSelect}
                    onShortlist={(c, shortlisted) => {
                      onShortlist(c, shortlisted);
                    }}
                    isShortlisted={shortlistedIds.has(card.id)}
                    impressionLogged={loggedImpressions.has(card.id)}
                  />
                ))}
              </div>
            )}
          </section>
        ))}
    </div>
  );
}
