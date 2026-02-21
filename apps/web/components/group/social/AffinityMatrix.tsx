"use client";

// AffinityMatrix — Grid heatmap showing preference similarity between members.
//
// Renders an N×N grid where each cell shows how similar two members' vibe
// preferences are (0–1). High-affinity pairs surface as split suggestions:
// "You and Alex both want ramen — split off?"
//
// Usage:
//   <AffinityMatrix members={members} entries={affinityData} onSplitAccept={fn} />

import { useMemo, useState } from "react";
import type { GroupMember } from "./EnergyBars";

// ---------- Types ----------

export interface AffinityEntry {
  memberIdA: string;
  memberIdB: string;
  /** 0–1 similarity score */
  score: number;
  /** Shared vibe tags that drive the score */
  sharedVibes: string[];
  /** Candidate activity for subgroup split */
  splitSuggestion?: string;
}

export interface SplitSuggestion {
  memberIds: string[];
  memberNames: string[];
  sharedVibes: string[];
  activity?: string;
  score: number;
}

export interface AffinityMatrixProps {
  members: GroupMember[];
  entries: AffinityEntry[];
  /** Minimum score to surface a split suggestion */
  splitThreshold?: number;
  onSplitAccept?: (memberIds: string[]) => void;
  className?: string;
}

// ---------- Helpers ----------

function affinityToColor(score: number): string {
  // Warm gradient: low = warm-background, high = terracotta
  if (score >= 0.8) return "#C4694F"; // accent
  if (score >= 0.6) return "#D68D73"; // terracotta-400
  if (score >= 0.4) return "#E8B09D"; // terracotta-300
  if (score >= 0.2) return "#F2CFC2"; // accent/20
  return "#FAEAE4"; // accent-light
}

function affinityTextColor(score: number): string {
  return score >= 0.6 ? "#fff" : "#52281E"; // white on dark terracotta, dark on light
}

function truncateName(name: string, max = 8): string {
  return name.length > max ? name.slice(0, max - 1) + "…" : name;
}

// ---------- Sub-components ----------

function SplitCard({
  suggestion,
  onAccept,
  onDismiss,
}: {
  suggestion: SplitSuggestion;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  const names = suggestion.memberNames.join(" and ");
  const vibeText = suggestion.sharedVibes.slice(0, 2).join(", ");

  return (
    <div
      className="
        rounded-xl border border-accent/20 bg-accent-light
        p-4 space-y-3
      "
      aria-label={`Split suggestion: ${names}`}
    >
      <div className="flex items-start gap-3">
        {/* Affinity icon */}
        <div className="shrink-0 w-8 h-8 rounded-full bg-accent-light flex items-center justify-center mt-0.5">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#C4694F"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-sora text-sm font-semibold text-accent-fg leading-snug">
            {names} both want{" "}
            {vibeText ? (
              <span className="text-accent">{vibeText}</span>
            ) : (
              "similar things"
            )}
            {suggestion.activity ? ` — split off for ${suggestion.activity}?` : " — split off?"}
          </p>

          <div className="flex flex-wrap gap-1 mt-2">
            {suggestion.sharedVibes.map((vibe) => (
              <span
                key={vibe}
                className="
                  font-dm-mono text-[10px] uppercase tracking-wider
                  px-2 py-0.5 rounded-full
                  bg-accent-light text-accent-fg
                "
              >
                {vibe}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={onAccept}
          className="
            flex-1 py-2 px-3 rounded-lg
            bg-accent text-white
            font-dm-mono text-[11px] uppercase tracking-wider
            hover:bg-accent-fg
            transition-colors duration-150
          "
        >
          Split off
        </button>
        <button
          onClick={onDismiss}
          className="
            py-2 px-3 rounded-lg
            border border-ink-700
            text-ink-400
            font-dm-mono text-[11px] uppercase tracking-wider
            hover:text-ink-100
            transition-colors duration-150
          "
        >
          Maybe later
        </button>
      </div>
    </div>
  );
}

function HeatCell({
  score,
  isSelf,
  label,
}: {
  score: number;
  isSelf: boolean;
  label: string;
}) {
  if (isSelf) {
    return (
      <div
        className="w-full h-full flex items-center justify-center"
        style={{ backgroundColor: "var(--bg-base)" }}
        aria-label="Same member"
      >
        <div className="w-2 h-2 rounded-full bg-ink-700" aria-hidden="true" />
      </div>
    );
  }

  const bg = affinityToColor(score);
  const fg = affinityTextColor(score);
  const pct = Math.round(score * 100);

  return (
    <div
      className="w-full h-full flex items-center justify-center transition-colors duration-200"
      style={{ backgroundColor: bg }}
      aria-label={`${label}: ${pct}% affinity`}
      title={`${pct}% affinity`}
    >
      <span
        className="font-dm-mono text-[9px] font-semibold tabular-nums"
        style={{ color: fg }}
        aria-hidden="true"
      >
        {pct}
      </span>
    </div>
  );
}

// ---------- Main component ----------

export function AffinityMatrix({
  members,
  entries,
  splitThreshold = 0.65,
  onSplitAccept,
  className = "",
}: AffinityMatrixProps) {
  const [dismissedPairs, setDismissedPairs] = useState<Set<string>>(new Set());

  // Build lookup map: "idA:idB" -> score
  const scoreMap = useMemo(() => {
    const m = new Map<string, AffinityEntry>();
    for (const entry of entries) {
      const key1 = `${entry.memberIdA}:${entry.memberIdB}`;
      const key2 = `${entry.memberIdB}:${entry.memberIdA}`;
      m.set(key1, entry);
      m.set(key2, entry);
    }
    return m;
  }, [entries]);

  // Surface split suggestions above threshold
  const splitSuggestions = useMemo<SplitSuggestion[]>(() => {
    return entries
      .filter((e) => {
        const key = [e.memberIdA, e.memberIdB].sort().join(":");
        return e.score >= splitThreshold && !dismissedPairs.has(key);
      })
      .map((e) => {
        const mA = members.find((m) => m.id === e.memberIdA);
        const mB = members.find((m) => m.id === e.memberIdB);
        return {
          memberIds: [e.memberIdA, e.memberIdB],
          memberNames: [mA?.name ?? "Member", mB?.name ?? "Member"],
          sharedVibes: e.sharedVibes,
          activity: e.splitSuggestion,
          score: e.score,
        };
      })
      .sort((a, b) => b.score - a.score);
  }, [entries, members, splitThreshold, dismissedPairs]);

  const CELL_SIZE = Math.min(48, Math.floor(240 / Math.max(members.length, 1)));

  if (members.length === 0) {
    return (
      <div
        className={`
          flex items-center justify-center py-8
          font-dm-mono text-xs text-ink-400 uppercase tracking-wider
          ${className}
        `}
        aria-label="No affinity data"
      >
        No members to compare
      </div>
    );
  }

  return (
    <div className={`space-y-5 ${className}`}>
      {/* Grid heatmap */}
      <div
        className="overflow-x-auto"
        aria-label="Member preference affinity heatmap"
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `${CELL_SIZE}px repeat(${members.length}, ${CELL_SIZE}px)`,
            gridTemplateRows: `${CELL_SIZE}px repeat(${members.length}, ${CELL_SIZE}px)`,
            gap: 2,
            width: "fit-content",
          }}
          role="grid"
          aria-label="Affinity matrix"
        >
          {/* Top-left empty cell */}
          <div aria-hidden="true" />

          {/* Column headers */}
          {members.map((m) => (
            <div
              key={`col-${m.id}`}
              role="columnheader"
              aria-label={m.name}
              className="flex items-end justify-center pb-1"
              style={{ height: CELL_SIZE }}
            >
              <span
                className="
                  font-dm-mono text-[9px] uppercase tracking-wider
                  text-ink-400
                  writing-mode-vertical
                "
                style={{
                  writingMode: "vertical-rl",
                  transform: "rotate(180deg)",
                  maxHeight: CELL_SIZE - 4,
                  overflow: "hidden",
                }}
              >
                {truncateName(m.name)}
              </span>
            </div>
          ))}

          {/* Rows */}
          {members.map((rowMember) => (
            <>
              {/* Row header */}
              <div
                key={`row-${rowMember.id}`}
                role="rowheader"
                aria-label={rowMember.name}
                className="flex items-center justify-end pr-1.5"
                style={{ height: CELL_SIZE }}
              >
                <span
                  className="
                    font-dm-mono text-[9px] uppercase tracking-wider
                    text-ink-400 truncate
                  "
                  style={{ maxWidth: CELL_SIZE - 4 }}
                >
                  {truncateName(rowMember.name)}
                </span>
              </div>

              {/* Cells */}
              {members.map((colMember) => {
                const isSelf = rowMember.id === colMember.id;
                const entry = scoreMap.get(
                  `${rowMember.id}:${colMember.id}`
                );
                const score = entry?.score ?? 0;

                return (
                  <div
                    key={`cell-${rowMember.id}-${colMember.id}`}
                    role="gridcell"
                    style={{ height: CELL_SIZE, width: CELL_SIZE }}
                    className="rounded overflow-hidden"
                  >
                    <HeatCell
                      score={score}
                      isSelf={isSelf}
                      label={`${rowMember.name} + ${colMember.name}`}
                    />
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>

      {/* Color scale legend */}
      <div className="flex items-center gap-2">
        <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider shrink-0">
          Low
        </span>
        <div
          className="flex-1 h-2 rounded-full"
          style={{
            background: "linear-gradient(to right, #FAEAE4, #C4694F)",
          }}
          aria-hidden="true"
        />
        <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider shrink-0">
          High
        </span>
      </div>

      {/* Split suggestions */}
      {splitSuggestions.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-sora text-sm font-semibold text-ink-100">
            Subgroup suggestions
          </h3>
          {splitSuggestions.map((suggestion) => {
            const pairKey = suggestion.memberIds.slice().sort().join(":");
            return (
              <SplitCard
                key={pairKey}
                suggestion={suggestion}
                onAccept={() => {
                  onSplitAccept?.(suggestion.memberIds);
                  setDismissedPairs((prev) => new Set([...prev, pairKey]));
                }}
                onDismiss={() => {
                  setDismissedPairs((prev) => new Set([...prev, pairKey]));
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
