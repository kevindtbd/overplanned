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

const VIBE_GROUPS = [
  {
    heading: "Pace & Energy",
    tags: [
      { slug: "high-energy", label: "High energy" },
      { slug: "slow-burn", label: "Slow burn" },
      { slug: "immersive", label: "Immersive" },
    ],
  },
  {
    heading: "Discovery Style",
    tags: [
      { slug: "hidden-gem", label: "Hidden gems" },
      { slug: "iconic-worth-it", label: "Iconic & worth it" },
      { slug: "locals-only", label: "Locals only" },
      { slug: "offbeat", label: "Offbeat & unexpected" },
    ],
  },
  {
    heading: "Food & Drink",
    tags: [
      { slug: "destination-meal", label: "Destination meals" },
      { slug: "street-food", label: "Street food" },
      { slug: "local-institution", label: "Local institutions" },
      { slug: "drinks-forward", label: "Drinks-forward spots" },
    ],
  },
  {
    heading: "Activity Type",
    tags: [
      { slug: "nature-immersive", label: "Nature immersive" },
      { slug: "urban-exploration", label: "Urban exploration" },
      { slug: "deep-history", label: "Deep history" },
      { slug: "contemporary-culture", label: "Contemporary culture" },
      { slug: "hands-on", label: "Hands-on experiences" },
      { slug: "scenic", label: "Scenic views" },
    ],
  },
  {
    heading: "Social & Time",
    tags: [
      { slug: "late-night", label: "Late night" },
      { slug: "early-morning", label: "Early morning" },
      { slug: "solo-friendly", label: "Solo-friendly" },
      { slug: "group-friendly", label: "Group-friendly" },
      { slug: "social-scene", label: "Social scene" },
      { slug: "low-interaction", label: "Low interaction" },
    ],
  },
] as const;

// ---------- Types ----------

type TravelStyleState = {
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

const DEFAULTS: TravelStyleState = {
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

type Tab = "practical" | "vibes";

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

// ---------- Sub-components ----------

type ArrayField = "dietary" | "mobility" | "languages" | "spendingPriorities" | "accommodationTypes" | "transitModes" | "vibePreferences";
type ScalarField = "travelFrequency" | "budgetComfort";

function ChipGroup({
  labels,
  selected,
  onToggle,
}: {
  labels: Record<string, string>;
  selected: string[];
  onToggle: (slug: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(labels).map(([slug, label]) => {
        const checked = selected.includes(slug);
        return (
          <label
            key={slug}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
              font-sora text-sm transition-colors
              ${checked
                ? "border-accent bg-accent/10 text-ink-100"
                : "border-ink-700 bg-transparent text-ink-300 hover:border-ink-400"
              }
            `}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={() => onToggle(slug)}
              className="sr-only"
            />
            {checked && <CheckIcon />}
            {label}
          </label>
        );
      })}
    </div>
  );
}

function RadioGroup({
  name,
  options,
  selected,
  onSelect,
  nullLabel,
}: {
  name: string;
  options: readonly { value: string; label: string }[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  nullLabel: string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(({ value, label }) => (
        <label
          key={value}
          className={`
            flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
            font-sora text-sm transition-colors
            ${selected === value
              ? "border-accent bg-accent/10 text-ink-100"
              : "border-ink-700 bg-transparent text-ink-300 hover:border-ink-400"
            }
          `}
        >
          <input
            type="radio"
            name={name}
            checked={selected === value}
            onChange={() => onSelect(value)}
            className="sr-only"
          />
          {label}
        </label>
      ))}
      <label
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
          font-sora text-sm transition-colors
          ${selected === null
            ? "border-accent bg-accent/10 text-ink-100"
            : "border-ink-700 bg-transparent text-ink-300 hover:border-ink-400"
          }
        `}
      >
        <input
          type="radio"
          name={name}
          checked={selected === null}
          onChange={() => onSelect(null)}
          className="sr-only"
        />
        {nullLabel}
      </label>
    </div>
  );
}

function NoteTextarea({
  value,
  onChange,
  onBlur,
  placeholder,
  maxLength = 500,
}: {
  value: string;
  onChange: (v: string) => void;
  onBlur: () => void;
  placeholder: string;
  maxLength?: number;
}) {
  const remaining = maxLength - value.length;
  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => {
          if (e.target.value.length <= maxLength) onChange(e.target.value);
        }}
        onBlur={onBlur}
        placeholder={placeholder}
        maxLength={maxLength}
        rows={3}
        className="w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-sora text-sm text-ink-100 placeholder:text-ink-500 focus:outline-none focus:ring-1 focus:ring-accent resize-none"
      />
      {remaining <= 100 && (
        <p className="mt-1 font-dm-mono text-[10px] text-ink-400 text-right">
          {remaining} characters remaining
        </p>
      )}
    </div>
  );
}

// ---------- Main Component ----------

export function TravelStyleSection() {
  const [state, setState] = useState<TravelStyleState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("practical");
  const [prefsNoteText, setPrefsNoteText] = useState("");
  const [styleNoteText, setStyleNoteText] = useState("");
  const lastSavedRef = useRef<TravelStyleState>(DEFAULTS);
  const vibeDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/preferences");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          setState(data);
          lastSavedRef.current = data;
          setPrefsNoteText(data.preferencesNote ?? "");
          setStyleNoteText(data.travelStyleNote ?? "");
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

  // Cleanup vibe debounce on unmount
  useEffect(() => {
    return () => {
      if (vibeDebounceRef.current) clearTimeout(vibeDebounceRef.current);
    };
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
      setState(lastSavedRef.current);
      setPrefsNoteText(lastSavedRef.current.preferencesNote ?? "");
      setStyleNoteText(lastSavedRef.current.travelStyleNote ?? "");
    }
  }, []);

  function toggleArray(field: ArrayField, value: string) {
    if (field === "vibePreferences") {
      // Vibes use debounced save
      setState((prev) => {
        const arr = prev.vibePreferences;
        const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
        if (vibeDebounceRef.current) clearTimeout(vibeDebounceRef.current);
        vibeDebounceRef.current = setTimeout(() => {
          patchField("vibePreferences", next);
        }, 500);
        return { ...prev, vibePreferences: next };
      });
    } else {
      // Other arrays use immediate save
      setState((prev) => {
        const arr = prev[field];
        const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
        patchField(field, next);
        return { ...prev, [field]: next };
      });
    }
  }

  function setScalar(field: ScalarField, value: string | null) {
    setState((prev) => {
      patchField(field, value);
      return { ...prev, [field]: value };
    });
  }

  function handlePrefsNoteBlur() {
    const trimmed = prefsNoteText.trim();
    const normalized = trimmed === "" ? null : trimmed;
    if (normalized === lastSavedRef.current.preferencesNote) return;
    setState((prev) => ({ ...prev, preferencesNote: normalized }));
    patchField("preferencesNote", normalized);
  }

  function handleStyleNoteBlur() {
    const trimmed = styleNoteText.trim();
    const normalized = trimmed === "" ? null : trimmed;
    if (normalized === lastSavedRef.current.travelStyleNote) return;
    setState((prev) => ({ ...prev, travelStyleNote: normalized }));
    patchField("travelStyleNote", normalized);
  }

  const TABS: { key: Tab; label: string }[] = [
    { key: "practical", label: "Practical" },
    { key: "vibes", label: "Vibes" },
  ];

  return (
    <section id="travel-style" aria-labelledby="travel-style-heading">
      <h2 id="travel-style-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Travel Style
      </h2>

      <div className="rounded-[20px] border border-ink-700 bg-surface p-5">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            <div className="h-4 w-32 bg-ink-700 rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-8 w-24 bg-ink-700 rounded-lg" />
              ))}
            </div>
            <div className="h-4 w-28 bg-ink-700 rounded" />
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-8 w-28 bg-ink-700 rounded-lg" />
              ))}
            </div>
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load travel style.</p>
        ) : (
          <>
            {/* Tab bar */}
            <div className="flex gap-4 border-b border-ink-700 pb-3 mb-4" role="tablist">
              {TABS.map(({ key, label }) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={activeTab === key}
                  onClick={() => setActiveTab(key)}
                  className={`
                    font-dm-mono text-xs uppercase tracking-wider pb-1 transition-colors
                    ${activeTab === key
                      ? "text-accent border-b-2 border-accent"
                      : "text-ink-400 hover:text-ink-300"
                    }
                  `}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Practical tab */}
            {activeTab === "practical" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4" role="tabpanel">
                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Dietary needs
                  </legend>
                  <ChipGroup labels={DIETARY_LABELS} selected={state.dietary} onToggle={(s) => toggleArray("dietary", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Accessibility
                  </legend>
                  <ChipGroup labels={MOBILITY_LABELS} selected={state.mobility} onToggle={(s) => toggleArray("mobility", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Budget comfort
                  </legend>
                  <RadioGroup
                    name="budgetComfort"
                    options={Object.entries(BUDGET_LABELS).map(([v, l]) => ({ value: v, label: l }))}
                    selected={state.budgetComfort}
                    onSelect={(v) => setScalar("budgetComfort", v)}
                    nullLabel="No preference"
                  />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Spending priorities
                  </legend>
                  <ChipGroup labels={SPENDING_LABELS} selected={state.spendingPriorities} onToggle={(s) => toggleArray("spendingPriorities", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Accommodation
                  </legend>
                  <ChipGroup labels={ACCOMMODATION_LABELS} selected={state.accommodationTypes} onToggle={(s) => toggleArray("accommodationTypes", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Getting around
                  </legend>
                  <ChipGroup labels={TRANSIT_LABELS} selected={state.transitModes} onToggle={(s) => toggleArray("transitModes", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Language comfort
                  </legend>
                  <ChipGroup labels={LANGUAGE_LABELS} selected={state.languages} onToggle={(s) => toggleArray("languages", s)} />
                </fieldset>

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    How often do you travel?
                  </legend>
                  <RadioGroup
                    name="travelFrequency"
                    options={FREQUENCY_OPTIONS as unknown as { value: string; label: string }[]}
                    selected={state.travelFrequency}
                    onSelect={(v) => setScalar("travelFrequency", v)}
                    nullLabel="No preference"
                  />
                </fieldset>

                <fieldset className="sm:col-span-2">
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Anything else about how you prefer to travel?
                  </legend>
                  <NoteTextarea
                    value={prefsNoteText}
                    onChange={setPrefsNoteText}
                    onBlur={handlePrefsNoteBlur}
                    placeholder="I always need a gym nearby, never book hostels..."
                  />
                </fieldset>
              </div>
            )}

            {/* Vibes tab */}
            {activeTab === "vibes" && (
              <div className="space-y-4" role="tabpanel">
                {VIBE_GROUPS.map((group, groupIdx) => (
                  <div key={group.heading}>
                    {groupIdx > 0 && (
                      <div className="border-t border-ink-700 mb-4" />
                    )}
                    <h3 className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                      {group.heading}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {group.tags.map((tag) => {
                        const checked = state.vibePreferences.includes(tag.slug);
                        return (
                          <label
                            key={tag.slug}
                            className={`
                              flex items-center gap-1.5 px-3 py-1.5 rounded-lg border cursor-pointer
                              font-sora text-sm transition-colors
                              ${checked
                                ? "border-accent bg-accent/10 text-ink-100"
                                : "border-ink-700 bg-transparent text-ink-300 hover:border-ink-400"
                              }
                            `}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleArray("vibePreferences", tag.slug)}
                              className="sr-only"
                            />
                            {checked && <CheckIcon />}
                            {tag.label}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}

                <div className="border-t border-ink-700" />

                <fieldset>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    Anything else about how you travel?
                  </legend>
                  <NoteTextarea
                    value={styleNoteText}
                    onChange={setStyleNoteText}
                    onBlur={handleStyleNoteBlur}
                    placeholder="I always hunt for the best coffee spot in every city..."
                  />
                </fieldset>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
