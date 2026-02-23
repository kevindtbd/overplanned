"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface ImportButtonProps {
  token: string;
  isSignedIn: boolean;
  currentUrl: string;
}

export function ImportButton({
  token,
  isSignedIn,
  currentUrl,
}: ImportButtonProps) {
  const router = useRouter();
  const [isImporting, setIsImporting] = useState(false);

  const handleImport = async () => {
    if (!isSignedIn) {
      // Redirect to sign-in with callback to this page
      const callbackUrl = encodeURIComponent(currentUrl);
      router.push(`/auth/signin?callbackUrl=${callbackUrl}`);
      return;
    }

    setIsImporting(true);
    try {
      const res = await fetch(`/api/shared/${token}/import`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!res.ok) {
        throw new Error("Import failed");
      }

      const data = await res.json();

      // Redirect to the newly created trip
      if (data.tripId) {
        router.push(`/trip/${data.tripId}`);
      } else {
        throw new Error("No trip ID returned");
      }
    } catch (error) {
      console.error("Import error:", error);
      setIsImporting(false);
      // TODO: Show error toast
    }
  };

  return (
    <button
      onClick={handleImport}
      disabled={isImporting}
      style={{
        fontFamily: "var(--font-dm-mono), monospace",
        fontSize: "0.6875rem",
        fontWeight: 500,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: isImporting ? "var(--ink-500)" : "var(--bg-base)",
        backgroundColor: isImporting ? "var(--ink-700)" : "var(--accent)",
        padding: "0.5rem 1rem",
        borderRadius: "0.5rem",
        border: "none",
        cursor: isImporting ? "not-allowed" : "pointer",
        transition: "background-color 0.2s",
      }}
    >
      {isImporting ? "Importing..." : isSignedIn ? "Import to my trips" : "Sign in to import"}
    </button>
  );
}
