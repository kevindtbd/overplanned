// SlotSkeleton — Shimmer placeholder matching SlotCard dimensions.
//
// Usage:
//   <SlotSkeleton />
//   {/* or repeat for a list */}
//   {Array.from({ length: 3 }).map((_, i) => <SlotSkeleton key={i} />)}

export function SlotSkeleton() {
  return (
    <div
      className="rounded-2xl bg-surface shadow-card overflow-hidden"
      aria-busy="true"
      aria-label="Loading slot"
      role="status"
    >
      {/* Photo placeholder */}
      <div className="aspect-[16/9] w-full skel" />

      {/* Content area */}
      <div className="p-4 space-y-3">
        {/* Title line */}
        <div className="flex items-start justify-between gap-2">
          <div className="skel h-4 rounded-full w-3/5" />
          <div className="skel h-4 rounded w-12" />
        </div>

        {/* Time line */}
        <div className="flex items-center gap-2">
          <div className="skel h-3 rounded-full w-20" />
          <div className="skel h-3 rounded-full w-12" />
        </div>

        {/* Tag chips */}
        <div className="flex gap-2">
          <div className="skel h-5 rounded-full w-14" />
          <div className="skel h-5 rounded-full w-20" />
          <div className="skel h-5 rounded-full w-16" />
        </div>
      </div>

      <span className="sr-only">Loading activity slot...</span>
    </div>
  );
}
