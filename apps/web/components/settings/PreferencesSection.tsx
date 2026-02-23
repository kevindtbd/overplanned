"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  DIETARY_OPTIONS,
  MOBILITY_OPTIONS,
  BUDGET_OPTIONS,
  SPENDING_PRIORITY_OPTIONS,
  ACCOMMODATION_OPTIONS,
  TRANSIT_OPTIONS,
} from "@/lib/validations/settings";

// ---------- Label Maps ----------

const DIETARY_LABELS: Record<(typeof DIETARY_OPTIONS)[number], string> = {
  vegan: "Vegan",
  vegetarian: "Vegetarian",
  halal: "Halal",
  kosher: "Kosher",
  "gluten-free": "Gluten-free",
  "nut-allergy": "Nut allergy",
  shellfish: "Shellfish allergy",
  "dairy-free": "Dairy-free",
  pescatarian: "Pescatarian",
  "no-pork": "No pork",
};

const MOBILITY_LABELS: Record<(typeof MOBILITY_OPTIONS)[number], string> = {
  wheelchair: "Wheelchair accessible",
  "low-step": "Low-step preferred",
  "elevator-required": "Elevator required",
  "sensory-friendly": "Sensory-friendly",
  "service-animal": "Service animal",
  "limited-stamina": "Limited stamina",
};

const LANGUAGE_LABELS: Record<string, string> = {
  "non-english-menus": "Comfortable with non-English menus",
  "limited-english-staff": "OK with limited English staff",
};

const BUDGET_LABELS: Record<(typeof BUDGET_OPTIONS)[number], string> = {
  budget: "Budget-friendly",
  "mid-range": "Mid-range",
  splurge: "Splurge-worthy",
  mix: "Mix of everything",
};

const SPENDING_LABELS: Record<(typeof SPENDING_PRIORITY_OPTIONS)[number], string> = {
  "food-drink": "Food & drink",
  experiences: "Experiences",
  accommodation: "Accommodation",
  shopping: "Shopping",
};

const ACCOMMODATION_LABELS: Record<(typeof ACCOMMODATION_OPTIONS)[number], string> = {
  hostel: "Hostel",
  "boutique-hotel": "Boutique hotel",
  "chain-hotel": "Chain hotel",
  airbnb: "Airbnb / rental",
  camping: "Camping",
};

const TRANSIT_LABELS: Record<(typeof TRANSIT_OPTIONS)[number], string> = {
  walking: "Walking",
  "public-transit": "Public transit",
  rideshare: "Rideshare",
  "rental-car": "Rental car",
  biking: "Biking",
  scooter: "Scooter",
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
  vibePreferences: string[];
  travelStyleNote: string | null;
  budgetComfort: string | null;
  spendingPriorities: string[];
  accommodationTypes: string[];
  transitModes: string[];
  preferencesNote: string | null;
};

const DEFAULTS: PrefsState = {
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
  vibePreferences: [],
  travelStyleNote: null,
  budgetComfort: null,
  spendingPriorities: [],
  accommodationTypes: [],
  transitModes: [],
  preferencesNote: null,
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

type ArrayField = "dietary" | "mobility" | "languages" | "spendingPriorities" | "accommodationTypes" | "transitModes";
type ScalarField = "travelFrequency" | "budgetComfort";

export function PreferencesSection() {
  const [prefs, setPrefs] = useState<PrefsState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [noteText, setNoteText] = useState("");
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
          setNoteText(data.preferencesNote ?? "");
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

  const patchField = useCallback(async (field: string, value: unknown) => {
    try {
      const res = await fetch("/api/settings/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      if (!res.ok) throw new Error();
      const saved = await res.json();
      lastSavedRef.current = saved;
    } catch {
      // Revert on failure
      setPrefs(lastSavedRef.current);
      setNoteText(lastSavedRef.current.preferencesNote ?? "");
    }
  }, []);

  function toggleArray(field: ArrayField, value: string) {
    setPrefs((prev) => {
      const arr = prev[field];
      const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
      const updated = { ...prev, [field]: next };
      patchField(field, next);
      return updated;
    });
  }

  function setScalar(field: ScalarField, value: string | null) {
    setPrefs((prev) => {
      const updated = { ...prev, [field]: value };
      patchField(field, value);
      return updated;
    });
  }

  function handleNoteBlur() {
    const trimmed = noteText.trim();
    const normalized = trimmed === "" ? null : trimmed;
    if (normalized === lastSavedRef.current.preferencesNote) return;
    setPrefs((prev) => ({ ...prev, preferencesNote: normalized }));
    patchField("preferencesNote", normalized);
  }

  const remaining = 500 - noteText.length;

  return (
    <section aria-labelledby="preferences-heading">
      <h2 id="preferences-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        My Preferences
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5">
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
            {/* Dietary needs */}
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

            {/* Accessibility */}
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

            {/* Budget comfort */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Budget comfort
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(BUDGET_LABELS).map(([value, label]) => (
                  <label
                    key={value}
                    className={`
                      flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                      font-sora text-sm transition-colors
                      ${prefs.budgetComfort === value
                        ? "border-accent bg-accent/10 text-ink-100"
                        : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                      }
                    `}
                  >
                    <input
                      type="radio"
                      name="budgetComfort"
                      checked={prefs.budgetComfort === value}
                      onChange={() => setScalar("budgetComfort", value)}
                      className="sr-only"
                    />
                    {label}
                  </label>
                ))}
                <label
                  className={`
                    flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                    font-sora text-sm transition-colors
                    ${prefs.budgetComfort === null
                      ? "border-accent bg-accent/10 text-ink-100"
                      : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                    }
                  `}
                >
                  <input
                    type="radio"
                    name="budgetComfort"
                    checked={prefs.budgetComfort === null}
                    onChange={() => setScalar("budgetComfort", null)}
                    className="sr-only"
                  />
                  No preference
                </label>
              </div>
            </fieldset>

            {/* Spending priorities */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Spending priorities
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(SPENDING_LABELS).map(([slug, label]) => {
                  const checked = prefs.spendingPriorities.includes(slug);
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
                        onChange={() => toggleArray("spendingPriorities", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Accommodation */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Accommodation
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(ACCOMMODATION_LABELS).map(([slug, label]) => {
                  const checked = prefs.accommodationTypes.includes(slug);
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
                        onChange={() => toggleArray("accommodationTypes", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Getting around */}
            <fieldset>
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Getting around
              </legend>
              <div className="flex flex-wrap gap-2">
                {Object.entries(TRANSIT_LABELS).map(([slug, label]) => {
                  const checked = prefs.transitModes.includes(slug);
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
                        onChange={() => toggleArray("transitModes", slug)}
                        className="sr-only"
                      />
                      {checked && <CheckIcon />}
                      {label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            {/* Language comfort */}
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
                      onChange={() => setScalar("travelFrequency", value)}
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
                    onChange={() => setScalar("travelFrequency", null)}
                    className="sr-only"
                  />
                  No preference
                </label>
              </div>
            </fieldset>

            {/* Free-form textarea (full width) */}
            <fieldset className="sm:col-span-2">
              <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                Anything else about how you prefer to travel?
              </legend>
              <textarea
                value={noteText}
                onChange={(e) => {
                  if (e.target.value.length <= 500) setNoteText(e.target.value);
                }}
                onBlur={handleNoteBlur}
                placeholder="I always need a gym nearby, never book hostels..."
                maxLength={500}
                rows={3}
                className="w-full rounded-lg border border-warm-border bg-warm-background px-3 py-2 font-sora text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
              />
              {remaining <= 100 && (
                <p className="mt-1 font-dm-mono text-[10px] text-ink-400 text-right">
                  {remaining} characters remaining
                </p>
              )}
            </fieldset>
          </div>
        )}
      </div>
    </section>
  );
}
