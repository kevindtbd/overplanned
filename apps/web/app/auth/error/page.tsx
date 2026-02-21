"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

/* ------------------------------------------------------------------ */
/*  SVG Warning Icon — terracotta-tinted triangle                      */
/* ------------------------------------------------------------------ */

function WarningIcon() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M24 4L2 42h44L24 4z"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <path
        d="M24 18v10"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="24" cy="34" r="1.5" fill="var(--accent)" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Error message mapping                                              */
/* ------------------------------------------------------------------ */

const ERROR_MESSAGES: Record<string, string> = {
  Configuration: "There is a problem with the server configuration.",
  AccessDenied: "You do not have permission to sign in.",
  Verification: "The verification link may have expired or already been used.",
  OAuthSignin: "Could not start the sign-in process. Please try again.",
  OAuthCallback: "Could not complete the sign-in process. Please try again.",
  OAuthCreateAccount: "Could not create your account. Please try again.",
  EmailCreateAccount: "Could not create your account. Please try again.",
  Callback: "Something went wrong during authentication.",
  OAuthAccountNotLinked: "This email is already associated with another sign-in method.",
  SessionRequired: "You need to be signed in to access this page.",
  Default: "An unexpected error occurred. Please try again.",
};

function getErrorMessage(error: string | null): string {
  if (!error) return ERROR_MESSAGES.Default;
  return ERROR_MESSAGES[error] || ERROR_MESSAGES.Default;
}

/* ------------------------------------------------------------------ */
/*  Error content (inner component using useSearchParams)              */
/* ------------------------------------------------------------------ */

function ErrorContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  return (
    <div className="min-h-screen bg-base flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Radial terracotta glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 60%, rgba(196,105,79,0.07) 0%, transparent 60%)",
        }}
      />

      {/* Card */}
      <div className="relative z-10 w-full max-w-[400px] bg-surface border border-ink-700 rounded-[20px] shadow-xl p-10 text-center">
        {/* Logo */}
        <div className="font-sora text-[20px] font-bold tracking-[-0.04em] text-ink-100 mb-8">
          overplanned<span className="text-accent">.</span>
        </div>

        {/* Warning icon */}
        <div className="flex justify-center mb-6">
          <WarningIcon />
        </div>

        {/* Heading */}
        <h1 className="font-lora text-[24px] font-medium italic text-ink-100 leading-tight mb-3">
          Something went wrong
        </h1>

        {/* Error message */}
        <p className="text-ink-400 text-[14px] font-light mb-8 leading-[1.6]">
          {getErrorMessage(error)}
        </p>

        {/* Try again button */}
        <Link
          href="/auth/signin"
          className="btn-primary inline-flex items-center justify-center gap-2 px-8 py-3 text-[14px] w-full no-underline"
        >
          Try again
        </Link>
      </div>

      {/* Back to home */}
      <Link
        href="/"
        className="relative z-10 mt-6 text-ink-500 text-[13px] hover:text-ink-300 transition-colors"
      >
        Back to home
      </Link>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page export with Suspense boundary                                 */
/* ------------------------------------------------------------------ */

export default function AuthErrorPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-base flex items-center justify-center">
          <div className="font-sora text-[20px] font-bold tracking-[-0.04em] text-ink-100">
            overplanned<span className="text-accent">.</span>
          </div>
        </div>
      }
    >
      <ErrorContent />
    </Suspense>
  );
}
