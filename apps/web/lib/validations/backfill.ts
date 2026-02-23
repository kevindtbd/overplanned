import { z } from "zod";

export const backfillSubmitSchema = z.object({
  text: z
    .string()
    .min(1, "Text is required")
    .max(10_000, "Text must be under 10,000 characters"),
  cityHint: z.string().max(200).optional(),
  dateRangeHint: z.string().max(200).optional(),
  contextTag: z
    .enum(["solo", "partner", "family", "friends", "work"])
    .optional(),
});

export const backfillTripPatchSchema = z
  .object({
    contextTag: z
      .enum(["solo", "partner", "family", "friends", "work"])
      .optional(),
    tripNote: z
      .string()
      .max(5_000, "Trip note must be under 5,000 characters")
      .optional(),
  })
  .refine((data) => data.contextTag !== undefined || data.tripNote !== undefined, {
    message: "At least one field (contextTag or tripNote) must be provided",
  });

export const backfillVenuePatchSchema = z.object({
  wouldReturn: z.boolean(),
});
