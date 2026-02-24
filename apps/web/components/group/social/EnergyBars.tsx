"use client";

// EnergyBars — Per-member energy state as horizontal progress bars.
//
// Renders each group member as a labeled horizontal bar showing their
// current engagement/energy level (0–1). Energy is derived from:
//   - recency of last vote
//   - number of confirmed slots
//   - signal activity in the last N hours
//
// Usage:
//   <EnergyBars members={members} showNames />

import { useMemo } from "react";

// ---------- Types ----------

export type EnergyLevel = "high" | "medium" | "low" | "absent";

export interface GroupMember {
  id: string;
  name: string;
  avatarUrl?: string;
  /** 0–1 normalized energy score */
  energyScore: number;
  /** Categorical override; if omitted, derived from energyScore */
  energyLevel?: EnergyLevel;
  /** Debt delta: positive = owes the group, negative = is owed */
  debtDelta: number;
  /** Last vote time ISO string */
  lastActiveAt?: string;
  /** Whether this member is the current group leader */
  isOrganizer?: boolean;
}

export interface EnergyBarsProps {
  members: GroupMember[];
  showNames?: boolean;
  showDebt?: boolean;
  className?: string;
}

// ---------- Helpers ----------

function getEnergyLevel(score: number): EnergyLevel {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  if (score > 0) return "low";
  return "absent";
}

const ENERGY_CONFIG: Record<
  EnergyLevel,
  { barColor: string; labelClass: string; label: string }
> = {
  high: {
    barColor: "#10b981",
    labelClass: "text-success",
    label: "High",
  },
  medium: {
    barColor: "#f59e0b",
    labelClass: "text-warning",
    label: "Mid",
  },
  low: {
    barColor: "var(--accent)",
    labelClass: "text-accent",
    label: "Low",
  },
  absent: {
    barColor: "#9ca3af",
    labelClass: "text-ink-600",
    label: "Away",
  },
};

function MemberAvatar({
  name,
  avatarUrl,
  size = 32,
}: {
  name: string;
  avatarUrl?: string;
  size?: number;
}) {
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt={name}
        width={size}
        height={size}
        className="rounded-full object-cover shrink-0"
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <div
      className="
        shrink-0 rounded-full
        bg-accent-light text-accent-fg
        flex items-center justify-center
        font-sora font-semibold
      "
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      aria-hidden="true"
    >
      {initials}
    </div>
  );
}

function DebtBadge({ delta }: { delta: number }) {
  if (Math.abs(delta) < 0.01) {
    return (
      <span className="font-dm-mono text-[10px] text-ink-400 px-1.5 py-0.5 rounded bg-base">
        Even
      </span>
    );
  }

  const positive = delta > 0;
  return (
    <span
      className={`
        font-dm-mono text-[10px] px-1.5 py-0.5 rounded
        ${
          positive
            ? "bg-warning-bg text-warning"
            : "bg-success-bg text-success"
        }
      `}
      title={positive ? "Owes the group" : "Group owes them"}
    >
      {positive ? "+" : ""}
      {delta.toFixed(1)}
    </span>
  );
}

function EnergyBar({
  member,
  showName,
  showDebt,
}: {
  member: GroupMember;
  showName: boolean;
  showDebt: boolean;
}) {
  const level = member.energyLevel ?? getEnergyLevel(member.energyScore);
  const config = ENERGY_CONFIG[level];
  const pct = Math.round(member.energyScore * 100);

  return (
    <div
      className="flex items-center gap-3"
      aria-label={`${member.name}: ${config.label} energy (${pct}%)`}
    >
      {/* Avatar */}
      <MemberAvatar name={member.name} avatarUrl={member.avatarUrl} size={32} />

      {/* Name + bar */}
      <div className="flex-1 min-w-0">
        {showName && (
          <div className="flex items-center justify-between mb-1 gap-2">
            <span className="font-sora text-sm font-medium text-ink-100 truncate">
              {member.name}
              {member.isOrganizer && (
                <span className="ml-1.5 font-dm-mono text-[9px] uppercase tracking-wider text-ink-400">
                  organizer
                </span>
              )}
            </span>
            <div className="flex items-center gap-2 shrink-0">
              {showDebt && <DebtBadge delta={member.debtDelta} />}
              <span className={`font-dm-mono text-[10px] uppercase tracking-wider ${config.labelClass}`}>
                {config.label}
              </span>
            </div>
          </div>
        )}

        {/* Bar track */}
        <div
          className="h-2 rounded-full bg-base overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${member.name} energy`}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              backgroundColor: config.barColor,
            }}
          />
        </div>
      </div>
    </div>
  );
}

// ---------- Main component ----------

export function EnergyBars({
  members,
  showNames = true,
  showDebt = true,
  className = "",
}: EnergyBarsProps) {
  const sorted = useMemo(
    () => [...members].sort((a, b) => b.energyScore - a.energyScore),
    [members]
  );

  if (members.length === 0) {
    return (
      <div
        className={`
          flex items-center justify-center py-8
          font-dm-mono text-xs text-ink-400 uppercase tracking-wider
          ${className}
        `}
        aria-label="No members to display"
      >
        No members yet
      </div>
    );
  }

  const highCount = members.filter(
    (m) => (m.energyLevel ?? getEnergyLevel(m.energyScore)) === "high"
  ).length;

  return (
    <div className={`space-y-4 ${className}`} aria-label="Member energy levels">
      {sorted.map((member) => (
        <EnergyBar
          key={member.id}
          member={member}
          showName={showNames}
          showDebt={showDebt}
        />
      ))}

      {/* Group summary footer */}
      <div className="pt-2 border-t border-ink-700">
        <p className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
          {highCount} of {members.length} members fully engaged
        </p>
      </div>
    </div>
  );
}
