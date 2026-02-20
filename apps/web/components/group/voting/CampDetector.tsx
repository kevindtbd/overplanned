"use client";

// CampDetector — Detects when group members have split into camps on a slot.
//
// A "camp" forms when the group divides into distinct blocs:
//   - One set of members votes yes/maybe
//   - Another set votes no
//
// This component is purely display — it receives vote data, computes the
// split, and renders a visual camp breakdown.
//
// The parent VotingOrchestrator decides whether to trigger ConflictResolver
// based on CampDetector's onCampDetected callback.
//
// Design: Sora headings, DM Mono labels, terracotta accent, warm tokens.

import { useEffect, useMemo } from "react";
import type { MemberVote, VoteChoice } from "./VotePanel";

// ---------- Types ----------

export interface Camp {
  /** The vote position this camp is aligned with */
  side: "for" | "against";
  /** Members in this camp */
  members: MemberVote[];
  /** Fraction of the group in this camp [0.0, 1.0] */
  fraction: number;
}

export interface CampSplit {
  isSplit: boolean;
  camps: [Camp, Camp] | null;
  /** Fraction of group that is "for" (yes/maybe) */
  forFraction: number;
  /** Fraction of group that is "against" (no) */
  againstFraction: number;
  /** True when votes are still pending — too early to call a split */
  awaitingVotes: boolean;
}

export interface CampDetectorProps {
  slotId: string;
  memberVotes: MemberVote[];
  /** Minimum fraction of members who must have voted to enable detection */
  quorumFraction?: number;
  /** Minimum minority camp size (as fraction) to declare a real split */
  splitThreshold?: number;
  /** Called when a genuine camp split is detected */
  onCampDetected: (slotId: string, split: CampSplit) => void;
}

// ---------- Helpers ----------

const DEFAULT_QUORUM = 0.6;     // 60% must have voted before detection
const DEFAULT_SPLIT_THRESHOLD = 0.25; // minority must be >= 25% of group

function computeCampSplit(
  memberVotes: MemberVote[],
  quorumFraction: number,
  splitThreshold: number,
): CampSplit {
  const total = memberVotes.length;
  if (total === 0) {
    return {
      isSplit: false,
      camps: null,
      forFraction: 0,
      againstFraction: 0,
      awaitingVotes: true,
    };
  }

  const voted = memberVotes.filter((mv) => mv.vote !== null);
  const votedFraction = voted.length / total;

  // Not enough votes yet — don't call a split prematurely
  if (votedFraction < quorumFraction) {
    return {
      isSplit: false,
      camps: null,
      forFraction: 0,
      againstFraction: 0,
      awaitingVotes: true,
    };
  }

  const forMembers = voted.filter(
    (mv) => mv.vote === "yes" || mv.vote === "maybe"
  );
  const againstMembers = voted.filter((mv) => mv.vote === "no");

  const forFraction = forMembers.length / total;
  const againstFraction = againstMembers.length / total;

  // A meaningful split: both camps are non-trivial
  const isSplit =
    forFraction >= splitThreshold && againstFraction >= splitThreshold;

  if (!isSplit) {
    return {
      isSplit: false,
      camps: null,
      forFraction,
      againstFraction,
      awaitingVotes: false,
    };
  }

  return {
    isSplit: true,
    camps: [
      { side: "for", members: forMembers, fraction: forFraction },
      { side: "against", members: againstMembers, fraction: againstFraction },
    ],
    forFraction,
    againstFraction,
    awaitingVotes: false,
  };
}

// ---------- Sub-components ----------

function CampBlock({ camp }: { camp: Camp }) {
  const isFor = camp.side === "for";
  const bgClass = isFor
    ? "bg-emerald-50 border-emerald-200"
    : "bg-red-50 border-red-200";
  const textClass = isFor ? "text-emerald-700" : "text-red-600";
  const label = isFor ? "In favor" : "Against";
  const pct = Math.round(camp.fraction * 100);

  return (
    <div
      className={`flex-1 rounded-lg border p-3 ${bgClass}`}
      role="group"
      aria-label={`${label} camp`}
    >
      <div className={`font-dm-mono text-[10px] uppercase tracking-wider mb-2 ${textClass}`}>
        {label} — {pct}%
      </div>
      <ul className="space-y-1.5" aria-label={`Members voting ${label.toLowerCase()}`}>
        {camp.members.map((mv) => (
          <li
            key={mv.memberId}
            className="flex items-center gap-2 font-dm-mono text-xs text-warm-text-primary"
          >
            {mv.avatarUrl ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={mv.avatarUrl}
                alt={mv.memberName}
                className="w-5 h-5 rounded-full object-cover shrink-0"
              />
            ) : (
              <div
                className="
                  w-5 h-5 rounded-full shrink-0 flex items-center justify-center
                  bg-terracotta-100 text-terracotta-600
                  font-sora text-[9px] font-semibold
                "
                aria-hidden="true"
              >
                {mv.memberName.charAt(0).toUpperCase()}
              </div>
            )}
            <span className="truncate">{mv.memberName}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SplitBar({
  forFraction,
  againstFraction,
}: {
  forFraction: number;
  againstFraction: number;
}) {
  const forPct = Math.round(forFraction * 100);
  const againstPct = Math.round(againstFraction * 100);

  return (
    <div
      className="h-1.5 w-full rounded-full overflow-hidden bg-warm-border flex"
      role="meter"
      aria-label={`${forPct}% for, ${againstPct}% against`}
    >
      <div
        className="h-full bg-emerald-400 transition-all duration-300"
        style={{ width: `${forPct}%` }}
      />
      <div
        className="h-full bg-red-400 transition-all duration-300"
        style={{ width: `${againstPct}%` }}
      />
    </div>
  );
}

// ---------- Component ----------

export function CampDetector({
  slotId,
  memberVotes,
  quorumFraction = DEFAULT_QUORUM,
  splitThreshold = DEFAULT_SPLIT_THRESHOLD,
  onCampDetected,
}: CampDetectorProps) {
  const split = useMemo(
    () => computeCampSplit(memberVotes, quorumFraction, splitThreshold),
    [memberVotes, quorumFraction, splitThreshold]
  );

  // Notify parent when a real split is detected
  useEffect(() => {
    if (split.isSplit) {
      onCampDetected(slotId, split);
    }
  }, [split.isSplit, slotId, onCampDetected, split]);

  // Not enough votes yet
  if (split.awaitingVotes) {
    return null;
  }

  // No meaningful split — nothing to show
  if (!split.isSplit || !split.camps) {
    return null;
  }

  return (
    <section
      aria-label="Camp split detected"
      className="
        mt-3 rounded-xl border border-red-200
        bg-red-50/40 overflow-hidden
      "
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-red-200">
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-red-500 shrink-0"
          aria-hidden="true"
        >
          <path d="M8 2L14 14H2L8 2Z" />
          <line x1="8" y1="7" x2="8" y2="10" />
          <circle cx="8" cy="12" r="0.5" fill="currentColor" />
        </svg>
        <h4 className="font-sora text-sm font-semibold text-red-700">
          The group is split on this one
        </h4>
      </div>

      {/* Split visualization */}
      <div className="px-4 py-3 space-y-3">
        <SplitBar
          forFraction={split.forFraction}
          againstFraction={split.againstFraction}
        />
        <div className="flex gap-2">
          {split.camps.map((camp) => (
            <CampBlock key={camp.side} camp={camp} />
          ))}
        </div>
        <p className="font-dm-mono text-xs text-warm-text-secondary">
          Alternatives will load below for a re-vote.
        </p>
      </div>
    </section>
  );
}

// ---------- Utility (exported for testing) ----------

/** Pure function for testing without React. */
export { computeCampSplit };
