import { z } from "zod";

const stripHtml = (val: string) => val.replace(/<[^>]*>/g, "").trim();

export const VIBE_OPTIONS = ["loved_it", "good_trip", "mixed_bag", "not_for_me"] as const;
export type VibeOption = (typeof VIBE_OPTIONS)[number];

export const VIBE_CHIP_MAP: Record<
  VibeOption,
  { signalType: "trip_vibe_rating"; signalValue: number; label: string }
> = {
  loved_it: { signalType: "trip_vibe_rating", signalValue: 1.0, label: "Loved it" },
  good_trip: { signalType: "trip_vibe_rating", signalValue: 0.5, label: "Good trip" },
  mixed_bag: { signalType: "trip_vibe_rating", signalValue: -0.25, label: "Mixed bag" },
  not_for_me: { signalType: "trip_vibe_rating", signalValue: -0.75, label: "Not for me" },
};

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
  vibe: z.enum(VIBE_OPTIONS).optional(),
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
