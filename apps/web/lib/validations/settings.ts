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
] as const;

export const MOBILITY_OPTIONS = [
  "wheelchair",
  "low-step",
  "elevator-required",
  "sensory-friendly",
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

export const updatePreferencesSchema = z.object({
  dietary: z.array(z.enum(DIETARY_OPTIONS)).max(10).optional(),
  mobility: z.array(z.enum(MOBILITY_OPTIONS)).max(10).optional(),
  languages: z.array(z.enum(LANGUAGE_OPTIONS)).max(5).optional(),
  travelFrequency: z.enum(TRAVEL_FREQUENCY_OPTIONS).nullable().optional(),
});

export const updateNotificationsSchema = z.object({
  tripReminders: z.boolean().optional(),
  morningBriefing: z.boolean().optional(),
  groupActivity: z.boolean().optional(),
  postTripPrompt: z.boolean().optional(),
  citySeeded: z.boolean().optional(),
  inspirationNudges: z.boolean().optional(),
  productUpdates: z.boolean().optional(),
});

export const updateConsentSchema = z.object({
  modelTraining: z.boolean().optional(),
  anonymizedResearch: z.boolean().optional(),
});
