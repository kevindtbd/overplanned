"use client";

import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";

export default function SignInPage() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard";

  const handleGoogleSignIn = async () => {
    await signIn("google", { callbackUrl });
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      gap: "2rem"
    }}>
      <h1>Sign In to Overplanned</h1>
      <button
        onClick={handleGoogleSignIn}
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
        Sign in with Google
      </button>
    </div>
  );
}
