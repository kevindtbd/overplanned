import { z } from "zod";

export const createDraftSchema = z.object({
  destination: z.string().min(1).max(200),
  city: z.string().min(1).max(200),
  country: z.string().min(1).max(100),
  timezone: z.string().min(1).max(100),
  startDate: z.string().datetime(),
  endDate: z.string().datetime(),
});

export const createTripSchema = z.object({
  name: z.string().min(1).max(200).optional(),
  destination: z.string().min(1).max(200),
  city: z.string().min(1).max(200),
  country: z.string().min(1).max(100),
  timezone: z.string().min(1).max(100),
  startDate: z.string().datetime(),
  endDate: z.string().datetime(),
  mode: z.enum(["solo", "group"]),
  presetTemplate: z.string().optional(),
  personaSeed: z.record(z.unknown())
    .refine(
      (val) => JSON.stringify(val).length <= 10_000,
      { message: "personaSeed must be under 10KB" }
    )
    .optional(),
});

export const updateTripSchema = z.object({
  name: z.string().min(1).max(200).optional(),
  status: z.enum(["draft", "planning", "active", "completed", "archived"]).optional(),
  planningProgress: z.number().min(0).max(1).optional(),
  startDate: z.string().datetime().optional(),
  endDate: z.string().datetime().optional(),
  mode: z.enum(["solo", "group"]).optional(),
  presetTemplate: z.string().optional(),
  personaSeed: z.record(z.unknown())
    .refine(
      (val) => JSON.stringify(val).length <= 10_000,
      { message: "personaSeed must be under 10KB" }
    )
    .optional(),
});
