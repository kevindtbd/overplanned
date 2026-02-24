/**
 * /memory/[token] — Public read-only trip memory page
 *
 * Server component. No auth required.
 *
 * Security:
 * - CSP: script-src 'none' enforced via headers export.
 * - All strings rendered via React (JSX), which HTML-encodes by default —
 *   no dangerouslySetInnerHTML anywhere.
 * - Token is validated server-side; no user data is exposed.
 * - Rate limiting expected at API layer.
 * - Image src restricted to Unsplash + GCS public URLs via CSP img-src.
 * - No emoji anywhere.
 */

import type { Metadata } from "next";
import Image from "next/image";

// ---------------------------------------------------------------------------
// CSP header — script-src 'none' enforced via next.config.js headers()
// for /memory/:token routes. No page-level export needed.
// ---------------------------------------------------------------------------

export async function generateStaticParams() {
  return [];
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MemoryPhoto {
  slotId: string;
  activityName: string;
  imageUrl: string;
}

interface MemoryHighlight {
  id: string;
  dayNumber: number;
  activityName: string;
  category: string;
  neighborhood?: string | null;
  primaryImageUrl?: string | null;
  descriptionShort?: string | null;
  status: "completed" | "skipped" | "loved";
}

interface MemoryStats {
  totalDays: number;
  totalSlots: number;
  completedSlots: number;
  skippedSlots: number;
  lovedSlots: number;
}

interface TripMemoryData {
  trip: {
    id: string;
    destination: string;
    city: string;
    country: string;
    timezone: string;
    startDate: string;
    endDate: string;
    coverImageUrl?: string | null;
  };
  stats: MemoryStats;
  photos: MemoryPhoto[];
  highlights: MemoryHighlight[];
  sharedAt: string;
}

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------

export async function generateMetadata({
  params,
}: {
  params: { token: string };
}): Promise<Metadata> {
  const data = await fetchTripMemory(params.token);
  if (!data) {
    return { title: "Memory not found — Overplanned" };
  }
  return {
    title: `${data.trip.destination} Memories — Overplanned`,
    description: `Trip memories from ${data.trip.city}, ${data.trip.country}.`,
    robots: { index: false, follow: false },
  };
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchTripMemory(
  token: string
): Promise<TripMemoryData | null> {
  const apiBase =
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "";

  // Sanitize token — alphanumeric, hyphens, underscores only; max 64 chars
  const safeToken = token.replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 64);
  if (safeToken.length < 10) return null;

  try {
    const res = await fetch(
      `${apiBase}/memory/${encodeURIComponent(safeToken)}`,
      { next: { revalidate: 60 } }
    );

    if (!res.ok) return null;
    const json = await res.json();
    if (!json.success || !json.data) return null;
    return json.data as TripMemoryData;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string, timezone: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "long",
    day: "numeric",
    timeZone: timezone,
  });
}

function formatDateShort(iso: string): string {
  try {
    const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
    return new Date(iso).toLocaleDateString("en-US", opts);
  } catch {
    return "";
  }
}

function formatDateRange(start: string, end: string): string {
  const s = formatDateShort(start);
  const e = new Date(end).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return `${s} - ${e}`;
}

function isAllowedImageSrc(url: string): boolean {
  return (
    url.startsWith("https://images.unsplash.com") ||
    url.startsWith("https://storage.googleapis.com")
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function TripMemoryPage({
  params,
}: {
  params: { token: string };
}) {
  const data = await fetchTripMemory(params.token);

  if (!data) {
    return <NotFound />;
  }

  const { trip, stats, photos, highlights } = data;
  const dateRange = formatDateRange(trip.startDate, trip.endDate);
  const completionRate =
    stats.totalSlots > 0
      ? Math.round((stats.completedSlots / stats.totalSlots) * 100)
      : 0;

  // Group highlights by day
  const highlightsByDay: Record<number, MemoryHighlight[]> = {};
  for (const h of highlights) {
    if (!highlightsByDay[h.dayNumber]) highlightsByDay[h.dayNumber] = [];
    highlightsByDay[h.dayNumber].push(h);
  }
  const sortedDays = Object.keys(highlightsByDay)
    .map(Number)
    .sort((a, b) => a - b);

  // Only render photos with allowed image sources
  const safePhotos = photos.filter((p) => isAllowedImageSrc(p.imageUrl));

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg-base)",
        color: "var(--ink-100)",
        fontFamily: "var(--font-sora), system-ui, sans-serif",
      }}
    >
      {/* Header */}
      <header
        style={{
          borderBottom: "1px solid var(--ink-700)",
          backgroundColor: "var(--bg-surface)",
          padding: "1.25rem 1.5rem",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div
          style={{
            maxWidth: "720px",
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-sora), system-ui, sans-serif",
              fontWeight: 700,
              fontSize: "1rem",
              color: "var(--accent)",
              letterSpacing: "-0.01em",
            }}
          >
            overplanned
          </span>
          <span
            style={{
              fontFamily: "var(--font-dm-mono), monospace",
              fontSize: "0.6875rem",
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--ink-400)",
            }}
          >
            Trip memory
          </span>
        </div>
      </header>

      {/* Hero — cover image + trip info overlay */}
      {trip.coverImageUrl && isAllowedImageSrc(trip.coverImageUrl) && (
        <div
          style={{
            maxWidth: "720px",
            margin: "0 auto",
            position: "relative",
            height: "220px",
            overflow: "hidden",
          }}
        >
          <Image
            src={trip.coverImageUrl}
            alt=""
            fill
            sizes="720px"
            style={{ objectFit: "cover" }}
            priority
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(to top, var(--bg-base) 0%, transparent 60%)",
            }}
          />
        </div>
      )}

      {/* Trip header */}
      <section
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: trip.coverImageUrl ? "0 1.5rem 0" : "2.5rem 1.5rem 0",
          position: "relative",
          marginTop: trip.coverImageUrl ? "-3rem" : "0",
          zIndex: 1,
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-dm-mono), monospace",
            fontSize: "0.6875rem",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            color: "var(--accent)",
            marginBottom: "0.625rem",
          }}
        >
          {trip.city}, {trip.country}
        </p>

        <h1
          style={{
            fontSize: "2.25rem",
            fontWeight: 700,
            lineHeight: 1.1,
            letterSpacing: "-0.02em",
            color: "var(--ink-100)",
            marginBottom: "1rem",
          }}
        >
          {trip.destination}
        </h1>

        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
          <MetaItem label="Dates" value={dateRange} />
          <MetaItem label="Days" value={String(stats.totalDays)} />
          <MetaItem
            label="Completion"
            value={`${completionRate}%`}
          />
        </div>
      </section>

      {/* Stats row */}
      <section
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "1.5rem 1.5rem 0",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "0.75rem",
          }}
        >
          <StatCard label="Planned" value={stats.totalSlots} variant="default" />
          <StatCard label="Completed" value={stats.completedSlots} variant="success" />
          <StatCard label="Skipped" value={stats.skippedSlots} variant="warn" />
          <StatCard label="Loved" value={stats.lovedSlots} variant="accent" />
        </div>
      </section>

      {/* Divider */}
      <Divider />

      {/* Photo strip */}
      {safePhotos.length > 0 && (
        <section
          style={{
            maxWidth: "720px",
            margin: "0 auto",
            padding: "0 1.5rem 2rem",
          }}
        >
          <SectionLabel>Trip photos</SectionLabel>
          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              overflowX: "auto",
              paddingBottom: "0.5rem",
            }}
          >
            {safePhotos.map((photo) => (
              <div
                key={photo.slotId}
                style={{
                  flexShrink: 0,
                  width: "144px",
                }}
              >
                <div
                  style={{
                    width: "144px",
                    height: "144px",
                    borderRadius: "0.75rem",
                    overflow: "hidden",
                    border: "1px solid var(--ink-700)",
                    backgroundColor: "var(--bg-surface)",
                  }}
                >
                  <Image
                    src={photo.imageUrl}
                    alt={photo.activityName}
                    width={144}
                    height={144}
                    style={{ objectFit: "cover", width: "100%", height: "100%" }}
                  />
                </div>
                <p
                  style={{
                    fontFamily: "var(--font-sora), system-ui, sans-serif",
                    fontSize: "0.75rem",
                    fontWeight: 500,
                    color: "var(--ink-100)",
                    textAlign: "center",
                    marginTop: "0.5rem",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {photo.activityName}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Highlights by day */}
      <main
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "0 1.5rem 4rem",
        }}
      >
        {safePhotos.length > 0 && <Divider inline />}

        <SectionLabel>Highlights</SectionLabel>

        {sortedDays.map((dayNumber) => {
          const dayHighlights = highlightsByDay[dayNumber] ?? [];

          return (
            <section key={dayNumber} style={{ marginBottom: "2.5rem" }}>
              {/* Day heading */}
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "0.75rem",
                  marginBottom: "1rem",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-dm-mono), monospace",
                    fontSize: "0.6875rem",
                    fontWeight: 500,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    color: "var(--accent)",
                  }}
                >
                  Day {dayNumber}
                </span>
              </div>

              {/* Highlight cards */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                {dayHighlights.map((h) => (
                  <HighlightCard key={h.id} highlight={h} />
                ))}
              </div>
            </section>
          );
        })}

        {sortedDays.length === 0 && (
          <p
            style={{
              fontFamily: "var(--font-dm-mono), monospace",
              fontSize: "0.875rem",
              color: "var(--ink-400)",
              textAlign: "center",
              paddingTop: "2rem",
            }}
          >
            No highlights to show yet.
          </p>
        )}
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--ink-700)",
          padding: "1.5rem",
          textAlign: "center",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-dm-mono), monospace",
            fontSize: "0.6875rem",
            color: "var(--ink-400)",
          }}
        >
          Shared via{" "}
          <span style={{ color: "var(--accent)" }}>overplanned</span>{" "}
          &mdash; behavioral-driven travel planning
        </p>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p
        style={{
          fontFamily: "var(--font-dm-mono), monospace",
          fontSize: "0.6875rem",
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--ink-400)",
          marginBottom: "0.2rem",
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontFamily: "var(--font-sora), system-ui, sans-serif",
          fontSize: "0.9375rem",
          fontWeight: 500,
          color: "var(--ink-100)",
        }}
      >
        {value}
      </p>
    </div>
  );
}

function StatCard({
  label,
  value,
  variant,
}: {
  label: string;
  value: number;
  variant: "default" | "success" | "warn" | "accent";
}) {
  const bgMap = {
    default: "var(--bg-surface)",
    success: "#ecfdf5",
    warn: "#fffbeb",
    accent: "#fdf2f0",
  };
  const colorMap = {
    default: "var(--ink-100)",
    success: "#047857",
    warn: "#b45309",
    accent: "var(--accent)",
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "0.75rem 0.5rem",
        borderRadius: "0.75rem",
        backgroundColor: bgMap[variant],
        border: "1px solid var(--ink-700)",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-sora), system-ui, sans-serif",
          fontWeight: 700,
          fontSize: "1.25rem",
          lineHeight: 1,
          color: colorMap[variant],
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontFamily: "var(--font-dm-mono), monospace",
          fontSize: "0.625rem",
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--ink-400)",
          marginTop: "0.375rem",
        }}
      >
        {label}
      </span>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: "var(--font-sora), system-ui, sans-serif",
        fontSize: "1.125rem",
        fontWeight: 600,
        color: "var(--ink-100)",
        marginBottom: "1.25rem",
      }}
    >
      {children}
    </h2>
  );
}

function Divider({ inline }: { inline?: boolean }) {
  return (
    <div
      style={{
        maxWidth: inline ? "100%" : "720px",
        margin: inline ? "0 0 1.5rem" : "0 auto",
        padding: inline ? "0" : "0 1.5rem",
        marginTop: inline ? "0" : "1.5rem",
        marginBottom: "1.5rem",
      }}
    >
      <div
        style={{
          height: "1px",
          backgroundColor: "var(--ink-700)",
        }}
      />
    </div>
  );
}

function HighlightCard({ highlight }: { highlight: MemoryHighlight }) {
  const hasImage =
    highlight.primaryImageUrl && isAllowedImageSrc(highlight.primaryImageUrl);

  const statusStyle = {
    completed: {
      bg: "#ecfdf5",
      color: "#047857",
      label: "completed",
    },
    skipped: {
      bg: "#f3f4f6",
      color: "#6b7280",
      label: "skipped",
    },
    loved: {
      bg: "#fdf2f0",
      color: "var(--accent)",
      label: "loved",
    },
  }[highlight.status] ?? {
    bg: "#f3f4f6",
    color: "#6b7280",
    label: highlight.status,
  };

  return (
    <div
      style={{
        backgroundColor: "var(--bg-surface)",
        border: "1px solid var(--ink-700)",
        borderRadius: "0.875rem",
        overflow: "hidden",
        display: "flex",
      }}
    >
      {/* Image column */}
      {hasImage && (
        <div
          style={{
            width: "100px",
            minWidth: "100px",
            position: "relative",
            flexShrink: 0,
          }}
        >
          <Image
            src={highlight.primaryImageUrl!}
            alt={highlight.activityName}
            fill
            sizes="100px"
            style={{ objectFit: "cover" }}
          />
        </div>
      )}

      {/* Content column */}
      <div style={{ padding: "1rem", flex: 1, minWidth: 0 }}>
        {/* Status + category row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            marginBottom: "0.375rem",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-dm-mono), monospace",
              fontSize: "0.6rem",
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: statusStyle.color,
              backgroundColor: statusStyle.bg,
              padding: "0.1rem 0.4rem",
              borderRadius: "0.25rem",
            }}
          >
            {statusStyle.label}
          </span>
          {highlight.category && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6rem",
                fontWeight: 500,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: "var(--ink-400)",
                backgroundColor: "var(--ink-700)",
                padding: "0.1rem 0.4rem",
                borderRadius: "0.25rem",
              }}
            >
              {highlight.category.replace("_", " ")}
            </span>
          )}
        </div>

        {/* Activity name */}
        <p
          style={{
            fontFamily: "var(--font-sora), system-ui, sans-serif",
            fontWeight: 600,
            fontSize: "0.9375rem",
            color: "var(--ink-100)",
            marginBottom: "0.25rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {highlight.activityName}
        </p>

        {/* Neighborhood */}
        {highlight.neighborhood && (
          <span
            style={{
              fontFamily: "var(--font-dm-mono), monospace",
              fontSize: "0.6875rem",
              color: "var(--ink-400)",
            }}
          >
            {highlight.neighborhood}
          </span>
        )}

        {/* Description */}
        {highlight.descriptionShort && (
          <p
            style={{
              fontFamily: "var(--font-sora), system-ui, sans-serif",
              fontSize: "0.8125rem",
              color: "var(--ink-400)",
              lineHeight: 1.5,
              marginTop: "0.5rem",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {highlight.descriptionShort}
          </p>
        )}
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg-base)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        textAlign: "center",
        fontFamily: "var(--font-sora), system-ui, sans-serif",
      }}
    >
      <span
        style={{
          fontWeight: 700,
          fontSize: "1.125rem",
          color: "var(--accent)",
          letterSpacing: "-0.01em",
          marginBottom: "2.5rem",
          display: "block",
        }}
      >
        overplanned
      </span>
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          color: "var(--ink-100)",
          marginBottom: "0.75rem",
        }}
      >
        This memory is no longer available
      </h1>
      <p
        style={{
          fontFamily: "var(--font-dm-mono), monospace",
          fontSize: "0.875rem",
          color: "var(--ink-400)",
          maxWidth: "360px",
          lineHeight: 1.6,
        }}
      >
        The memory link may have expired or been removed by the trip owner.
        Ask them for a new link.
      </p>
    </div>
  );
}
