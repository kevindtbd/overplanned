"use client";

/**
 * InviteJoinButton — handles the join / sign-in action on the invite page.
 *
 * If the user is signed in: calls the join API endpoint then redirects to the trip.
 * If not signed in: redirects to Google OAuth with callbackUrl pointing back here,
 *                   so after auth they land on the invite page and can join.
 */

import { useState } from "react";
import { signIn } from "next-auth/react";

interface Props {
  token: string;
  tripId: string;
  isSignedIn: boolean;
  callbackUrl: string;
}

export function InviteJoinButton({
  token,
  tripId,
  isSignedIn,
  callbackUrl,
}: Props) {
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleJoin = async () => {
    if (!isSignedIn) {
      await signIn("google", { callbackUrl });
      return;
    }

    setState("loading");
    setErrorMessage(null);

    try {
      const res = await fetch(
        `/api/trips/${encodeURIComponent(tripId)}/join?token=${encodeURIComponent(token)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        }
      );

      if (res.ok) {
        window.location.href = `/trip/${tripId}`;
        return;
      }

      const json = await res.json().catch(() => null);
      const msg =
        json?.error?.message ||
        "Something went wrong. Please try again or ask the organizer for a new invite.";
      setErrorMessage(msg);
      setState("error");
    } catch {
      setErrorMessage(
        "Unable to connect. Check your connection and try again."
      );
      setState("error");
    }
  };

  const label = !isSignedIn
    ? "Sign in with Google to join"
    : state === "loading"
    ? "Joining..."
    : "Join this trip";

  return (
    <div>
      <button
        onClick={handleJoin}
        disabled={state === "loading"}
        style={{
          display: "block",
          width: "100%",
          padding: "0.75rem 1.5rem",
          backgroundColor:
            state === "loading"
              ? "var(--color-warm-border)"
              : "var(--color-terracotta)",
          color: state === "loading" ? "var(--color-warm-text-secondary)" : "#fff",
          border: "none",
          borderRadius: "0.625rem",
          fontFamily: "var(--font-sora), system-ui, sans-serif",
          fontWeight: 600,
          fontSize: "0.9375rem",
          cursor: state === "loading" ? "not-allowed" : "pointer",
          transition: "background-color 150ms ease",
          textAlign: "center",
        }}
        aria-busy={state === "loading"}
      >
        {label}
      </button>

      {state === "error" && errorMessage && (
        <p
          role="alert"
          style={{
            marginTop: "0.75rem",
            fontFamily: "var(--font-dm-mono), monospace",
            fontSize: "0.75rem",
            color: "#b91c1c",
            textAlign: "center",
          }}
        >
          {errorMessage}
        </p>
      )}
    </div>
  );
}
