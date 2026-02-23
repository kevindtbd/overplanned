import { z } from "zod";

export const pivotCreateSchema = z.object({
  slotId: z.string().uuid(),
  trigger: z.enum(["user_mood", "user_request"]),
  reason: z.string().max(200).optional(),
});

export type PivotCreateInput = z.infer<typeof pivotCreateSchema>;

export const pivotResolveSchema = z.object({
  outcome: z.enum(["accepted", "rejected"]),
  selectedNodeId: z.string().uuid().optional(),
});

export type PivotResolveInput = z.infer<typeof pivotResolveSchema>;

/** Max active (proposed) pivots per trip */
export const MAX_ACTIVE_PIVOTS_PER_TRIP = 3;

/** Max active (proposed) pivots per slot */
export const MAX_ACTIVE_PIVOTS_PER_SLOT = 1;
