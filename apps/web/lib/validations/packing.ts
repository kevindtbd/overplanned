import { z } from "zod";

export const packingGenerateSchema = z
  .object({
    regenerate: z.boolean().default(false),
  })
  .optional();

export const packingCheckSchema = z.object({
  itemId: z.string().uuid(),
  checked: z.boolean(),
});

// Output validation for LLM response
export const packingItemSchema = z.object({
  id: z.string(),
  text: z.string().max(100),
  category: z.enum([
    "essentials",
    "clothing",
    "documents",
    "tech",
    "toiletries",
    "misc",
  ]),
  checked: z.boolean().default(false),
});

export const packingListSchema = z.object({
  items: z.array(packingItemSchema).max(50),
});

export const packingClaimSchema = z.object({
  itemId: z.string().uuid(),
  claimedBy: z.string().uuid().nullable(),
});

export type PackingItem = z.infer<typeof packingItemSchema>;
export type PackingList = z.infer<typeof packingListSchema>;
export type PackingClaim = z.infer<typeof packingClaimSchema>;
