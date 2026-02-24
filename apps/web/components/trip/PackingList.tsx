"use client";

import { useState, useCallback } from "react";

interface PackingItem {
  id: string;
  text: string;
  category: "essentials" | "clothing" | "documents" | "tech" | "toiletries" | "misc";
  checked: boolean;
  claimedBy?: string | null;
}

interface PackingListData {
  items: PackingItem[];
  generatedAt: string;
  model: string;
}

interface PackingListProps {
  tripId: string;
  packingList: PackingListData | null;
  onUpdate: () => void;
  currentUserId?: string;
  members?: Array<{
    userId: string;
    user: { name: string | null; avatarUrl: string | null };
  }>;
}

const CATEGORY_ORDER = [
  "essentials",
  "clothing",
  "documents",
  "tech",
  "toiletries",
  "misc",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  essentials: "Essentials",
  clothing: "Clothing",
  documents: "Documents",
  tech: "Tech",
  toiletries: "Toiletries",
  misc: "Misc",
};

function ClaimPill({
  item,
  currentUserId,
  members,
  onClaim,
  onUnclaim,
}: {
  item: PackingItem;
  currentUserId?: string;
  members?: Map<string, { name: string | null; avatarUrl: string | null }>;
  onClaim: (itemId: string) => void;
  onUnclaim: (itemId: string) => void;
}) {
  if (!currentUserId) return null;

  // Unclaimed
  if (!item.claimedBy) {
    return (
      <button
        onClick={() => onClaim(item.id)}
        className="border border-dashed border-ink-700 rounded-full px-2 py-0.5 text-[10px] font-dm-mono text-ink-400 cursor-pointer hover:border-ink-400 transition-colors"
        aria-label={`Claim ${item.text}`}
      >
        claim
      </button>
    );
  }

  // Claimed by current user
  if (item.claimedBy === currentUserId) {
    return (
      <button
        onClick={() => onUnclaim(item.id)}
        className="bg-accent/10 border border-accent/30 rounded-full px-2 py-0.5 text-[10px] font-dm-mono text-accent inline-flex items-center gap-1 cursor-pointer"
        aria-label={`Unclaim ${item.text}`}
      >
        <span className="w-3.5 h-3.5 rounded-full bg-accent/20 flex items-center justify-center text-[8px] font-dm-mono text-accent">
          {members?.get(currentUserId)?.name?.charAt(0)?.toUpperCase() || "Y"}
        </span>
        you
      </button>
    );
  }

  // Claimed by someone else
  const claimer = members?.get(item.claimedBy);
  const claimerName = claimer?.name?.split(" ")[0] || "Someone";
  const claimerInitial = claimer?.name?.charAt(0)?.toUpperCase() || "?";

  return (
    <span className="bg-ink-700 rounded-full px-2 py-0.5 text-[10px] font-dm-mono text-ink-300 inline-flex items-center gap-1">
      {claimer?.avatarUrl ? (
        <img
          src={claimer.avatarUrl}
          alt={claimerName}
          className="w-3.5 h-3.5 rounded-full object-cover"
        />
      ) : (
        <span className="w-3.5 h-3.5 rounded-full bg-ink-700 flex items-center justify-center text-[8px]">
          {claimerInitial}
        </span>
      )}
      {claimerName}
    </span>
  );
}

export function PackingList({ tripId, packingList, onUpdate, currentUserId, members }: PackingListProps) {
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState<string | null>(null);
  const [claiming, setClaiming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const memberMap = members
    ? new Map(members.map((m) => [m.userId, m.user]))
    : undefined;

  const generate = useCallback(
    async (regenerate = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/trips/${tripId}/packing`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: regenerate ? JSON.stringify({ regenerate: true }) : undefined,
        });
        if (!res.ok) {
          const data = await res.json();
          setError(data.error || "Failed to generate packing list");
          return;
        }
        onUpdate();
      } catch {
        setError("Network error");
      } finally {
        setLoading(false);
      }
    },
    [tripId, onUpdate]
  );

  const toggleItem = useCallback(
    async (itemId: string, checked: boolean) => {
      setChecking(itemId);
      try {
        const res = await fetch(`/api/trips/${tripId}/packing`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ itemId, checked }),
        });
        if (res.ok) {
          onUpdate();
        }
      } catch {
        // Silently fail — optimistic UI will revert on next fetch
      } finally {
        setChecking(null);
      }
    },
    [tripId, onUpdate]
  );

  const claimItem = useCallback(
    async (itemId: string) => {
      if (!currentUserId) return;
      setClaiming(itemId);
      try {
        const res = await fetch(`/api/trips/${tripId}/packing`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ itemId, claimedBy: currentUserId }),
        });
        if (res.ok) onUpdate();
      } catch {
        // Silently fail
      } finally {
        setClaiming(null);
      }
    },
    [tripId, currentUserId, onUpdate]
  );

  const unclaimItem = useCallback(
    async (itemId: string) => {
      setClaiming(itemId);
      try {
        const res = await fetch(`/api/trips/${tripId}/packing`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ itemId, claimedBy: null }),
        });
        if (res.ok) onUpdate();
      } catch {
        // Silently fail
      } finally {
        setClaiming(null);
      }
    },
    [tripId, onUpdate]
  );

  // No packing list yet — show generate button
  if (!packingList) {
    return (
      <div className="rounded-xl bg-surface border border-ink-700 p-6">
        <h3 className="font-sora text-lg text-ink-100 mb-2">Packing List</h3>
        <p className="text-sm text-ink-300 mb-4">
          Build a packing list from your destination, dates, and weather.
        </p>
        {error && (
          <p className="text-sm text-error mb-3">{error}</p>
        )}
        <button
          onClick={() => generate(false)}
          disabled={loading}
          className="btn-primary text-sm"
        >
          {loading ? "Generating..." : "Generate packing list"}
        </button>
      </div>
    );
  }

  // Group items by category
  const grouped = CATEGORY_ORDER.reduce<Record<string, PackingItem[]>>(
    (acc, cat) => {
      const items = packingList.items.filter((i) => i.category === cat);
      if (items.length > 0) {
        acc[cat] = items;
      }
      return acc;
    },
    {}
  );

  const totalItems = packingList.items.length;
  const checkedCount = packingList.items.filter((i) => i.checked).length;

  return (
    <div className="rounded-xl bg-surface border border-ink-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-sora text-lg text-ink-100">Packing List</h3>
          <p className="text-sm text-ink-400 font-dm-mono mt-0.5">
            {checkedCount}/{totalItems} packed
          </p>
        </div>
        <button
          onClick={() => generate(true)}
          disabled={loading}
          className="text-sm text-ink-300 hover:text-ink-100 transition-colors"
        >
          {loading ? "Regenerating..." : "Regenerate"}
        </button>
      </div>

      {error && (
        <p className="text-sm text-error mb-3">{error}</p>
      )}

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-ink-700 mb-5 overflow-hidden">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${totalItems > 0 ? (checkedCount / totalItems) * 100 : 0}%` }}
        />
      </div>

      {/* Categorized items */}
      <div className="space-y-5">
        {Object.entries(grouped).map(([category, items]) => (
          <div key={category}>
            <h4 className="text-xs font-dm-mono text-ink-400 uppercase tracking-wider mb-2">
              {CATEGORY_LABELS[category]}
            </h4>
            <ul className="space-y-1.5">
              {items.map((item) => (
                <li key={item.id} className="flex items-center gap-2">
                  <button
                    onClick={() => toggleItem(item.id, !item.checked)}
                    disabled={checking === item.id}
                    className={`flex-shrink-0 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                      item.checked
                        ? "bg-accent border-accent"
                        : "border-ink-700 hover:border-ink-400"
                    }`}
                    aria-label={`${item.checked ? "Uncheck" : "Check"} ${item.text}`}
                  >
                    {item.checked && (
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M2.5 6L5 8.5L9.5 3.5"
                          stroke="white"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </button>
                  <ClaimPill
                    item={item}
                    currentUserId={currentUserId}
                    members={memberMap}
                    onClaim={claimItem}
                    onUnclaim={unclaimItem}
                  />
                  <span
                    className={`text-sm transition-colors ${
                      item.checked ? "text-ink-400 line-through" : "text-ink-200"
                    }`}
                  >
                    {item.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
