/**
 * /s/[token] — Public read-only shared trip itinerary
 *
 * Server component with client-side import functionality.
 *
 * Security:
 * - CSP allows Next.js hydration for interactive import button.
 * - All strings rendered via React (JSX), which HTML-encodes by default —
 *   no dangerouslySetInnerHTML anywhere.
 * - Token is validated server-side; no user data is exposed.
 * - No affiliate links. No emoji.
 * - Image src is from activityNode.primaryImageUrl (Unsplash only per design rules).
 *   We use next/image with a restricted domain list in next.config.js.
 */

import type { Metadata } from "next";
import Image from "next/image";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { ImportButton } from "./ImportButton";

// ---------------------------------------------------------------------------
// CSP header — updated to allow Next.js scripts for import functionality
// ---------------------------------------------------------------------------

export async function generateStaticParams() {
  // Dynamic — no static params
  return [];
}

// Next.js 14 headers export (applied at the segment level)
export const headers = {
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https://images.unsplash.com data:; connect-src 'self'; frame-ancestors 'none';",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ActivityPreview {
  id: string;
  name: string;
  canonicalName: string;
  category: string;
  subcategory?: string | null;
  neighborhood?: string | null;
  priceLevel?: number | null;
  primaryImageUrl?: string | null;
  descriptionShort?: string | null;
  latitude: number;
  longitude: number;
}

interface SlotPreview {
  id: string;
  dayNumber: number;
  sortOrder: number;
  slotType: string;
  status: string;
  startTime?: string | null;
  endTime?: string | null;
  durationMinutes?: number | null;
  activity?: ActivityPreview | null;
}

interface TripPreview {
  id: string;
  destination: string;
  city: string;
  country: string;
  timezone: string;
  startDate: string;
  endDate: string;
  status: string;
  mode: string;
}

interface SharedTripData {
  trip: TripPreview;
  slotsByDay: Record<string, SlotPreview[]>;
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
  const data = await fetchSharedTrip(params.token);
  if (!data) {
    return { title: "Trip not found — Overplanned" };
  }
  return {
    title: `${data.trip.destination} Itinerary — Overplanned`,
    description: `A curated itinerary for ${data.trip.city}, ${data.trip.country}.`,
    // Prevent indexing of shared trips
    robots: { index: false, follow: false },
  };
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchSharedTrip(
  token: string
): Promise<SharedTripData | null> {
  // Sanitize token before using in URL
  const safeToken = token.replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 64);
  if (safeToken.length < 10) return null;

  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || ""}/api/shared/${encodeURIComponent(safeToken)}`,
      {
        // Shared trips should be fresh — 60 second revalidation
        next: { revalidate: 60 },
      }
    );

    if (!res.ok) return null;
    const json = await res.json();

    // API returns unwrapped data directly
    if (!json.trip || !json.slotsByDay) return null;
    return json as SharedTripData;
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

function formatTime(iso: string, timezone: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: timezone,
  });
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function priceLevelDots(level: number): string {
  return "$".repeat(Math.min(Math.max(level, 1), 4));
}

function getDayLabel(
  dayNumber: number,
  startDate: string,
  timezone: string
): string {
  const start = new Date(startDate);
  const day = new Date(start);
  day.setDate(start.getDate() + dayNumber - 1);
  return formatDate(day.toISOString(), timezone);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function SharedTripPage({
  params,
}: {
  params: { token: string };
}) {
  const data = await fetchSharedTrip(params.token);
  const session = await getServerSession(authOptions);

  if (!data) {
    return <NotFound />;
  }

  const { trip, slotsByDay } = data;
  const sortedDays = Object.keys(slotsByDay)
    .map(Number)
    .sort((a, b) => a - b);

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
          <ImportButton
            token={params.token}
            isSignedIn={!!session}
            currentUrl={`/s/${params.token}`}
          />
        </div>
      </header>

      {/* Hero */}
      <section
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "2.5rem 1.5rem 2rem",
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

        <div
          style={{
            display: "flex",
            gap: "1.5rem",
            flexWrap: "wrap",
          }}
        >
          <MetaItem
            label="Dates"
            value={`${formatDate(trip.startDate, trip.timezone)} — ${formatDate(trip.endDate, trip.timezone)}`}
          />
          <MetaItem label="Days" value={String(sortedDays.length)} />
        </div>
      </section>

      {/* Divider */}
      <div
        style={{
          maxWidth: "720px",
          margin: "0 auto 2rem",
          padding: "0 1.5rem",
        }}
      >
        <div
          style={{
            height: "1px",
            backgroundColor: "var(--ink-700)",
          }}
        />
      </div>

      {/* Itinerary */}
      <main
        style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "0 1.5rem 4rem",
        }}
      >
        {sortedDays.map((dayNumber) => {
          const slots = slotsByDay[String(dayNumber)] ?? [];
          const dayLabel = getDayLabel(dayNumber, trip.startDate, trip.timezone);

          return (
            <section key={dayNumber} style={{ marginBottom: "3rem" }}>
              {/* Day heading */}
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "0.75rem",
                  marginBottom: "1.25rem",
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
                <h2
                  style={{
                    fontSize: "1.125rem",
                    fontWeight: 600,
                    color: "var(--ink-100)",
                  }}
                >
                  {dayLabel}
                </h2>
              </div>

              {/* Slot list */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.875rem",
                }}
              >
                {slots.map((slot) => (
                  <SlotCard
                    key={slot.id}
                    slot={slot}
                    timezone={trip.timezone}
                  />
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
            This itinerary is still being planned.
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
          -- behavioral-driven travel planning
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

function SlotCard({
  slot,
  timezone,
}: {
  slot: SlotPreview;
  timezone: string;
}) {
  const activity = slot.activity;
  const hasImage =
    activity?.primaryImageUrl &&
    activity.primaryImageUrl.startsWith("https://images.unsplash.com");

  return (
    <div
      style={{
        backgroundColor: "var(--bg-surface)",
        border: "1px solid var(--ink-700)",
        borderRadius: "0.875rem",
        overflow: "hidden",
        display: "flex",
        gap: 0,
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
            src={activity!.primaryImageUrl!}
            alt={activity!.name}
            fill
            sizes="100px"
            style={{ objectFit: "cover" }}
            unoptimized={false}
          />
        </div>
      )}

      {/* Content column */}
      <div style={{ padding: "1rem", flex: 1, minWidth: 0 }}>
        {/* Time + type row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            marginBottom: "0.375rem",
          }}
        >
          {slot.startTime && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6875rem",
                fontWeight: 500,
                color: "var(--accent)",
              }}
            >
              {formatTime(slot.startTime, timezone)}
            </span>
          )}
          {slot.durationMinutes && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6875rem",
                color: "var(--ink-400)",
              }}
            >
              {formatDuration(slot.durationMinutes)}
            </span>
          )}
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
            {slot.slotType}
          </span>
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
          {activity?.name ?? "Activity"}
        </p>

        {/* Location + category meta */}
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {activity?.neighborhood && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6875rem",
                color: "var(--ink-400)",
              }}
            >
              {activity.neighborhood}
            </span>
          )}
          {activity?.category && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6875rem",
                color: "var(--ink-400)",
                textTransform: "capitalize",
              }}
            >
              {activity.category.replace("_", " ")}
            </span>
          )}
          {activity?.priceLevel != null && activity.priceLevel > 0 && (
            <span
              style={{
                fontFamily: "var(--font-dm-mono), monospace",
                fontSize: "0.6875rem",
                color: "var(--ink-400)",
              }}
            >
              {priceLevelDots(activity.priceLevel)}
            </span>
          )}
        </div>

        {/* Description */}
        {activity?.descriptionShort && (
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
            {activity.descriptionShort}
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
        This itinerary is no longer available
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
        This share link expired or was removed. Ask the organizer for a new one.
      </p>
    </div>
  );
}
