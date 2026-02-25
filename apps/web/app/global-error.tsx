"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily:
            "'Sora', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          backgroundColor: "#FAF8F5",
          color: "#1A1815",
        }}
      >
        <div style={{ textAlign: "center", maxWidth: 480, padding: "0 24px" }}>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 600,
              marginBottom: 8,
              color: "#1A1815",
            }}
          >
            Something went wrong
          </h1>
          <p
            style={{
              fontSize: 15,
              color: "#6B6560",
              marginBottom: 24,
              lineHeight: 1.5,
            }}
          >
            An unexpected error occurred. Our team has been notified.
          </p>
          {error.digest && (
            <p
              style={{
                fontSize: 12,
                fontFamily: "'DM Mono', monospace",
                color: "#9B9590",
                marginBottom: 24,
              }}
            >
              Reference: {error.digest}
            </p>
          )}
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              onClick={reset}
              style={{
                padding: "10px 24px",
                fontSize: 14,
                fontWeight: 500,
                fontFamily: "'Sora', sans-serif",
                color: "#FFFFFF",
                backgroundColor: "#C4694F",
                border: "none",
                borderRadius: 8,
                cursor: "pointer",
              }}
            >
              Try again
            </button>
            <a
              href="/"
              style={{
                padding: "10px 24px",
                fontSize: 14,
                fontWeight: 500,
                fontFamily: "'Sora', sans-serif",
                color: "#6B6560",
                backgroundColor: "transparent",
                border: "1px solid #D5D0CC",
                borderRadius: 8,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
              }}
            >
              Go home
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}
