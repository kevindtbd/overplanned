export type Pace = "packed" | "moderate" | "relaxed";
export type MorningPreference = "early" | "mid" | "late";

export interface PersonaSeed {
  pace: Pace;
  morningPreference: MorningPreference;
  foodPreferences: string[];
  freeformVibes?: string;
  template?: string;
}

export interface TemplateConfig {
  weights: Record<string, number>;  // category -> weight (0-1, should sum to ~1)
  paceModifier: number;  // -1, 0, or +1 adjusts slots per day
}

export interface ScoredNode {
  nodeId: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
  neighborhood: string | null;
  descriptionShort: string | null;
  priceLevel: number | null;
  authorityScore: number | null;
  vibeTagSlugs: string[];
  score: number;
}

export interface PlacedSlot {
  nodeId: string;
  name: string;
  category: string;
  dayNumber: number;  // 1-indexed
  sortOrder: number;  // 1-indexed within day
  slotType: "anchor" | "flex" | "meal" | "rest" | "transit";
  startTime: Date | null;
  endTime: Date | null;
  durationMinutes: number;
}

export const TEMPLATE_WEIGHTS: Record<string, TemplateConfig> = {
  "foodie-weekend":    { weights: { dining: 0.35, drinks: 0.20, culture: 0.10, outdoors: 0.10, experience: 0.15, nightlife: 0.10 }, paceModifier: 0 },
  "culture-deep-dive": { weights: { dining: 0.15, drinks: 0.05, culture: 0.40, outdoors: 0.15, experience: 0.15, nightlife: 0.05, shopping: 0.05 }, paceModifier: 0 },
  "adventure":         { weights: { dining: 0.10, drinks: 0.05, culture: 0.05, outdoors: 0.35, active: 0.30, experience: 0.10, wellness: 0.05 }, paceModifier: 1 },
  "chill":             { weights: { dining: 0.20, drinks: 0.15, culture: 0.10, outdoors: 0.15, wellness: 0.20, experience: 0.10, shopping: 0.10 }, paceModifier: -1 },
  "night-owl":         { weights: { dining: 0.20, drinks: 0.25, nightlife: 0.30, culture: 0.05, experience: 0.10, entertainment: 0.10 }, paceModifier: 0 },
  "local-immersion":   { weights: { dining: 0.25, drinks: 0.10, culture: 0.15, outdoors: 0.10, experience: 0.25, shopping: 0.10, wellness: 0.05 }, paceModifier: 0 },
  "first-timer":       { weights: { dining: 0.20, drinks: 0.10, culture: 0.25, outdoors: 0.15, experience: 0.15, entertainment: 0.10, nightlife: 0.05 }, paceModifier: 0 },
  "weekend-sprint":    { weights: { dining: 0.20, drinks: 0.10, culture: 0.20, outdoors: 0.15, experience: 0.25, nightlife: 0.10 }, paceModifier: 1 },
};

// Default balanced weights when no template selected
export const DEFAULT_WEIGHTS: Record<string, number> = {
  dining: 0.20, drinks: 0.10, culture: 0.15, outdoors: 0.15,
  experience: 0.15, entertainment: 0.10, nightlife: 0.05,
  shopping: 0.05, wellness: 0.05,
};

export const PACE_SLOTS_PER_DAY: Record<Pace, number> = {
  packed: 6,
  moderate: 4,
  relaxed: 2,
};

export const MORNING_START_HOUR: Record<MorningPreference, number> = {
  early: 7.5,   // 07:30
  mid: 9,       // 09:00
  late: 10.5,   // 10:30
};
