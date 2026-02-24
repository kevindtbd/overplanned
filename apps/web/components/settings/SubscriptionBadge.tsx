"use client";

import { useState } from "react";

type SubscriptionBadgeProps = {
  tier: string;
};

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  beta: "Beta",
  pro: "Pro",
  lifetime: "Lifetime",
};

function SpinnerIcon() {
  return (
    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function SubscriptionBadge({ tier }: SubscriptionBadgeProps) {
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);
  const showBillingLink = ["pro", "lifetime"].includes(tier);

  async function handleManageBilling() {
    setBillingLoading(true);
    setBillingError(null);
    try {
      const res = await fetch("/api/settings/billing-portal", { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: "Something went wrong" }));
        setBillingError(data.error || "Something went wrong");
        return;
      }
      const data = await res.json();
      window.location.href = data.url;
    } catch {
      setBillingError("Could not reach billing service");
    } finally {
      setBillingLoading(false);
    }
  }

  return (
    <section id="subscription" aria-labelledby="subscription-heading">
      <h2 id="subscription-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Subscription
      </h2>

      <div className="rounded-[20px] border border-ink-700 bg-surface p-5">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 font-dm-mono text-xs text-accent uppercase tracking-wider">
            {TIER_LABELS[tier] || tier}
          </span>
          {showBillingLink && (
            <button
              onClick={handleManageBilling}
              disabled={billingLoading}
              className="font-dm-mono text-xs text-ink-400 hover:text-accent transition-colors disabled:opacity-50"
            >
              {billingLoading ? (
                <span className="flex items-center gap-1.5"><SpinnerIcon />Opening...</span>
              ) : "Manage billing"}
            </button>
          )}
        </div>
        {billingError && (
          <p className="mt-2 font-sora text-xs text-[var(--error)]">{billingError}</p>
        )}
        {!showBillingLink && (
          <p className="mt-3 font-sora text-sm text-ink-400">
            Your plan details will appear here.
          </p>
        )}
      </div>
    </section>
  );
}
