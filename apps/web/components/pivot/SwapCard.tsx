"use client";

// SwapCard — Side-by-side comparison card for pivot drawer.
// Displays original slot vs a candidate alternative.
// Used inside PivotDrawer to render each alternative in sequence.

import Image from "next/image";
import { type VibeTagDisplay } from "@/components/slot/VibeChips";

// ---------- Types ----------

export interface SwapCandidate {
  activityNodeId: string;
  activityName: string;
  imageUrl?: string;
  neighborhood?: string;
  category: string;
  priceLevel?: number;
  durationMinutes?: number;
  vibeTags: VibeTagDisplay[];
  /** Convergence score 0–1 */
  convergenceScore?: number;
  /** Short description from ActivityNode */
  descriptionShort?: string;
}

export interface SwapCardProps {
  /** Which side this card occupies */
  side: "original" | "alternative";
  candidate: SwapCandidate;
  /** Highlight border on selection */
  isSelected?: boolean;
  onClick?: () => void;
}

// ---------- Helpers ----------

function priceLevelLabel(level?: number): string {
  if (!level) return "";
  return "$".repeat(Math.min(level, 4));
}

function durationLabel(minutes?: number): string {
  if (!minutes) return "";
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function convergenceLabel(score?: number): string {
  if (score === undefined || score === null) return "";
  const pct = Math.round(score * 100);
  return `${pct}% match`;
}

// ---------- Sub-components ----------

function CategoryIcon({ category }: { category: string }) {
  // Inline SVG paths per category — no icon library
  const paths: Record<string, React.ReactNode> = {
    dining: <path d="M8 2v3m0 0c-2.2 0-4 1.8-4 4H4v5h8v-5h-.5C11 7.8 9.2 6 8 5zm-3 9h6" strokeLinecap="round" strokeLinejoin="round" />,
    drinks: <><path d="M6 2h4l1 5H5L6 2z" /><path d="M5 7v5a3 3 0 006 0V7" /></>,
    culture: <><rect x="2" y="8" width="12" height="7" rx="1" /><path d="M5 8V5a3 3 0 016 0v3" /></>,
    outdoors: <><path d="M2 14l4-6 3 3 3-4 4 7H2z" /><circle cx="12" cy="4" r="1.5" /></>,
    active: <><circle cx="8" cy="5" r="2" /><path d="M4 14l2-4 2 2 2-2 2 4" /></>,
    entertainment: <><circle cx="8" cy="8" r="6" /><polygon points="6,5 11,8 6,11" /></>,
    shopping: <><path d="M3 6h10l-1.5 7H4.5L3 6z" /><circle cx="6" cy="15" r="1" /><circle cx="10" cy="15" r="1" /></>,
    experience: <><path d="M8 2l1.8 3.6L14 6.3l-3 2.9.7 4.1L8 11.4l-3.7 1.9.7-4.1L2 6.3l4.2-.7L8 2z" /></>,
    nightlife: <><path d="M8 2C4.7 2 2 4.7 2 8s2.7 6 6 6 6-2.7 6-6" /><path d="M14 2l-4 4" /></>,
    wellness: <><path d="M8 14s-5-3.5-5-7a5 5 0 0110 0c0 3.5-5 7-5 7z" /></>,
  };

  const d = paths[category] ?? <circle cx="8" cy="8" r="5" />;

  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {d}
    </svg>
  );
}

// ---------- Component ----------

export function SwapCard({
  side,
  candidate,
  isSelected = false,
  onClick,
}: SwapCardProps) {
  const isOriginal = side === "original";

  return (
    <article
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") onClick(); } : undefined}
      aria-pressed={onClick ? isSelected : undefined}
      aria-label={`${isOriginal ? "Original" : "Alternative"}: ${candidate.activityName}`}
      className={`
        relative flex flex-col rounded-xl border overflow-hidden
        transition-all duration-200
        ${onClick ? "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta-400 focus-visible:ring-offset-2" : ""}
        ${isSelected
          ? "border-terracotta-500 shadow-[0_0_0_2px_#C4694F20]"
          : isOriginal
          ? "border-warm-border bg-warm-surface opacity-75"
          : "border-warm-border bg-warm-surface hover:border-terracotta-300"
        }
      `}
    >
      {/* Side label */}
      <div
        className={`
          absolute top-2 left-2 z-10
          px-2 py-0.5 rounded-full
          font-dm-mono text-[10px] uppercase tracking-wider
          ${isOriginal
            ? "bg-warm-background text-warm-text-secondary border border-warm-border"
            : isSelected
            ? "bg-terracotta-500 text-white"
            : "bg-terracotta-100 text-terracotta-700 border border-terracotta-200"
          }
        `}
      >
        {isOriginal ? "Current" : "Alternative"}
      </div>

      {/* Image */}
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-warm-background">
        {candidate.imageUrl ? (
          <Image
            src={candidate.imageUrl}
            alt={candidate.activityName}
            fill
            sizes="(max-width: 640px) 50vw, 33vw"
            className={`object-cover transition-transform duration-300 ${!isOriginal && !isSelected ? "hover:scale-[1.03]" : ""}`}
            loading="lazy"
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <svg
              width="40"
              height="40"
              viewBox="0 0 48 48"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-warm-text-secondary opacity-25"
              aria-hidden="true"
            >
              <rect x="6" y="10" width="36" height="28" rx="3" />
              <circle cx="18" cy="22" r="4" />
              <path d="M6 34l10-8 6 4 10-10 10 8" />
            </svg>
          </div>
        )}

        {/* Convergence badge — alternatives only */}
        {!isOriginal && candidate.convergenceScore !== undefined && (
          <div className="absolute bottom-2 right-2">
            <span className="
              px-2 py-0.5 rounded-full
              font-dm-mono text-[10px] uppercase tracking-wider
              bg-warm-surface/90 backdrop-blur-sm
              text-terracotta-600 border border-terracotta-200
            ">
              {convergenceLabel(candidate.convergenceScore)}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-3 space-y-2 flex-1">
        {/* Name */}
        <h4 className="font-sora font-semibold text-sm text-warm-text-primary leading-tight line-clamp-2">
          {candidate.activityName}
        </h4>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {/* Category */}
          <span className="flex items-center gap-1 font-dm-mono text-[11px] text-warm-text-secondary uppercase tracking-wider">
            <CategoryIcon category={candidate.category} />
            {candidate.category.replace("_", " ")}
          </span>

          {/* Price level */}
          {candidate.priceLevel && (
            <span className="font-dm-mono text-[11px] text-warm-text-secondary">
              {priceLevelLabel(candidate.priceLevel)}
            </span>
          )}

          {/* Duration */}
          {candidate.durationMinutes && (
            <span className="font-dm-mono text-[11px] text-warm-text-secondary">
              {durationLabel(candidate.durationMinutes)}
            </span>
          )}
        </div>

        {/* Neighborhood */}
        {candidate.neighborhood && (
          <p className="font-dm-mono text-[11px] text-warm-text-secondary truncate">
            {candidate.neighborhood}
          </p>
        )}

        {/* Short description */}
        {candidate.descriptionShort && (
          <p className="font-sora text-[12px] text-warm-text-secondary leading-relaxed line-clamp-3">
            {candidate.descriptionShort}
          </p>
        )}

        {/* Vibe tags — top 2 */}
        {candidate.vibeTags.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {candidate.vibeTags.slice(0, 2).map((tag) => (
              <span
                key={tag.slug}
                className="
                  inline-flex items-center px-1.5 py-0.5 rounded-full
                  font-dm-mono text-[10px] uppercase tracking-wider
                  bg-warm-background text-warm-text-secondary border border-warm-border
                "
              >
                {tag.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Selection indicator */}
      {isSelected && !isOriginal && (
        <div className="
          absolute top-2 right-2 z-10
          w-5 h-5 rounded-full
          bg-terracotta-500 flex items-center justify-center
        ">
          <svg
            width="10"
            height="10"
            viewBox="0 0 12 12"
            fill="none"
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="2 6.5 4.5 9 10 3.5" />
          </svg>
        </div>
      )}
    </article>
  );
}
