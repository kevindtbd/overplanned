"use client";

import { useState, useEffect } from "react";
import { signOut } from "next-auth/react";

// ---------- Types ----------

type ConsentState = {
  modelTraining: boolean;
  anonymizedResearch: boolean;
};

type ConsentField = keyof ConsentState;

const DEFAULTS: ConsentState = {
  modelTraining: false,
  anonymizedResearch: false,
};

const CONSENT_ITEMS: { field: ConsentField; label: string; sub: string }[] = [
  {
    field: "modelTraining",
    label: "Improve your recommendations",
    sub: "Your trip patterns and preferences make your recommendations more accurate, and help us improve for similar travelers.",
  },
  {
    field: "anonymizedResearch",
    label: "Contribute to travel insights",
    sub: "Anonymized data helps us spot travel trends and improve recommendations across the board.",
  },
];

// ---------- Component ----------

export function PrivacySection({ email }: { email: string }) {
  const [consent, setConsent] = useState<ConsentState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [bannerVisible, setBannerVisible] = useState(false);

  // Export state
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  // Delete state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // SSR guard: check localStorage in useEffect only
  useEffect(() => {
    if (!localStorage.getItem("consent-banner-seen")) {
      setBannerVisible(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/privacy");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setConsent(data);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  function dismissBanner() {
    localStorage.setItem("consent-banner-seen", "1");
    setBannerVisible(false);
  }

  async function toggleConsent(field: ConsentField) {
    const prev = consent[field];
    const next = !prev;

    setConsent((s) => ({ ...s, [field]: next }));

    try {
      const res = await fetch("/api/settings/privacy", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: next }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setConsent((s) => ({ ...s, [field]: prev }));
    }
  }

  async function handleExport() {
    setExporting(true);
    setExportMsg(null);

    try {
      const res = await fetch("/api/settings/export");
      if (res.status === 429) {
        setExportMsg("Please wait before requesting another export.");
        setExporting(false);
        return;
      }
      if (!res.ok) {
        setExportMsg("Failed to download. Please try again.");
        setExporting(false);
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `overplanned-export-${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      setExportMsg("Failed to download. Please try again.");
    }

    setExporting(false);
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);

    try {
      const res = await fetch("/api/settings/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmEmail }),
      });

      if (res.ok) {
        signOut({ callbackUrl: "/" });
        return;
      }

      setDeleteError("Failed to delete account. Please try again.");
    } catch {
      setDeleteError("Failed to delete account. Please try again.");
    }

    setDeleting(false);
  }

  const emailMatch = confirmEmail.toLowerCase() === email.toLowerCase();

  return (
    <section aria-labelledby="privacy-heading">
      <h2 id="privacy-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Privacy & Data
      </h2>

      <div className="rounded-[20px] border border-ink-700 bg-surface p-5 space-y-8">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2].map((i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="h-4 w-64 bg-ink-700 rounded" />
                <div className="h-6 w-10 bg-ink-700 rounded-full" />
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load privacy settings.</p>
        ) : (
          <>
            {/* Consent Toggles */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-3">
                Consent
              </h3>

              {/* Education banner */}
              {bannerVisible && (
                <div className="rounded-xl border border-ink-700 bg-base p-4 mb-4" data-testid="consent-banner">
                  <p className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    How your data helps
                  </p>
                  <p className="font-sora text-sm text-ink-300 mb-3">
                    Your preferences and trip patterns help us learn what makes great
                    recommendations.
                  </p>
                  <p className="font-sora text-sm text-ink-300 mb-3">
                    You can enable or change these options anytime.
                  </p>
                  <button
                    onClick={dismissBanner}
                    className="rounded-full border border-accent text-accent px-4 py-1.5 font-sora text-sm hover:bg-accent/10 transition-colors"
                  >
                    Got it
                  </button>
                </div>
              )}

              <div className="space-y-3">
                {CONSENT_ITEMS.map(({ field, label, sub }) => (
                  <div key={field} className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <span className="font-sora text-sm text-ink-200">{label}</span>
                      <p className="font-sora text-xs text-ink-400 mt-0.5">{sub}</p>
                    </div>
                    <button
                      role="switch"
                      aria-checked={consent[field]}
                      onClick={() => toggleConsent(field)}
                      className={`
                        relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full
                        border-2 border-transparent transition-colors
                        ${consent[field] ? "bg-accent" : "bg-ink-500"}
                      `}
                    >
                      <span
                        aria-hidden="true"
                        className={`
                          pointer-events-none inline-block h-5 w-5 rounded-full bg-white
                          shadow-sm transition-transform
                          ${consent[field] ? "translate-x-4" : "translate-x-0"}
                        `}
                      />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Data Export */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-3">
                Your Data
              </h3>
              <p className="font-sora text-sm text-ink-300 mb-3">
                Download a copy of all your Overplanned data in JSON format.
              </p>
              <button
                onClick={handleExport}
                disabled={exporting}
                className="rounded-xl border border-ink-700 px-4 py-2 font-sora text-sm text-ink-200 hover:bg-ink-700/50 transition-colors disabled:opacity-50"
              >
                {exporting ? "Downloading..." : "Download my data"}
              </button>
              {exportMsg && (
                <p className="mt-2 font-sora text-sm text-red-400">{exportMsg}</p>
              )}
            </div>

            {/* Delete Account */}
            <div>
              <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-red-400 mb-3">
                Danger Zone
              </h3>
              <p className="font-sora text-sm text-ink-300 mb-3">
                Permanently delete your account and all personal data. Trip data is kept anonymously for service improvement.
              </p>

              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="font-sora text-sm text-red-400 hover:text-red-300 transition-colors"
                >
                  Delete my account
                </button>
              ) : (
                <div className="space-y-3">
                  <label className="block">
                    <span className="font-sora text-sm text-ink-300">Type your email to confirm:</span>
                    <input
                      type="email"
                      value={confirmEmail}
                      onChange={(e) => setConfirmEmail(e.target.value)}
                      placeholder="your@email.com"
                      className="mt-1 block w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-sora text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                  </label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setConfirmEmail("");
                        setDeleteError(null);
                      }}
                      className="rounded-lg px-4 py-2 font-sora text-sm text-ink-300 hover:text-ink-200 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleDelete}
                      disabled={!emailMatch || deleting}
                      className="rounded-lg bg-error/10 px-4 py-2 font-sora text-sm text-red-400 hover:bg-error/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Yes, delete my account
                    </button>
                  </div>
                  {deleteError && (
                    <p className="font-sora text-sm text-red-400">{deleteError}</p>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
