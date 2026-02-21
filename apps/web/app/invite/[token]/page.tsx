/**
 * /invite/[token] — Invite landing page
 *
 * Server component: fetches trip preview from the API using the invite token.
 * If the user is already signed in, shows a "Join trip" action.
 * If not, shows "Sign in with Google to join".
 *
 * Security:
 * - Token is never echoed into script contexts.
 * - All user-facing strings come from the API response (sanitized server-side).
 * - No affiliate links. No emoji.
 */

import { headers } from "next/headers";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth/config";
import { InviteJoinButton } from "./InviteJoinButton";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InvitePreview {
  tripId: string;
  destination: string;
  city: string;
  country: string;
  startDate: string;
  endDate: string;
  memberCount: number;
  valid: boolean;
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchInvitePreview(
  token: string
): Promise<InvitePreview | null> {
  const apiBase =
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "";

  try {
    const res = await fetch(`${apiBase}/invites/preview/${encodeURIComponent(token)}`, {
      // Cache for 30 seconds — invite previews don't need to be real-time,
      // and this reduces DB load for shared links.
      next: { revalidate: 30 },
    });

    if (!res.ok) return null;

    const json = await res.json();
    if (!json.success || !json.data) return null;

    return json.data as InvitePreview;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateRange(startDate: string, endDate: string): string {
  const start = new Date(startDate);
  const end = new Date(endDate);

  const startStr = start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const endStr = end.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return `${startStr} — ${endStr}`;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface PageProps {
  params: { token: string };
}

export default async function InvitePage({ params }: PageProps) {
  const { token } = params;

  // Validate token format client-side before hitting API
  // base64url tokens are 43 chars; hard-limit to 64 to prevent log injection
  const sanitizedToken = token.replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 64);
  if (sanitizedToken.length < 10) {
    return <InvalidInvite />;
  }

  const [preview, session] = await Promise.all([
    fetchInvitePreview(sanitizedToken),
    getServerSession(authOptions),
  ]);

  if (!preview || !preview.valid) {
    return <InvalidInvite />;
  }

  const isSignedIn = !!session?.user;
  const callbackUrl = `/invite/${sanitizedToken}`;

  return (
    <main
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg-base)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
      }}
    >
      {/* Wordmark */}
      <div style={{ marginBottom: "3rem", textAlign: "center" }}>
        <span
          style={{
            fontFamily: "var(--font-sora), system-ui, sans-serif",
            fontWeight: 700,
            fontSize: "1.125rem",
            color: "var(--accent)",
            letterSpacing: "-0.01em",
          }}
        >
          overplanned
        </span>
      </div>

      {/* Card */}
      <div
        style={{
          width: "100%",
          maxWidth: "440px",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--ink-700)",
          borderRadius: "1rem",
          padding: "2rem",
          boxShadow: "0 4px 24px rgba(0,0,0,0.06)",
        }}
      >
        {/* Label */}
        <p
          style={{
            fontFamily: "var(--font-dm-mono), monospace",
            fontSize: "0.6875rem",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            color: "var(--ink-400)",
            marginBottom: "1rem",
          }}
        >
          You&apos;ve been invited
        </p>

        {/* Destination */}
        <h1
          style={{
            fontFamily: "var(--font-sora), system-ui, sans-serif",
            fontWeight: 700,
            fontSize: "1.875rem",
            lineHeight: 1.15,
            color: "var(--ink-100)",
            marginBottom: "0.375rem",
          }}
        >
          {preview.destination}
        </h1>

        {/* City, Country */}
        <p
          style={{
            fontFamily: "var(--font-dm-mono), monospace",
            fontSize: "0.875rem",
            color: "var(--ink-400)",
            marginBottom: "1.5rem",
          }}
        >
          {preview.city}, {preview.country}
        </p>

        {/* Divider */}
        <div
          style={{
            height: "1px",
            backgroundColor: "var(--ink-700)",
            marginBottom: "1.5rem",
          }}
        />

        {/* Trip meta */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
            marginBottom: "2rem",
          }}
        >
          <MetaCell
            label="Dates"
            value={formatDateRange(preview.startDate, preview.endDate)}
          />
          <MetaCell
            label="Members"
            value={`${preview.memberCount} ${preview.memberCount === 1 ? "person" : "people"}`}
          />
        </div>

        {/* CTA */}
        <InviteJoinButton
          token={sanitizedToken}
          tripId={preview.tripId}
          isSignedIn={isSignedIn}
          callbackUrl={callbackUrl}
        />

        {/* Fine print */}
        {!isSignedIn && (
          <p
            style={{
              marginTop: "1rem",
              fontFamily: "var(--font-dm-mono), monospace",
              fontSize: "0.6875rem",
              color: "var(--ink-400)",
              textAlign: "center",
              lineHeight: 1.5,
            }}
          >
            Google sign-in is required to join. Your account will be created
            automatically if you don&apos;t have one.
          </p>
        )}
      </div>

      {/* Footer */}
      <p
        style={{
          marginTop: "2rem",
          fontFamily: "var(--font-dm-mono), monospace",
          fontSize: "0.6875rem",
          color: "var(--ink-400)",
          textAlign: "center",
        }}
      >
        Invite links expire after 7 days and are single-use.
      </p>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetaCell({ label, value }: { label: string; value: string }) {
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
          marginBottom: "0.25rem",
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

function InvalidInvite() {
  return (
    <main
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg-base)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
        textAlign: "center",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-sora), system-ui, sans-serif",
          fontWeight: 700,
          fontSize: "1.125rem",
          color: "var(--accent)",
          letterSpacing: "-0.01em",
          marginBottom: "3rem",
          display: "block",
        }}
      >
        overplanned
      </span>

      <h1
        style={{
          fontFamily: "var(--font-sora), system-ui, sans-serif",
          fontWeight: 700,
          fontSize: "1.5rem",
          color: "var(--ink-100)",
          marginBottom: "0.75rem",
        }}
      >
        This invite is no longer valid
      </h1>
      <p
        style={{
          fontFamily: "var(--font-dm-mono), monospace",
          fontSize: "0.875rem",
          color: "var(--ink-400)",
          maxWidth: "340px",
        }}
      >
        The invite link may have expired, been revoked, or already been used.
        Ask the trip organizer to send a new one.
      </p>
    </main>
  );
}
