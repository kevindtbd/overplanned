import { z } from "zod";

const stripHtml = (val: string) => val.replace(/<[^>]*>/g, "").trim();

export const reflectionSchema = z.object({
  ratings: z
    .array(
      z.object({
        slotId: z.string().uuid(),
        rating: z.enum(["loved", "skipped", "missed"]),
      })
    )
    .min(1)
    .max(100),
  feedback: z.string().max(500).transform(stripHtml).optional(),
});

export type ReflectionInput = z.infer<typeof reflectionSchema>;

/** Signal values for behavioral logging keyed by rating */
export const REFLECTION_SIGNAL_MAP: Record<
  string,
  { signalType: "post_loved" | "post_skipped" | "post_missed"; signalValue: number }
> = {
  loved: { signalType: "post_loved", signalValue: 1.0 },
  skipped: { signalType: "post_skipped", signalValue: -0.5 },
  missed: { signalType: "post_missed", signalValue: 0.8 },
};
