"use client";

export function PreferencesStub() {
  return (
    <section aria-labelledby="preferences-heading">
      <h2 id="preferences-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        My Preferences
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5">
        <p className="font-sora text-sm text-ink-300">
          Set dietary needs, accessibility requirements, and travel pace.
        </p>
        <p className="mt-1 font-dm-mono text-xs text-ink-400">
          Available soon.
        </p>
      </div>
    </section>
  );
}
