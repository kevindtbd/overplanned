"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------- Label Maps ----------

const DIETARY_LABELS: Record<string, string> = {
  vegan: "Vegan",
  vegetarian: "Vegetarian",
  halal: "Halal",
  kosher: "Kosher",
  "gluten-free": "Gluten-free",
  "nut-allergy": "Nut allergy",
  shellfish: "Shellfish allergy",
};

const MOBILITY_LABELS: Record<string, string> = {
  wheelchair: "Wheelchair accessible",
  "low-step": "Low-step preferred",
  "elevator-required": "Elevator required",
  "sensory-friendly": "Sensory-friendly",
};

const LANGUAGE_LABELS: Record<string, string> = {
  "non-english-menus": "Comfortable with non-English menus",
  "limited-english-staff": "OK with limited English staff",
};

const FREQUENCY_OPTIONS = [
  { value: "few-times-year", label: "A few times a year" },
  { value: "monthly", label: "Monthly" },
  { value: "constantly", label: "Constantly" },
] as const;

// ---------- Types ----------

type PrefsState = {
  dietary: string[];
  mobility: string[];
  languages: string[];
  travelFrequency: string | null;
};

const DEFAULTS: PrefsState = {
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
};

// ---------- Icons ----------

function CheckIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

// ---------- Component ----------

export function PreferencesSection() {
  const [prefs, setPrefs] = useState<PrefsState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef<PrefsState>(DEFAULTS);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/preferences");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setPrefs(data);
          lastSavedRef.current = data;
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

  const save = useCallback((next: PrefsState) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch("/api/settings/preferences", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
        if (!res.ok) throw new Error();
        const saved = await res.json();
        lastSavedRef.current = saved;
      } catch {
        // Revert all on failure
        setPrefs(lastSavedRef.current);
      }
    }, 500);
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function toggleArray(field: "dietary" | "mobility" | "languages", value: string) {
    setPrefs((prev) => {
      const arr = prev[field];
      const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
      const updated = { ...prev, [field]: next };
      save(updated);
      return updated;
    });
  }

  function setFrequency(value: string | null) {
    setPrefs((prev) => {
      const updated = { ...prev, travelFrequency: value };
      save(updated);
      return updated;
    });
  }

  return (
    <section aria-labelledby="preferences-heading">
      <h2 id="preferences-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        My Preferences
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-6">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            <div className="h-4 w-32 bg-warm-border rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-8 w-24 bg-warm-border rounded-lg" />
              ))}
            </div>
            <div className="h-4 w-28 bg-warm-border rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-8 w-28 bg-warm-border rounded-lg" />
              ))}
            </div>
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load preferences.</p>
        ) : (
          <>
            {/* Dietary */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Dietary needs
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(DIETARY_LABELS).map(([slug, label]) => {
                  const checked = prefs.dietary.includes(slug);
                  return (
                    <label
                      key={slug}
                      className={`
                        flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                        font-sora text-sm transition-colors
                        ${checked
                          ? "border-accent bg-accent/10 text-ink-100"
                          : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                        }
                      `}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleArray("dietary", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Mobility */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Accessibility
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(MOBILITY_LABELS).map(([slug, label]) => {
                  const checked = prefs.mobility.includes(slug);
                  return (
                    <label
                      key={slug}
                      className={`
                        flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                        font-sora text-sm transition-colors
                        ${checked
                          ? "border-accent bg-accent/10 text-ink-100"
                          : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                        }
                      `}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleArray("mobility", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Languages */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Language comfort
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(LANGUAGE_LABELS).map(([slug, label]) => {
                  const checked = prefs.languages.includes(slug);
                  return (
                    <label
                      key={slug}
                      className={`
                        flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                        font-sora text-sm transition-colors
                        ${checked
                          ? "border-accent bg-accent/10 text-ink-100"
                          : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                        }
                      `}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleArray("languages", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Travel frequency */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                How often do you travel?
              </legend>
              <div className="flex flex-wrap gap-2">
                {FREQUENCY_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className={`
                      flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                      font-sora text-sm transition-colors
                      ${prefs.travelFrequency === value
                        ? "border-accent bg-accent/10 text-ink-100"
                        : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                      }
                    `}
                  >
                    <input
                      type="radio"
                      name="travelFrequency"
                      checked={prefs.travelFrequency === value}
                      onChange={() => setFrequency(value)}
                      className="sr-only"
                    />
                    {label}
                  </label>
                ))}
                <label
                  className={`
                    flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                    font-sora text-sm transition-colors
                    ${prefs.travelFrequency === null
                      ? "border-accent bg-accent/10 text-ink-100"
                      : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                    }
                  `}
                >
                  <input
                    type="radio"
                    name="travelFrequency"
                    checked={prefs.travelFrequency === null}
                    onChange={() => setFrequency(null)}
                    className="sr-only"
                  />
                  No preference
                </label>
              </div>
            </fieldset>
          </>
        )}
      </div>
    </section>
  );
}
