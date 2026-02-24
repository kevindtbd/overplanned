"use client";

import { Suspense, useState } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

/* ------------------------------------------------------------------ */
/*  SVG Icons — inline, no icon libraries                              */
/* ------------------------------------------------------------------ */

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
    </svg>
  );
}

function FacebookIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Sign-in form (inner component using useSearchParams)               */
/* ------------------------------------------------------------------ */

function EmailIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="3" />
      <path d="M22 7l-10 7L2 7" />
    </svg>
  );
}

const DEV_USERS = [
  { email: "test@overplanned.app", label: "Test User (beta)" },
  { email: "admin@overplanned.app", label: "Admin User (lifetime)" },
];

function SignInContent() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard";
  const [showEmail, setShowEmail] = useState(false);
  const [email, setEmail] = useState("");
  const [devLoading, setDevLoading] = useState(false);
  const isDev = process.env.NODE_ENV === "development";

  async function devLogin(devEmail: string) {
    setDevLoading(true);
    try {
      const res = await fetch("/api/auth/dev-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: devEmail }),
      });
      if (res.ok) {
        window.location.href = callbackUrl;
      } else {
        const data = await res.json();
        alert(data.error || "Dev login failed");
      }
    } finally {
      setDevLoading(false);
    }
  }

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
      <div className="relative z-10 w-full max-w-[400px] bg-surface border border-ink-700 rounded-[20px] shadow-xl p-10">
        {/* Logo */}
        <div className="font-sora text-[28px] font-bold tracking-[-0.04em] text-ink-100 mb-8">
          overplanned<span className="text-accent">.</span>
        </div>

        {/* Heading */}
        <h1 className="font-sora text-[28px] font-medium italic text-ink-100 leading-tight mb-2">
          Welcome back
        </h1>

        {/* Subtext */}
        <p className="text-ink-400 font-light text-[14px] mb-8">
          Pick up where you left off.
        </p>

        {/* Divider */}
        <div className="border-t border-ink-700 mb-8" />

        {/* Social sign-in — desktop: full buttons, mobile: circles */}
        <div className="hidden sm:flex flex-col gap-4">
          <button
            onClick={() => signIn("google", { callbackUrl })}
            className="w-full flex items-center justify-center gap-3 rounded-full py-3.5 px-4 text-[14px] font-medium bg-white text-[#1f1f1f] border border-ink-700 hover:border-ink-500 hover:shadow-sm transition-all cursor-pointer"
            aria-label="Continue with Google"
          >
            <GoogleIcon />
            Continue with Google
          </button>

          <button
            onClick={() => signIn("apple", { callbackUrl })}
            className="w-full flex items-center justify-center gap-3 rounded-full py-3.5 px-4 text-[14px] font-medium bg-[#1a1a1a] text-white hover:bg-black transition-colors cursor-pointer"
            aria-label="Continue with Apple"
          >
            <AppleIcon />
            Continue with Apple
          </button>

          <button
            onClick={() => signIn("facebook", { callbackUrl })}
            className="w-full flex items-center justify-center gap-3 rounded-full py-3.5 px-4 text-[14px] font-medium bg-[#1877F2] text-white hover:bg-[#166fe5] transition-colors cursor-pointer"
            aria-label="Continue with Facebook"
          >
            <FacebookIcon />
            Continue with Facebook
          </button>
        </div>

        {/* Mobile: icon circles */}
        <div className="flex sm:hidden items-center justify-center gap-5">
          <button
            onClick={() => signIn("google", { callbackUrl })}
            className="w-[52px] h-[52px] rounded-full bg-white border border-ink-700 flex items-center justify-center hover:border-ink-500 hover:shadow-sm transition-all cursor-pointer"
            aria-label="Continue with Google"
          >
            <GoogleIcon />
          </button>
          <button
            onClick={() => signIn("apple", { callbackUrl })}
            className="w-[52px] h-[52px] rounded-full bg-[#1a1a1a] flex items-center justify-center text-white hover:bg-black transition-colors cursor-pointer"
            aria-label="Continue with Apple"
          >
            <AppleIcon />
          </button>
          <button
            onClick={() => signIn("facebook", { callbackUrl })}
            className="w-[52px] h-[52px] rounded-full bg-[#1877F2] flex items-center justify-center text-white hover:bg-[#166fe5] transition-colors cursor-pointer"
            aria-label="Continue with Facebook"
          >
            <FacebookIcon />
          </button>
        </div>

        {/* Divider with "or" */}
        <div className="flex items-center gap-3 my-6">
          <div className="flex-1 border-t border-ink-700" />
          <span className="font-dm-mono text-[9px] tracking-[0.1em] uppercase text-ink-500">or</span>
          <div className="flex-1 border-t border-ink-700" />
        </div>

        {/* Email sign-in */}
        {!showEmail ? (
          <button
            onClick={() => setShowEmail(true)}
            className="w-full flex items-center justify-center gap-3 rounded-full py-3.5 px-4 text-[14px] font-medium text-ink-100 bg-raised border border-ink-700 hover:border-ink-500 transition-all cursor-pointer"
            aria-label="Continue with email"
          >
            <EmailIcon />
            Continue with email
          </button>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (email.includes("@")) {
                signIn("email", { email, callbackUrl });
              }
            }}
            className="flex flex-col gap-3"
          >
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoFocus
              className="w-full bg-input border border-ink-700 rounded-full px-5 py-3 text-[14px] text-ink-100 outline-none placeholder:text-ink-500 focus:border-accent transition-colors"
              aria-label="Email address"
            />
            <button
              type="submit"
              className="btn-primary w-full py-3.5 text-[14px]"
            >
              Send magic link
            </button>
          </form>
        )}

        {/* Dev-only quick login */}
        {isDev && (
          <div className="mt-6 border-t border-dashed border-ink-700 pt-5">
            <span className="font-dm-mono text-[9px] tracking-[0.1em] uppercase text-warning block mb-3">
              Dev Login
            </span>
            <div className="flex flex-col gap-2">
              {DEV_USERS.map((u) => (
                <button
                  key={u.email}
                  onClick={() => devLogin(u.email)}
                  disabled={devLoading}
                  className="w-full flex items-center justify-between rounded-lg py-2.5 px-4 text-[13px] text-ink-300 bg-raised border border-ink-700 hover:border-amber-500/40 transition-all cursor-pointer disabled:opacity-50"
                >
                  <span>{u.label}</span>
                  <span className="font-dm-mono text-[10px] text-ink-500">{u.email}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Disclaimer */}
        <p className="font-dm-mono text-[9px] tracking-[0.08em] uppercase text-ink-600 text-center mt-8 leading-[1.6]">
          By continuing, you agree to our{" "}
          <Link href="/terms" className="underline hover:text-ink-400 transition-colors">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="underline hover:text-ink-400 transition-colors">
            Privacy Policy
          </Link>
        </p>
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

export default function SignInPage() {
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
      <SignInContent />
    </Suspense>
  );
}
