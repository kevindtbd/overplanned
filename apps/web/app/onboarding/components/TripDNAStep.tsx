"use client";

const PACE_OPTIONS = [
  {
    id: "packed" as const,
    label: "Packed",
    description: "Max activities, minimal downtime",
  },
  {
    id: "moderate" as const,
    label: "Moderate",
    description: "Good balance of plans and free time",
  },
  {
    id: "relaxed" as const,
    label: "Relaxed",
    description: "Slow and intentional, no rushing",
  },
];

const MORNING_OPTIONS = [
  { id: "early" as const, label: "Early bird", time: "Before 8am" },
  { id: "mid" as const, label: "Mid morning", time: "8am - 10am" },
  { id: "late" as const, label: "Late riser", time: "After 10am" },
];

export const FOOD_CHIPS = [
  "street food",
  "fine dining",
  "local staples",
  "seafood",
  "ramen",
  "coffee culture",
  "bakeries",
  "night markets",
  "vegetarian",
  "izakaya",
  "wine bars",
  "brunch spots",
];

export type Pace = "packed" | "moderate" | "relaxed";
export type MorningPreference = "early" | "mid" | "late";

interface TripDNAStepProps {
  pace: Pace | null;
  morningPreference: MorningPreference | null;
  foodPreferences: string[];
  freeformVibes: string;
  onPaceChange: (pace: Pace) => void;
  onMorningChange: (pref: MorningPreference) => void;
  onFoodToggle: (chip: string) => void;
  onFreeformChange: (value: string) => void;
}

export function TripDNAStep({
  pace,
  morningPreference,
  foodPreferences,
  freeformVibes,
  onPaceChange,
  onMorningChange,
  onFoodToggle,
  onFreeformChange,
}: TripDNAStepProps) {
  return (
    <div className="mx-auto w-full max-w-lg">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        Your Trip DNA
      </h2>
      <p className="label-mono mt-2">
        helps us shape your itinerary
      </p>

      {/* Pace */}
      <div className="mt-8">
        <h3 className="font-sora text-base font-medium text-primary">
          Travel pace
        </h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {PACE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              onClick={() => onPaceChange(opt.id)}
              className={`rounded-lg border px-4 py-3 text-left transition-all duration-150 ${
                pace === opt.id
                  ? "border-accent bg-accent-light text-accent-fg"
                  : "border-ink-700 bg-raised text-ink-300 hover:border-accent/50"
              }`}
            >
              <span className="block font-sora text-sm font-medium text-primary">
                {opt.label}
              </span>
              <span className="mt-0.5 block font-dm-mono text-xs text-secondary">
                {opt.description}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Morning preference */}
      <div className="mt-8">
        <h3 className="font-sora text-base font-medium text-primary">
          Morning preference
        </h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {MORNING_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              onClick={() => onMorningChange(opt.id)}
              className={`rounded-lg border px-4 py-3 text-left transition-all duration-150 ${
                morningPreference === opt.id
                  ? "border-accent bg-accent-light text-accent-fg"
                  : "border-ink-700 bg-raised text-ink-300 hover:border-accent/50"
              }`}
            >
              <span className="block font-sora text-sm font-medium text-primary">
                {opt.label}
              </span>
              <span className="mt-0.5 block font-dm-mono text-xs text-secondary">
                {opt.time}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Food preferences */}
      <div className="mt-8">
        <h3 className="font-sora text-base font-medium text-primary">
          Food interests
        </h3>
        <p className="mt-1 font-dm-mono text-xs text-secondary">
          Select as many as you like
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {FOOD_CHIPS.map((chip) => {
            const selected = foodPreferences.includes(chip);
            return (
              <button
                key={chip}
                onClick={() => onFoodToggle(chip)}
                className={`rounded-full border px-3.5 py-1.5 font-dm-mono text-xs transition-all duration-150 ${
                  selected
                    ? "border-accent bg-accent-light text-accent-fg"
                    : "border-ink-700 bg-raised text-ink-300 hover:border-accent/50"
                }`}
              >
                {chip}
              </button>
            );
          })}
        </div>
      </div>

      {/* Free-form vibes */}
      <div className="mt-8">
        <h3 className="font-sora text-base font-medium text-primary">
          Anything else?
        </h3>
        <p className="mt-1 font-dm-mono text-xs text-secondary">
          Hidden gems, local markets, avoiding crowds, whatever
        </p>
        <textarea
          value={freeformVibes}
          onChange={(e) => onFreeformChange(e.target.value)}
          placeholder="I love hole-in-the-wall spots and hate tourist traps..."
          maxLength={300}
          rows={3}
          className="mt-3 w-full rounded-xl border-[1.5px] border-ink-700 bg-input py-3 px-4 font-dm-mono text-sm text-primary placeholder:text-secondary resize-none focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <p className="mt-1 text-right font-dm-mono text-xs text-secondary">
          {freeformVibes.length}/300
        </p>
      </div>
    </div>
  );
}
