"use client";

// VibeChips — Displays vibe tag chips for an activity slot.
// Usage: <VibeChips tags={[{ slug: "late-night", name: "Late Night" }]} primarySlug="late-night" />

export interface VibeTagDisplay {
  slug: string;
  name: string;
}

interface VibeChipsProps {
  tags: VibeTagDisplay[];
  /** The slug of the primary vibe tag (rendered with terracotta accent) */
  primarySlug?: string;
  /** Max chips to show before collapsing with "+N" */
  maxVisible?: number;
}

export function VibeChips({
  tags,
  primarySlug,
  maxVisible = 4,
}: VibeChipsProps) {
  if (!tags.length) return null;

  const visible = tags.slice(0, maxVisible);
  const overflowCount = tags.length - maxVisible;

  return (
    <div className="flex flex-wrap gap-1.5" role="list" aria-label="Vibe tags">
      {visible.map((tag) => {
        const isPrimary = tag.slug === primarySlug;
        return (
          <span
            key={tag.slug}
            role="listitem"
            className={`
              inline-flex items-center px-2 py-0.5 rounded-full
              font-dm-mono text-[11px] uppercase tracking-wider
              transition-colors duration-150
              ${
                isPrimary
                  ? "bg-terracotta-100 text-terracotta-700 border border-terracotta-300"
                  : "bg-warm-surface text-warm-text-secondary border border-warm-border"
              }
            `}
          >
            {tag.name}
          </span>
        );
      })}
      {overflowCount > 0 && (
        <span
          role="listitem"
          className="
            inline-flex items-center px-2 py-0.5 rounded-full
            font-dm-mono text-[11px] uppercase tracking-wider
            bg-warm-surface text-warm-text-secondary border border-warm-border
          "
          aria-label={`${overflowCount} more tags`}
        >
          +{overflowCount}
        </span>
      )}
    </div>
  );
}
