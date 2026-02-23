"use client";

// WelcomeCard — Post-creation inline welcome for the trip detail page.
// Shows after trip creation, dismisses on first slot action or "Got it" tap.

interface WelcomeCardProps {
  city: string;
  totalSlots: number;
  totalDays: number;
  onDismiss: () => void;
  /** Multi-leg route string, e.g. "Tokyo → Kyoto → Osaka" */
  routeString?: string;
}

export function WelcomeCard({ city, totalSlots, totalDays, onDismiss, routeString }: WelcomeCardProps) {
  const title = routeString
    ? `Your ${routeString} trip is ready`
    : `Your ${city} itinerary is ready`;

  return (
    <div className="rounded-xl border border-accent/20 bg-accent/5 p-4 space-y-2">
      <h3 className="font-sora text-base font-medium text-ink-100">
        {title}
      </h3>
      <p className="font-dm-mono text-xs text-ink-400 leading-relaxed">
        {totalSlots > 0
          ? `${totalSlots} activities across ${totalDays} days, built from your vibes. Tap confirm on the ones you love, skip the rest.`
          : `${totalDays} days planned. Browse activities to start filling your itinerary.`}
      </p>
      <button
        onClick={onDismiss}
        className="font-dm-mono text-xs text-accent hover:text-accent/80 transition-colors"
      >
        Got it
      </button>
    </div>
  );
}
