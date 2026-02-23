"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------- Vibe Tag Groups ----------

const VIBE_GROUPS = [
  {
    heading: "Pace & Energy",

    tags: [
      { slug: "high-energy", label: "High energy" },
      { slug: "slow-burn", label: "Slow burn" },
      { slug: "immersive", label: "Immersive" },
    ],
  },
  {
    heading: "Discovery Style",

    tags: [
      { slug: "hidden-gem", label: "Hidden gems" },
      { slug: "iconic-worth-it", label: "Iconic & worth it" },
      { slug: "locals-only", label: "Locals only" },
      { slug: "offbeat", label: "Offbeat & unexpected" },
    ],
  },
  {
    heading: "Food & Drink",

    tags: [
      { slug: "destination-meal", label: "Destination meals" },
      { slug: "street-food", label: "Street food" },
      { slug: "local-institution", label: "Local institutions" },
      { slug: "drinks-forward", label: "Drinks-forward spots" },
    ],
  },
  {
    heading: "Activity Type",

    tags: [
      { slug: "nature-immersive", label: "Nature immersive" },
      { slug: "urban-exploration", label: "Urban exploration" },
      { slug: "deep-history", label: "Deep history" },
      { slug: "contemporary-culture", label: "Contemporary culture" },
      { slug: "hands-on", label: "Hands-on experiences" },
      { slug: "scenic", label: "Scenic views" },
    ],
  },
  {
    heading: "Social & Time",

    tags: [
      { slug: "late-night", label: "Late night" },
      { slug: "early-morning", label: "Early morning" },
      { slug: "solo-friendly", label: "Solo-friendly" },
      { slug: "group-friendly", label: "Group-friendly" },
      { slug: "social-scene", label: "Social scene" },
      { slug: "low-interaction", label: "Low interaction" },
    ],
  },
] as const;

// ---------- Icons ----------

function CheckIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}


// ---------- Types ----------

type InterestsState = {
  vibePreferences: string[];
  travelStyleNote: string | null;
};

const DEFAULTS: InterestsState = {
  vibePreferences: [],
  travelStyleNote: null,
};

const MAX_NOTE_LENGTH = 500;

// ---------- Component ----------

export function TravelInterests() {
  const [state, setState] = useState<InterestsState>(DEFAULTS);
  const [noteValue, setNoteValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedVibesRef = useRef<string[]>([]);
  const lastSavedNoteRef = useRef<string | null>(null);

  // ---------- Fetch on mount ----------

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/preferences");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          const vibes: string[] = data.vibePreferences ?? [];
          const note: string | null = data.travelStyleNote ?? null;
          setState({ vibePreferences: vibes, travelStyleNote: note });
          setNoteValue(note ?? "");
          lastSavedVibesRef.current = vibes;
          lastSavedNoteRef.current = note;
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ---------- Debounced vibe save ----------

  const saveVibes = useCallback((nextVibes: string[]) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch("/api/settings/preferences", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ vibePreferences: nextVibes }),
        });
        if (!res.ok) throw new Error();
        lastSavedVibesRef.current = nextVibes;
      } catch {
        // Revert on failure
        setState((prev) => ({
          ...prev,
          vibePreferences: lastSavedVibesRef.current,
        }));
      }
    }, 500);
  }, []);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // ---------- Textarea blur save ----------

  const saveNote = useCallback(async (value: string) => {
    const trimmed = value.trim() || null;
    try {
      const res = await fetch("/api/settings/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ travelStyleNote: trimmed }),
      });
      if (!res.ok) throw new Error();
      lastSavedNoteRef.current = trimmed;
      setState((prev) => ({ ...prev, travelStyleNote: trimmed }));
    } catch {
      // Revert on failure
      const reverted = lastSavedNoteRef.current ?? "";
      setNoteValue(reverted);
      setState((prev) => ({ ...prev, travelStyleNote: lastSavedNoteRef.current }));
    }
  }, []);

  // ---------- Handlers ----------

  function toggleVibe(slug: string) {
    setState((prev) => {
      const arr = prev.vibePreferences;
      const next = arr.includes(slug)
        ? arr.filter((v) => v !== slug)
        : [...arr, slug];
      const updated = { ...prev, vibePreferences: next };
      saveVibes(next);
      return updated;
    });
  }

  function handleNoteBlur() {
    // Only save if value changed from last saved
    const current = noteValue.trim() || null;
    if (current !== lastSavedNoteRef.current) {
      saveNote(noteValue);
    }
  }

  // ---------- Render ----------

  const remaining = MAX_NOTE_LENGTH - noteValue.length;

  return (
    <section id="travel-interests" aria-labelledby="travel-interests-heading">
      <h2
        id="travel-interests-heading"
        className="font-sora text-lg font-medium text-ink-100 mb-4"
      >
        Travel Interests
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-4">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            <div className="h-4 w-32 bg-warm-border rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-8 w-24 bg-warm-border rounded-lg" />
              ))}
            </div>
            <div className="h-4 w-28 bg-warm-border rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-8 w-28 bg-warm-border rounded-lg" />
              ))}
            </div>
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">
            Failed to load travel interests.
          </p>
        ) : (
          <>
            {/* Vibe tag groups — always expanded */}
            {VIBE_GROUPS.map((group, groupIdx) => (
              <div key={group.heading}>
                {groupIdx > 0 && (
                  <div className="border-t border-warm-border mb-4" />
                )}
                <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                  {group.heading}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {group.tags.map((tag) => {
                    const checked = state.vibePreferences.includes(tag.slug);
                    return (
                      <label
                        key={tag.slug}
                        className={`
                          flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                          font-sora text-sm transition-colors
                          ${
                            checked
                              ? "border-accent bg-accent/10 text-ink-100"
                              : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                          }
                        `}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleVibe(tag.slug)}
                          className="sr-only"
                        />
                        {checked && <CheckIcon />}
                        {tag.label}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}

            {/* Divider */}
            <div className="border-t border-warm-border" />

            {/* Free-form textarea */}
            <div>
              <label
                htmlFor="travel-style-note"
                className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2 block"
              >
                Anything else about how you travel?
              </label>
              <textarea
                id="travel-style-note"
                value={noteValue}
                onChange={(e) => setNoteValue(e.target.value)}
                onBlur={handleNoteBlur}
                placeholder="I always hunt for the best coffee spot in every city..."
                maxLength={MAX_NOTE_LENGTH}
                rows={3}
                className="w-full rounded-lg border border-warm-border bg-transparent px-3 py-2 font-sora text-sm text-ink-100 placeholder:text-ink-500 resize-none focus:outline-none focus:border-accent transition-colors"
              />
              {remaining <= 100 && (
                <p
                  className={`text-right font-dm-mono text-[10px] tabular-nums ${
                    remaining <= 20 ? "text-[var(--error)]" : "text-ink-400"
                  }`}
                >
                  {remaining}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
