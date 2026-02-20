"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";

export default function AuthErrorPage() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      gap: "2rem"
    }}>
      <h1>Authentication Error</h1>
      <p>Error: {error || "Unknown error occurred"}</p>
      <Link href="/auth/signin">
        <button
          style={{
            padding: "12px 24px",
            fontSize: "16px",
            cursor: "pointer",
            backgroundColor: "#4285f4",
            color: "white",
            border: "none",
            borderRadius: "4px",
          }}
        >
          Back to Sign In
        </button>
      </Link>
    </div>
  );
}
