import { z } from "zod";
import { MAX_TRIP_NIGHTS, MAX_TRIP_ADVANCE_YEARS } from "@/lib/constants/trip";
import { nightsBetween } from "@/lib/utils/dates";

// ---------- Shared sub-schemas ----------

/** Printable Unicode, no control chars, max 100 chars */
export const cityNameSchema = z
  .string()
  .min(1, "City name is required")
  .max(100, "City name must be under 100 characters")
  .regex(
    /^[\p{L}\p{M}\p{N}\p{P}\p{Z}\p{S}]+$/u,
    "City name contains invalid characters"
  );

export const transitModeSchema = z.enum([
  "flight",
  "train",
  "shinkansen",
  "bus",
  "car",
  "ferry",
]);

export const tripLegSchema = z.object({
  city: cityNameSchema,
  country: z.string().min(1).max(100),
  timezone: z.string().max(100).optional(),
  destination: z.string().min(1).max(200),
  startDate: z.string().datetime(),
  endDate: z.string().datetime(),
  arrivalTime: z.enum(["morning", "afternoon", "evening"]).optional(),
  departureTime: z.enum(["morning", "afternoon", "evening"]).optional(),
  transitMode: transitModeSchema.optional(),
  transitDurationMin: z.number().int().min(0).max(10080).optional(),
  transitCostHint: z.string().max(100).optional(),
});

// ---------- Date range validation ----------

function validateDateRange(
  data: { startDate: string; endDate: string },
  ctx: z.RefinementCtx
) {
  const nights = nightsBetween(data.startDate, data.endDate);

  if (nights <= 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "End date must be after start date",
      path: ["endDate"],
    });
    return;
  }

  if (nights > MAX_TRIP_NIGHTS) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `Trip cannot exceed ${MAX_TRIP_NIGHTS} nights`,
      path: ["endDate"],
    });
  }

  // Extreme future date defense
  const startDate = new Date(data.startDate.slice(0, 10));
  const maxAdvance = new Date();
  maxAdvance.setFullYear(maxAdvance.getFullYear() + MAX_TRIP_ADVANCE_YEARS);
  if (startDate > maxAdvance) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `Start date cannot be more than ${MAX_TRIP_ADVANCE_YEARS} years in the future`,
      path: ["startDate"],
    });
  }
}

// ---------- Create schemas ----------

export const createDraftSchema = z
  .object({
    startDate: z.string().datetime(),
    endDate: z.string().datetime(),
    legs: z.array(tripLegSchema).min(1).max(8),
  })
  .superRefine(validateDateRange);

export const createTripSchema = z
  .object({
    name: z.string().min(1).max(200).optional(),
    startDate: z.string().datetime(),
    endDate: z.string().datetime(),
    mode: z.enum(["solo", "group"]),
    legs: z.array(tripLegSchema).min(1).max(8),
    presetTemplate: z.string().optional(),
    personaSeed: z
      .record(z.unknown())
      .refine((val) => JSON.stringify(val).length <= 10_000, {
        message: "personaSeed must be under 10KB",
      })
      .optional(),
  })
  .superRefine(validateDateRange);

// ---------- Update schemas ----------

export const updateTripSchema = z
  .object({
    name: z.string().min(1).max(200).optional(),
    status: z
      .enum(["draft", "planning", "active", "completed", "archived"])
      .optional(),
    planningProgress: z.number().min(0).max(1).optional(),
    startDate: z.string().datetime().optional(),
    endDate: z.string().datetime().optional(),
    mode: z.enum(["solo", "group"]).optional(),
    presetTemplate: z.string().optional(),
    personaSeed: z
      .record(z.unknown())
      .refine((val) => JSON.stringify(val).length <= 10_000, {
        message: "personaSeed must be under 10KB",
      })
      .optional(),
  })
  .superRefine((data, ctx) => {
    if (data.startDate !== undefined && data.endDate !== undefined) {
      const nights = nightsBetween(data.startDate, data.endDate);

      if (nights <= 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "End date must be after start date",
          path: ["endDate"],
        });
        return;
      }

      if (nights > MAX_TRIP_NIGHTS) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Trip cannot exceed ${MAX_TRIP_NIGHTS} nights`,
          path: ["endDate"],
        });
      }
    }
  });

/** For PATCH on individual leg fields (transit, arrival/departure time) */
export const updateLegSchema = z.object({
  arrivalTime: z.enum(["morning", "afternoon", "evening"]).nullable().optional(),
  departureTime: z.enum(["morning", "afternoon", "evening"]).nullable().optional(),
  transitMode: transitModeSchema.nullable().optional(),
  transitDurationMin: z.number().int().min(0).max(10080).nullable().optional(),
  transitCostHint: z.string().max(100).nullable().optional(),
  transitConfirmed: z.boolean().optional(),
});

// ---------- Leg CRUD schemas ----------

/** POST /api/trips/[id]/legs — Add a new leg */
export const addLegSchema = z.object({
  city: cityNameSchema,
  country: z.string().min(1).max(100),
  timezone: z.string().max(100).optional(),
  destination: z.string().min(1).max(200),
  startDate: z.string().datetime(),
  endDate: z.string().datetime(),
});

/** PATCH /api/trips/[id]/legs/[legId] — Edit leg city/dates */
export const patchLegSchema = z.object({
  city: cityNameSchema.optional(),
  country: z.string().min(1).max(100).optional(),
  timezone: z.string().max(100).nullable().optional(),
  destination: z.string().min(1).max(200).optional(),
  startDate: z.string().datetime().optional(),
  endDate: z.string().datetime().optional(),
});

/** POST /api/trips/[id]/legs/reorder — Reorder legs */
export const legReorderSchema = z.object({
  legOrder: z
    .array(z.string().uuid())
    .min(1, "legOrder must contain at least one ID")
    .max(8, "legOrder cannot exceed 8 legs"),
});

/** POST /api/cities/resolve — Resolve freeform city name */
export const cityResolveSchema = z.object({
  city: cityNameSchema,
});
