import { z } from "zod";

export const updateAccountSchema = z.object({
  name: z.string().trim().min(1, "Name cannot be empty").max(100, "Name is too long"),
});

// Allowlists for preference arrays (future use)
export const DIETARY_OPTIONS = [
  "vegan",
  "vegetarian",
  "halal",
  "kosher",
  "gluten-free",
  "nut-allergy",
  "shellfish",
  "dairy-free",
  "pescatarian",
  "no-pork",
] as const;

export const MOBILITY_OPTIONS = [
  "wheelchair",
  "low-step",
  "elevator-required",
  "sensory-friendly",
  "service-animal",
  "limited-stamina",
] as const;

export const LANGUAGE_OPTIONS = [
  "non-english-menus",
  "limited-english-staff",
] as const;

export const TRAVEL_FREQUENCY_OPTIONS = [
  "few-times-year",
  "monthly",
  "constantly",
] as const;

export const VIBE_PREFERENCE_OPTIONS = [
  "high-energy", "slow-burn", "immersive",
  "hidden-gem", "iconic-worth-it", "locals-only", "offbeat",
  "destination-meal", "street-food", "local-institution", "drinks-forward",
  "nature-immersive", "urban-exploration", "deep-history", "contemporary-culture", "hands-on", "scenic",
  "late-night", "early-morning", "solo-friendly", "group-friendly", "social-scene", "low-interaction",
] as const;

export const BUDGET_OPTIONS = ["budget", "mid-range", "splurge", "mix"] as const;
export const SPENDING_PRIORITY_OPTIONS = ["food-drink", "experiences", "accommodation", "shopping"] as const;
export const ACCOMMODATION_OPTIONS = ["hostel", "boutique-hotel", "chain-hotel", "airbnb", "camping"] as const;
export const TRANSIT_OPTIONS = ["walking", "public-transit", "rideshare", "rental-car", "biking", "scooter"] as const;

export const DISTANCE_UNITS = ["mi", "km"] as const;
export const TEMPERATURE_UNITS = ["F", "C"] as const;
export const DATE_FORMATS = ["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"] as const;
export const TIME_FORMATS = ["12h", "24h"] as const;
export const THEME_OPTIONS = ["light", "dark", "system"] as const;

export const PRE_TRIP_DAYS = [1, 3, 7] as const;

export const updatePreferencesSchema = z
  .object({
    dietary: z.array(z.enum(DIETARY_OPTIONS)).max(10).optional(),
    mobility: z.array(z.enum(MOBILITY_OPTIONS)).max(10).optional(),
    languages: z.array(z.enum(LANGUAGE_OPTIONS)).max(5).optional(),
    travelFrequency: z.enum(TRAVEL_FREQUENCY_OPTIONS).nullable().optional(),
    vibePreferences: z.array(z.enum(VIBE_PREFERENCE_OPTIONS)).max(23).optional(),
    // SECURITY: travelStyleNote MUST use delimiter isolation (<user_note> tags) when
    // fed to any LLM for persona extraction. Never pass raw text as instructions.
    travelStyleNote: z.string().max(500).optional(),
    budgetComfort: z.enum(BUDGET_OPTIONS).nullable().optional(),
    spendingPriorities: z.array(z.enum(SPENDING_PRIORITY_OPTIONS)).max(4).optional(),
    accommodationTypes: z.array(z.enum(ACCOMMODATION_OPTIONS)).max(5).optional(),
    transitModes: z.array(z.enum(TRANSIT_OPTIONS)).max(6).optional(),
    // SECURITY: preferencesNote MUST use delimiter isolation (<user_note> tags) when
    // fed to any LLM for persona extraction. Never pass raw text as instructions.
    preferencesNote: z.string().max(500).optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");

export const updateDisplaySchema = z
  .object({
    distanceUnit: z.enum(DISTANCE_UNITS).optional(),
    temperatureUnit: z.enum(TEMPERATURE_UNITS).optional(),
    dateFormat: z.enum(DATE_FORMATS).optional(),
    timeFormat: z.enum(TIME_FORMATS).optional(),
    theme: z.enum(THEME_OPTIONS).optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");

export const updateNotificationsSchema = z
  .object({
    tripReminders: z.boolean().optional(),
    morningBriefing: z.boolean().optional(),
    groupActivity: z.boolean().optional(),
    postTripPrompt: z.boolean().optional(),
    citySeeded: z.boolean().optional(),
    inspirationNudges: z.boolean().optional(),
    productUpdates: z.boolean().optional(),
    checkinReminder: z.boolean().optional(),
    preTripDaysBefore: z.number().int().refine(v => [1, 3, 7].includes(v), "Must be 1, 3, or 7").optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");

export const updateConsentSchema = z
  .object({
    modelTraining: z.boolean().optional(),
    anonymizedResearch: z.boolean().optional(),
  })
  .refine((obj) => Object.keys(obj).length > 0, "At least one field required");

export const deleteAccountSchema = z.object({
  confirmEmail: z.string().email("Valid email required"),
});
