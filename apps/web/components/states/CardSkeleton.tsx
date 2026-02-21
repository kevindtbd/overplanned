// CardSkeleton — Generic card skeleton for dashboard trip cards, etc.
//
// Usage:
//   <CardSkeleton />
//   <CardSkeleton className="h-48" />

interface CardSkeletonProps {
  className?: string;
}

export function CardSkeleton({ className }: CardSkeletonProps) {
  return (
    <div
      className={`rounded-2xl bg-surface shadow-card overflow-hidden p-4 space-y-3 ${className ?? ""}`}
      aria-busy="true"
      aria-label="Loading card"
      role="status"
    >
      {/* Photo / hero area */}
      <div className="skel h-32 rounded-xl w-full" />

      {/* Title */}
      <div className="skel h-4 rounded-full w-3/4" />

      {/* Subtitle */}
      <div className="skel h-3 rounded-full w-1/2" />

      {/* Metadata row */}
      <div className="flex gap-3">
        <div className="skel h-3 rounded-full w-16" />
        <div className="skel h-3 rounded-full w-20" />
      </div>

      <span className="sr-only">Loading content...</span>
    </div>
  );
}
