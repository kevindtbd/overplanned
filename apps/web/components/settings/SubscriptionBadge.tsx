"use client";

type SubscriptionBadgeProps = {
  tier: string;
};

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  beta: "Beta",
  pro: "Pro",
  lifetime: "Lifetime",
};

export function SubscriptionBadge({ tier }: SubscriptionBadgeProps) {
  return (
    <section aria-labelledby="subscription-heading">
      <h2 id="subscription-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Subscription
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 font-dm-mono text-xs text-accent uppercase tracking-wider">
            {TIER_LABELS[tier] || tier}
          </span>
        </div>
        <p className="mt-3 font-sora text-sm text-ink-400">
          Your plan details will appear here.
        </p>
      </div>
    </section>
  );
}
