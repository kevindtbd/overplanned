"use client";

// GroupDashboard — Mid-trip group social surface.
//
// Renders the full group state during an active trip:
//   - Group member list with energy bars
//   - Activity pulse line over time
//   - Affinity matrix with subgroup split suggestions
//   - Contested slot callouts
//
// Usage:
//   <GroupDashboard trip={tripData} members={memberList} />

import { useState, useMemo } from "react";
import { PulseLine, type PulsePoint } from "./PulseLine";
import { EnergyBars, type GroupMember } from "./EnergyBars";
import { AffinityMatrix, type AffinityEntry } from "./AffinityMatrix";

// ---------- Types ----------

export interface GroupTripData {
  id: string;
  destination: string;
  currentDay: number;
  totalDays: number;
  /** Active contested slot count */
  contestedSlots: number;
  /** Resolved decisions so far */
  resolvedCount: number;
  /** Overall group fairness score 0–1 */
  fairnessScore: number;
}

export interface GroupMemberFull extends GroupMember {
  /** Vibe tags this member has signaled strongly */
  topVibes: string[];
  /** Vote behavior: cooperative | contested | absent */
  votingPattern: "cooperative" | "contested" | "absent";
}

export interface GroupDashboardProps {
  trip: GroupTripData;
  members: GroupMemberFull[];
  pulseHistory: PulsePoint[];
  affinityData: AffinityEntry[];
  /** Called when a split suggestion is accepted */
  onSplitAccept?: (memberIds: string[]) => void;
  /** Called when a contested slot needs resolution */
  onResolveContest?: (slotId: string) => void;
}

// ---------- Sub-components ----------

function FairnessIndicator({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const colorClass =
    score >= 0.75
      ? "text-success"
      : score >= 0.5
      ? "text-warning"
      : "text-error";

  const arcRadius = 28;
  const circumference = Math.PI * arcRadius; // half-circle
  const offset = circumference * (1 - score);

  return (
    <div className="flex flex-col items-center gap-1" aria-label={`Fairness score: ${pct}%`}>
      <svg
        width="72"
        height="44"
        viewBox="0 0 72 44"
        fill="none"
        aria-hidden="true"
      >
        {/* Background arc */}
        <path
          d="M 8 36 A 28 28 0 0 1 64 36"
          stroke="var(--ink-700)"
          strokeWidth="5"
          strokeLinecap="round"
          fill="none"
        />
        {/* Foreground arc */}
        <path
          d="M 8 36 A 28 28 0 0 1 64 36"
          stroke={score >= 0.75 ? "#10b981" : score >= 0.5 ? "#f59e0b" : "#ef4444"}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${offset}`}
          fill="none"
          style={{ transformOrigin: "36px 36px" }}
        />
      </svg>
      <span className={`font-dm-mono text-lg font-semibold tabular-nums ${colorClass}`}>
        {pct}%
      </span>
      <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
        Fairness
      </span>
    </div>
  );
}

function StatPill({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-4 py-3 rounded-xl bg-surface border border-ink-700">
      <span
        className={`font-sora font-semibold text-xl ${
          accent ? "text-accent" : "text-ink-100"
        }`}
      >
        {value}
      </span>
      <span className="font-dm-mono text-[10px] uppercase tracking-wider text-ink-400">
        {label}
      </span>
    </div>
  );
}

function ContestBanner({
  count,
  onResolve,
}: {
  count: number;
  onResolve?: () => void;
}) {
  if (count === 0) return null;

  return (
    <div
      role="alert"
      className="
        flex items-center justify-between gap-3
        px-4 py-3 rounded-xl
        bg-warning-bg border border-amber-200
      "
    >
      <div className="flex items-center gap-2.5">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#d97706"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span className="font-sora text-sm font-semibold text-amber-800">
          {count} contested {count === 1 ? "slot" : "slots"} need group input
        </span>
      </div>
      {onResolve && (
        <button
          onClick={onResolve}
          className="
            font-dm-mono text-[11px] uppercase tracking-wider
            text-accent hover:text-accent-fg
            transition-colors duration-150 shrink-0
          "
        >
          Resolve
        </button>
      )}
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="font-sora font-semibold text-base text-ink-100">
        {title}
      </h2>
      {subtitle && (
        <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
          {subtitle}
        </p>
      )}
    </div>
  );
}

// ---------- Main component ----------

export function GroupDashboard({
  trip,
  members,
  pulseHistory,
  affinityData,
  onSplitAccept,
  onResolveContest,
}: GroupDashboardProps) {
  const [activeTab, setActiveTab] = useState<"energy" | "pulse" | "affinity">(
    "energy"
  );

  const presentMembers = useMemo(
    () => members.filter((m) => m.votingPattern !== "absent"),
    [members]
  );

  const tabs = [
    { id: "energy" as const, label: "Energy" },
    { id: "pulse" as const, label: "Pulse" },
    { id: "affinity" as const, label: "Affinity" },
  ];

  return (
    <section
      className="space-y-5"
      aria-label={`Group dashboard for ${trip.destination}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-sora font-bold text-xl text-ink-100">
            {trip.destination}
          </h1>
          <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
            Day {trip.currentDay} of {trip.totalDays} —{" "}
            {members.length} travelers
          </p>
        </div>
        <FairnessIndicator score={trip.fairnessScore} />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <StatPill label="Resolved" value={trip.resolvedCount} />
        <StatPill
          label="Contested"
          value={trip.contestedSlots}
          accent={trip.contestedSlots > 0}
        />
        <StatPill label="Active" value={presentMembers.length} />
      </div>

      {/* Contest banner */}
      <ContestBanner
        count={trip.contestedSlots}
        onResolve={
          onResolveContest
            ? () => onResolveContest("pending")
            : undefined
        }
      />

      {/* Tab navigation */}
      <div
        role="tablist"
        aria-label="Dashboard views"
        className="flex gap-1 p-1 rounded-xl bg-surface border border-ink-700"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex-1 py-2 px-3 rounded-lg
              font-dm-mono text-[11px] uppercase tracking-wider
              transition-all duration-150
              ${
                activeTab === tab.id
                  ? "bg-base text-accent shadow-sm"
                  : "text-ink-400 hover:text-ink-100"
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div
        id="panel-energy"
        role="tabpanel"
        aria-labelledby="tab-energy"
        hidden={activeTab !== "energy"}
      >
        <SectionHeader
          title="Member Energy"
          subtitle="Current engagement levels across the group"
        />
        <EnergyBars members={members} showNames />
      </div>

      <div
        id="panel-pulse"
        role="tabpanel"
        aria-labelledby="tab-pulse"
        hidden={activeTab !== "pulse"}
      >
        <SectionHeader
          title="Group Activity Pulse"
          subtitle="Voting and engagement over time"
        />
        <PulseLine
          data={pulseHistory}
          height={160}
          accentColor="var(--accent)"
        />
      </div>

      <div
        id="panel-affinity"
        role="tabpanel"
        aria-labelledby="tab-affinity"
        hidden={activeTab !== "affinity"}
      >
        <SectionHeader
          title="Preference Affinity"
          subtitle="Similarity between members — split suggestions shown below"
        />
        <AffinityMatrix
          members={members}
          entries={affinityData}
          onSplitAccept={onSplitAccept}
        />
      </div>
    </section>
  );
}
