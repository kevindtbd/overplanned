"use client";

import { useState, useCallback } from "react";

interface SubgroupSuggestion {
  memberIds: string[];
  slotIds: string[];
}

interface SplitDayCardProps {
  tripId: string;
  dayNumber: number;
  subgroups: SubgroupSuggestion[];
  members: Array<{
    userId: string;
    user: { name: string | null; avatarUrl: string | null };
  }>;
  isOrganizer: boolean;
  onSplit: () => void;
  onDismiss: () => void;
}

function MemberAvatar({
  name,
  avatarUrl,
}: {
  name: string | null;
  avatarUrl: string | null;
}) {
  const initial = name ? name.charAt(0).toUpperCase() : "?";

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name || "Member"}
        className="w-6 h-6 rounded-full border-2 border-warm-surface object-cover"
      />
    );
  }

  return (
    <div
      className="w-6 h-6 rounded-full border-2 border-warm-surface bg-warm-border flex items-center justify-center"
      aria-label={name || "Member"}
    >
      <span className="font-mono text-[9px] text-ink-300">{initial}</span>
    </div>
  );
}

function getFirstName(name: string | null): string {
  if (!name) return "?";
  return name.split(" ")[0];
}

export function SplitDayCard({
  tripId,
  dayNumber,
  subgroups,
  members,
  isOrganizer,
  onSplit,
  onDismiss,
}: SplitDayCardProps) {
  const [submitting, setSubmitting] = useState(false);

  const memberMap = new Map(
    members.map((m) => [m.userId, m.user])
  );

  const handleSplit = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/trips/${tripId}/split-day`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dayNumber, subgroups }),
      });
      if (res.ok) {
        onSplit();
      }
    } catch {
      // Silently fail
    } finally {
      setSubmitting(false);
    }
  }, [tripId, dayNumber, subgroups, onSplit, submitting]);

  const handleSuggest = useCallback(() => {
    // TODO: Send a chat message suggesting this split to the group
    console.log("Suggest split", { tripId, dayNumber, subgroups });
  }, [tripId, dayNumber, subgroups]);

  return (
    <div className="rounded-[13px] border border-warm-border bg-warm-surface p-4">
      <h4 className="font-heading text-sm text-ink-100 mb-3">
        Split the afternoon?
      </h4>

      {/* Subgroup bubbles */}
      <div className="space-y-2 mb-4">
        {subgroups.map((group, idx) => {
          const groupMembers = group.memberIds
            .map((id) => ({ id, user: memberMap.get(id) }))
            .filter((m) => m.user);

          return (
            <div key={idx} className="flex items-center gap-2">
              {/* Overlapping avatars */}
              <div className="flex -space-x-1.5">
                {groupMembers.map((m) => (
                  <MemberAvatar
                    key={m.id}
                    name={m.user!.name}
                    avatarUrl={m.user!.avatarUrl}
                  />
                ))}
              </div>
              {/* Names */}
              <span className="font-mono text-[11px] text-ink-300">
                {groupMembers
                  .map((m) => getFirstName(m.user!.name))
                  .join(" + ")}
              </span>
            </div>
          );
        })}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        {isOrganizer ? (
          <button
            onClick={handleSplit}
            disabled={submitting}
            className="bg-terracotta text-white rounded-lg px-4 py-2 text-sm disabled:opacity-50 transition-colors"
          >
            {submitting ? "Splitting..." : "Split up"}
          </button>
        ) : (
          <button
            onClick={handleSuggest}
            className="bg-terracotta text-white rounded-lg px-4 py-2 text-sm transition-colors"
          >
            Suggest split
          </button>
        )}
        <button
          onClick={onDismiss}
          disabled={submitting}
          className="border border-warm-border text-ink-300 rounded-lg px-4 py-2 text-sm hover:border-ink-400 transition-colors"
        >
          Stay together
        </button>
      </div>
    </div>
  );
}
