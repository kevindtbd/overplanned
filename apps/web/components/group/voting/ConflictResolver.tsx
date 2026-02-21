"use client";

// ConflictResolver — Presents alternative activities when a slot is contested.
//
// Flow:
//   1. Parent passes alternatives fetched from ActivitySearchService
//   2. ConflictResolver renders each alternative as a selectable card
//   3. Members vote on the alternatives (same VotePanel mechanic)
//   4. On resolution:
//      - ItinerarySlot.voteState updated to 'confirmed'
//      - ItinerarySlot.isContested set to false
//   5. If no alternative wins, parent can escalate (manual pick / Abilene prompt)
//
// Design: Sora headings, DM Mono labels, terracotta accent, warm tokens.

import { useCallback, useTransition } from "react";
import Image from "next/image";
import type { MemberVote, VoteState } from "./VotePanel";
import { VotePanel } from "./VotePanel";

// ---------- Types ----------

export interface AlternativeActivity {
  activityNodeId: string;
  name: string;
  imageUrl?: string;
  category: string;
  priceLevel?: number | null;
  /** Short description, 1-2 sentences */
  descriptionShort?: string;
  vibeTags: Array<{ slug: string; label: string }>;
  /** [0.0, 1.0] — how well this alternative fits the group's merged preferences */
  groupFitScore?: number;
  /** { memberId -> preference score [0.0, 1.0] } */
  memberFitScores?: Record<string, number>;
}

export interface AlternativeVoteState {
  activityNodeId: string;
  voteState: VoteState;
  memberVotes: MemberVote[];
  isComplete: boolean;
}

export interface ConflictResolverProps {
  slotId: string;
  /** Contested slot info */
  contestedSlotName: string;
  /** Alternatives fetched from ActivitySearchService */
  alternatives: AlternativeActivity[];
  /** Per-alternative vote states */
  alternativeVotes: AlternativeVoteState[];
  /** ID of the current user */
  currentUserId: string;
  /** True while alternatives are loading from the API */
  isLoading?: boolean;
  /** Called when a member votes on an alternative */
  onVote: (
    slotId: string,
    alternativeActivityNodeId: string,
    vote: "yes" | "no" | "maybe"
  ) => void | Promise<void>;
  /** Called when the group confirms an alternative */
  onConfirm: (
    slotId: string,
    chosenActivityNodeId: string
  ) => void | Promise<void>;
}

// ---------- Helpers ----------

const PRICE_LABELS: Record<number, string> = {
  1: "$",
  2: "$$",
  3: "$$$",
};

function FitBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div
      className="flex items-center gap-2"
      aria-label={`Group fit: ${pct}%`}
    >
      <div className="flex-1 h-1 rounded-full bg-ink-700 overflow-hidden">
        <div
          className="h-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
          role="presentation"
        />
      </div>
      <span className="font-dm-mono text-[10px] text-ink-400 shrink-0">
        {pct}% fit
      </span>
    </div>
  );
}

function AlternativeCard({
  alternative,
  voteState,
  currentUserId,
  onVote,
  onConfirm,
  slotId,
}: {
  alternative: AlternativeActivity;
  voteState: AlternativeVoteState | undefined;
  currentUserId: string;
  onVote: ConflictResolverProps["onVote"];
  onConfirm: ConflictResolverProps["onConfirm"];
  slotId: string;
}) {
  const [isPending, startTransition] = useTransition();

  const isConfirmed = voteState?.voteState === "confirmed";
  const isEmpty = !voteState || voteState.memberVotes.length === 0;

  const handleVote = useCallback(
    (altNodeId: string, choice: "yes" | "no" | "maybe") => {
      startTransition(() => {
        const result = onVote(slotId, altNodeId, choice);
        if (result instanceof Promise) {
          result.catch(console.error);
        }
      });
    },
    [slotId, onVote]
  );

  const handleConfirm = useCallback(() => {
    startTransition(() => {
      const result = onConfirm(slotId, alternative.activityNodeId);
      if (result instanceof Promise) {
        result.catch(console.error);
      }
    });
  }, [slotId, alternative.activityNodeId, onConfirm]);

  return (
    <article
      className={`
        rounded-xl border overflow-hidden transition-shadow duration-200
        ${isConfirmed
          ? "border-emerald-300 bg-emerald-50/30 shadow-sm"
          : "border-ink-700 bg-surface hover:shadow-md"
        }
      `}
      aria-label={`Alternative: ${alternative.name}${isConfirmed ? " (confirmed)" : ""}`}
    >
      {/* Image */}
      <div className="relative aspect-[3/2] w-full overflow-hidden bg-base">
        {alternative.imageUrl ? (
          <Image
            src={alternative.imageUrl}
            alt={alternative.name}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <svg
              width="40"
              height="40"
              viewBox="0 0 48 48"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-ink-400 opacity-30"
              aria-hidden="true"
            >
              <rect x="6" y="10" width="36" height="28" rx="3" />
              <circle cx="18" cy="22" r="4" />
              <path d="M6 34l10-8 6 4 10-10 10 8" />
            </svg>
          </div>
        )}

        {/* Confirmed badge */}
        {isConfirmed && (
          <div className="absolute top-3 right-3">
            <span
              className="
                inline-flex items-center gap-1.5 px-2 py-1 rounded-full
                bg-emerald-100 text-success
                font-dm-mono text-[10px] uppercase tracking-wider
                backdrop-blur-sm
              "
            >
              <span className="w-1.5 h-1.5 rounded-full bg-success" aria-hidden="true" />
              Confirmed
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Name + meta */}
        <div className="flex items-start justify-between gap-2">
          <h5 className="font-sora font-semibold text-ink-100 text-sm leading-tight">
            {alternative.name}
          </h5>
          <div className="flex items-center gap-1.5 shrink-0">
            {alternative.priceLevel != null && (
              <span className="font-dm-mono text-[10px] text-ink-400 bg-base px-1.5 py-0.5 rounded">
                {PRICE_LABELS[alternative.priceLevel] ?? ""}
              </span>
            )}
            <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400 bg-base px-1.5 py-0.5 rounded">
              {alternative.category}
            </span>
          </div>
        </div>

        {/* Description */}
        {alternative.descriptionShort && (
          <p className="font-dm-mono text-xs text-ink-400 leading-relaxed">
            {alternative.descriptionShort}
          </p>
        )}

        {/* Group fit bar */}
        {alternative.groupFitScore != null && (
          <FitBar score={alternative.groupFitScore} />
        )}

        {/* Vibe tags */}
        {alternative.vibeTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {alternative.vibeTags.slice(0, 4).map((tag) => (
              <span
                key={tag.slug}
                className="
                  font-dm-mono text-[10px] uppercase tracking-wider
                  text-accent-fg bg-accent-light
                  px-1.5 py-0.5 rounded
                "
              >
                {tag.label}
              </span>
            ))}
          </div>
        )}

        {/* Vote panel for this alternative */}
        {!isEmpty && voteState && (
          <VotePanel
            slotId={alternative.activityNodeId}
            voteState={voteState.voteState}
            memberVotes={voteState.memberVotes}
            currentUserId={currentUserId}
            isComplete={voteState.isComplete}
            onVote={(_, choice) => handleVote(alternative.activityNodeId, choice)}
          />
        )}

        {/* Confirm button (shown when all voted yes/maybe) */}
        {voteState?.isComplete && voteState.voteState === "confirmed" && (
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isPending}
            className="
              w-full py-2.5 px-4 rounded-lg
              bg-accent text-white
              font-sora text-sm font-semibold
              hover:bg-accent-fg active:bg-accent-fg
              transition-colors duration-150
              focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-accent-400 focus-visible:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed
            "
          >
            Lock this in
          </button>
        )}
      </div>
    </article>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-ink-700 bg-surface overflow-hidden animate-pulse"
          aria-hidden="true"
        >
          <div className="aspect-[3/2] w-full bg-ink-700/40" />
          <div className="p-4 space-y-3">
            <div className="h-4 w-2/3 rounded bg-ink-700/40" />
            <div className="h-3 w-full rounded bg-ink-700/40" />
            <div className="h-1.5 w-full rounded-full bg-ink-700/40" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------- Component ----------

export function ConflictResolver({
  slotId,
  contestedSlotName,
  alternatives,
  alternativeVotes,
  currentUserId,
  isLoading = false,
  onVote,
  onConfirm,
}: ConflictResolverProps) {
  if (isLoading) {
    return (
      <section aria-label="Loading alternatives" className="mt-4 space-y-4">
        <div className="flex items-center gap-2">
          <div
            className="w-4 h-4 rounded-full border-2 border-accent/30 border-t-accent-fg animate-spin"
            aria-hidden="true"
          />
          <span className="font-dm-mono text-xs uppercase tracking-wider text-ink-400">
            Finding alternatives for the group...
          </span>
        </div>
        <LoadingSkeleton />
      </section>
    );
  }

  if (alternatives.length === 0) {
    return (
      <section
        aria-label="No alternatives available"
        className="mt-4 py-8 rounded-xl border-2 border-dashed border-ink-700 text-center"
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 32 32"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="mx-auto mb-3 text-ink-400 opacity-40"
          aria-hidden="true"
        >
          <circle cx="16" cy="16" r="13" />
          <line x1="16" y1="10" x2="16" y2="18" />
          <circle cx="16" cy="22" r="1" fill="currentColor" />
        </svg>
        <p className="font-sora text-sm font-semibold text-ink-100 mb-1">
          No alternatives found
        </p>
        <p className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
          Try adjusting group preferences
        </p>
      </section>
    );
  }

  const voteMap = new Map(
    alternativeVotes.map((av) => [av.activityNodeId, av])
  );

  return (
    <section aria-label="Conflict resolver" className="mt-4 space-y-4">
      {/* Header */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-warning-bg border border-amber-200">
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-warning shrink-0 mt-0.5"
          aria-hidden="true"
        >
          <path d="M10 2L18 18H2L10 2Z" />
          <line x1="10" y1="8" x2="10" y2="12" />
          <circle cx="10" cy="15" r="0.75" fill="currentColor" />
        </svg>
        <div>
          <h4 className="font-sora text-sm font-semibold text-amber-800 mb-0.5">
            Let&apos;s find something everyone can agree on
          </h4>
          <p className="font-dm-mono text-xs text-warning">
            The group split on{" "}
            <span className="font-medium">{contestedSlotName}</span>. Vote on
            these alternatives.
          </p>
        </div>
      </div>

      {/* Alternative cards */}
      <div className="space-y-3">
        {alternatives.map((alt) => (
          <AlternativeCard
            key={alt.activityNodeId}
            alternative={alt}
            voteState={voteMap.get(alt.activityNodeId)}
            currentUserId={currentUserId}
            onVote={onVote}
            onConfirm={onConfirm}
            slotId={slotId}
          />
        ))}
      </div>
    </section>
  );
}
