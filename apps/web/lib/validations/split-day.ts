import { z } from "zod";

export const splitDaySchema = z.object({
  dayNumber: z.number().int().positive(),
  subgroups: z
    .array(
      z.object({
        memberIds: z.array(z.string().uuid()).min(1),
        slotIds: z.array(z.string().uuid()).min(1),
      })
    )
    .min(2)
    .max(4),
});

export type SplitDayInput = z.infer<typeof splitDaySchema>;
