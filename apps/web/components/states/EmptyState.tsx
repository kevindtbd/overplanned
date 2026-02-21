// EmptyState — Centered empty state with icon, title, description, and optional CTA.
//
// Usage:
//   <EmptyState
//     icon={<MapPinIcon />}
//     title="Nowhere planned yet."
//     description="Tell us where you're thinking. We'll handle the rest."
//     action={{ label: "Plan a trip", onClick: () => router.push("/trips/new") }}
//   />

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      {/* Icon container */}
      <div
        className="w-14 h-14 rounded-2xl bg-raised flex items-center justify-center mb-4 text-ink-500"
        aria-hidden="true"
      >
        {icon}
      </div>

      {/* Title */}
      <h3 className="font-lora italic text-xl text-ink-200 mb-2 leading-snug">
        {title}
      </h3>

      {/* Description */}
      <p className="text-ink-400 text-sm font-light leading-relaxed max-w-[240px] mb-5">
        {description}
      </p>

      {/* Action button */}
      {action && (
        <button
          type="button"
          className="btn-primary"
          onClick={action.onClick}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
