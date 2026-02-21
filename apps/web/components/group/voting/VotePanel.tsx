"use client";

// VotePanel — Group voting UI for a single ItinerarySlot.
//
// Vote lifecycle:
//   proposed -> voting -> confirmed | contested
//
// Each member casts a vote (yes / no / maybe) on each proposed slot.
// When all members have voted:
//   - Majority yes -> confirmed
//   - Divided votes -> contested (triggers CampDetector)
//
// Design: Sora headings, DM Mono labels, terracotta accent, warm tokens.

import { useState, useCallback, useTransition } from "react";

// ---------- Types ----------

export type VoteChoice = "yes" | "no" | "maybe";

export type VoteState = "proposed" | "voting" | "confirmed" | "contested";

export interface MemberVote {
  memberId: string;
  memberName: string;
  /** Unsplash URL or null */
  avatarUrl?: string | null;
  vote: VoteChoice | null;
}

export interface VotePanelProps {
  slotId: string;
  /** Current group vote state for this slot */
  voteState: VoteState;
  /** Ordered list of group members and their current votes */
  memberVotes: MemberVote[];
  /** ID of the current user (to highlight their vote row) */
  currentUserId: string;
  /** Whether all members have voted */
  isComplete: boolean;
  /** Called when the current user casts or changes their vote */
  onVote: (slotId: string, vote: VoteChoice) => void | Promise<void>;
}

// ---------- Helpers ----------

const VOTE_CONFIG: Record<
  VoteChoice,
  { label: string; activeClass: string; hoverClass: string; icon: React.ReactNode }
> = {
  yes: {
    label: "Yes",
    activeClass: "bg-emerald-100 text-success border-emerald-400",
    hoverClass: "hover:border-emerald-400 hover:text-success",
    icon: (
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />
      </svg>
    ),
  },
  maybe: {
    label: "Maybe",
    activeClass: "bg-amber-100 text-warning border-amber-400",
    hoverClass: "hover:border-amber-400 hover:text-warning",
    icon: (
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
        <circle cx="8" cy="8" r="6.5" />
        <line x1="8" y1="5" x2="8" y2="9" />
        <circle cx="8" cy="11.5" r="0.75" fill="currentColor" />
      </svg>
    ),
  },
  no: {
    label: "No",
    activeClass: "bg-error-bg text-error border-red-400",
    hoverClass: "hover:border-red-400 hover:text-error",
    icon: (
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <line x1="4" y1="4" x2="12" y2="12" />
        <line x1="12" y1="4" x2="4" y2="12" />
      </svg>
    ),
  },
};

const VOTE_STATE_BADGE: Record<
  VoteState,
  { label: string; dotClass: string; textClass: string }
> = {
  proposed: {
    label: "Awaiting votes",
    dotClass: "bg-ink-700",
    textClass: "text-ink-400",
  },
  voting: {
    label: "Voting in progress",
    dotClass: "bg-warning",
    textClass: "text-warning",
  },
  confirmed: {
    label: "Confirmed",
    dotClass: "bg-success",
    textClass: "text-success",
  },
  contested: {
    label: "Contested",
    dotClass: "bg-red-400",
    textClass: "text-error",
  },
};

function VoteCountSummary({ memberVotes }: { memberVotes: MemberVote[] }) {
  const counts = memberVotes.reduce(
    (acc, mv) => {
      if (mv.vote) acc[mv.vote] = (acc[mv.vote] || 0) + 1;
      return acc;
    },
    {} as Record<VoteChoice, number>
  );

  const total = memberVotes.length;
  const voted = memberVotes.filter((mv) => mv.vote !== null).length;

  return (
    <div className="flex items-center gap-4 font-dm-mono text-xs text-ink-400">
      <span className="uppercase tracking-wider">
        {voted}/{total} voted
      </span>
      {(counts.yes ?? 0) > 0 && (
        <span className="text-success">{counts.yes} yes</span>
      )}
      {(counts.maybe ?? 0) > 0 && (
        <span className="text-warning">{counts.maybe} maybe</span>
      )}
      {(counts.no ?? 0) > 0 && (
        <span className="text-error">{counts.no} no</span>
      )}
    </div>
  );
}

function MemberVoteRow({
  mv,
  isCurrentUser,
  onVote,
  isPending,
}: {
  mv: MemberVote;
  isCurrentUser: boolean;
  onVote: (choice: VoteChoice) => void;
  isPending: boolean;
}) {
  return (
    <div
      className={`
        flex items-center justify-between gap-3 py-2.5 px-3 rounded-lg
        ${isCurrentUser ? "bg-base" : ""}
      `}
    >
      {/* Member identity */}
      <div className="flex items-center gap-2.5 min-w-0">
        {mv.avatarUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={mv.avatarUrl}
            alt={mv.memberName}
            className="w-7 h-7 rounded-full object-cover shrink-0"
          />
        ) : (
          <div
            className="
              w-7 h-7 rounded-full shrink-0
              bg-accent-light text-accent-fg
              flex items-center justify-center
              font-sora text-xs font-semibold
            "
            aria-hidden="true"
          >
            {mv.memberName.charAt(0).toUpperCase()}
          </div>
        )}
        <span
          className={`
            font-dm-mono text-xs truncate
            ${isCurrentUser ? "text-ink-100 font-medium" : "text-ink-400"}
          `}
        >
          {isCurrentUser ? "You" : mv.memberName}
        </span>
      </div>

      {/* Vote buttons (only interactive for current user) */}
      {isCurrentUser ? (
        <div
          className="flex items-center gap-1.5"
          role="group"
          aria-label={`Your vote for this slot`}
        >
          {(["yes", "maybe", "no"] as VoteChoice[]).map((choice) => {
            const cfg = VOTE_CONFIG[choice];
            const isSelected = mv.vote === choice;
            return (
              <button
                key={choice}
                type="button"
                onClick={() => onVote(choice)}
                disabled={isPending}
                aria-pressed={isSelected}
                aria-label={`Vote ${choice}`}
                className={`
                  inline-flex items-center gap-1 px-2 py-1 rounded-md
                  font-dm-mono text-[10px] uppercase tracking-wider
                  border transition-all duration-150
                  focus-visible:outline-none focus-visible:ring-2
                  focus-visible:ring-accent-400 focus-visible:ring-offset-1
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${
                    isSelected
                      ? cfg.activeClass
                      : `bg-surface text-ink-400 border-ink-700 ${cfg.hoverClass}`
                  }
                `}
              >
                {cfg.icon}
                {cfg.label}
              </button>
            );
          })}
        </div>
      ) : (
        /* Other member — show their vote status read-only */
        <div className="font-dm-mono text-xs">
          {mv.vote ? (
            <span
              className={`
                inline-flex items-center gap-1 px-2 py-1 rounded-md border
                ${VOTE_CONFIG[mv.vote].activeClass}
              `}
            >
              {VOTE_CONFIG[mv.vote].icon}
              {VOTE_CONFIG[mv.vote].label}
            </span>
          ) : (
            <span className="text-ink-400 uppercase tracking-wider opacity-60">
              Pending
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- Component ----------

export function VotePanel({
  slotId,
  voteState,
  memberVotes,
  currentUserId,
  isComplete,
  onVote,
}: VotePanelProps) {
  const [isPending, startTransition] = useTransition();

  const handleVote = useCallback(
    (choice: VoteChoice) => {
      startTransition(() => {
        const result = onVote(slotId, choice);
        if (result instanceof Promise) {
          result.catch(console.error);
        }
      });
    },
    [slotId, onVote]
  );

  const badgeCfg = VOTE_STATE_BADGE[voteState];

  return (
    <section
      aria-label="Group vote"
      className="
        mt-3 rounded-xl border border-ink-700
        bg-surface overflow-hidden
      "
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-700">
        <h4 className="font-sora text-sm font-semibold text-ink-100">
          Group Vote
        </h4>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${badgeCfg.dotClass}`}
            aria-hidden="true"
          />
          <span
            className={`font-dm-mono text-[10px] uppercase tracking-wider ${badgeCfg.textClass}`}
          >
            {badgeCfg.label}
          </span>
        </div>
      </div>

      {/* Member vote rows */}
      <div className="divide-y divide-ink-700">
        {memberVotes.map((mv) => (
          <MemberVoteRow
            key={mv.memberId}
            mv={mv}
            isCurrentUser={mv.memberId === currentUserId}
            onVote={handleVote}
            isPending={isPending}
          />
        ))}
      </div>

      {/* Summary footer */}
      {memberVotes.length > 0 && (
        <div className="px-4 py-3 border-t border-ink-700 bg-base">
          <VoteCountSummary memberVotes={memberVotes} />
          {isComplete && voteState === "contested" && (
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-error mt-1.5">
              Votes are divided. See alternatives below.
            </p>
          )}
          {isComplete && voteState === "confirmed" && (
            <p className="font-dm-mono text-[10px] uppercase tracking-wider text-success mt-1.5">
              Everyone is in. This one is locked.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
