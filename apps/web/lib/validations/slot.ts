import { z } from "zod";

// Valid status transitions (state machine guard)
const VALID_TRANSITIONS: Record<string, string[]> = {
  proposed: ["confirmed", "skipped"],
  voted: ["confirmed", "skipped"],
  confirmed: ["active", "skipped"],
  active: ["completed", "skipped"],
};

export const updateSlotStatusSchema = z.object({
  action: z.enum(["confirm", "skip", "lock"]),
});

export { VALID_TRANSITIONS };
