"use client";

import { useState, useRef } from "react";
import { signOut } from "next-auth/react";
import { useRouter } from "next/navigation";

// ---------- Types ----------

type AccountSectionProps = {
  name: string | null;
  email: string;
  provider: string;
};

// ---------- Icons ----------

function CheckIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
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

// ---------- Component ----------

export function AccountSection({ name, email, provider }: AccountSectionProps) {
  const router = useRouter();
  const [displayName, setDisplayName] = useState(name || "");
  const [savedName, setSavedName] = useState(name || "");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function handleSave() {
    const trimmed = displayName.trim();
    if (!trimmed || trimmed === savedName) return;

    setSaving(true);
    setSaveStatus("idle");

    try {
      const res = await fetch("/api/settings/account", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });

      if (!res.ok) {
        throw new Error("Failed to save");
      }

      setSavedName(trimmed);
      setDisplayName(trimmed);
      setSaveStatus("saved");
      router.refresh();

      // Clear "saved" indicator after 2s
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      // Revert on failure
      setDisplayName(savedName);
      setSaveStatus("error");
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => setSaveStatus("idle"), 3000);
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.currentTarget.blur();
    }
    if (e.key === "Escape") {
      setDisplayName(savedName);
      e.currentTarget.blur();
    }
  }

  return (
    <section aria-labelledby="account-heading">
      <h2 id="account-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Account
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-5">
        {/* Display name */}
        <div>
          <label
            htmlFor="display-name"
            className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-1.5"
          >
            Display name
          </label>
          <div className="flex items-center gap-2">
            <input
              id="display-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyDown}
              maxLength={100}
              disabled={saving}
              className="
                flex-1 bg-transparent border border-warm-border rounded-lg
                px-3 py-2 font-sora text-sm text-ink-100
                focus:outline-none focus:border-accent
                disabled:opacity-50
                transition-colors
              "
              placeholder="Your name"
            />
            {saveStatus === "saved" && (
              <span className="text-green-500 flex items-center gap-1">
                <CheckIcon />
              </span>
            )}
            {saveStatus === "error" && (
              <span className="font-dm-mono text-[10px] text-red-400">
                Failed to save
              </span>
            )}
          </div>
        </div>

        {/* Email */}
        <div>
          <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-1.5">
            Email
          </span>
          <p className="font-sora text-sm text-ink-300">{email}</p>
        </div>

        {/* Connected accounts */}
        <div>
          <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-1.5">
            Connected accounts
          </span>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-lg border border-warm-border px-3 py-1.5">
              <GoogleIcon />
              <span className="font-sora text-sm text-ink-300 capitalize">{provider}</span>
            </div>
          </div>
        </div>

        {/* Sign out */}
        <div className="pt-2 border-t border-warm-border">
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="font-sora text-sm text-ink-400 hover:text-ink-100 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>
    </section>
  );
}
