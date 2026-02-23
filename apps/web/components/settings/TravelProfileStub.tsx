"use client";

export function TravelProfileStub() {
  return (
    <section aria-labelledby="travel-profile-heading">
      <h2 id="travel-profile-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        My Travel Profile
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5">
        <p className="font-sora text-sm text-ink-300">
          Your travel profile builds as you explore.
        </p>
        <p className="mt-1 font-dm-mono text-xs text-ink-400">
          Check back after your first trip to see what Overplanned has learned about your style.
        </p>
      </div>
    </section>
  );
}
