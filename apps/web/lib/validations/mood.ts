import { z } from "zod";

export const moodSchema = z.object({
  mood: z.enum(["high", "medium", "low"]),
});

export type MoodInput = z.infer<typeof moodSchema>;
