import { z } from "zod";

export const voteSchema = z.object({
  vote: z.enum(["yes", "no", "maybe"]),
});

export type VoteInput = z.infer<typeof voteSchema>;

/** Signal values for behavioral logging */
export const VOTE_SIGNAL_VALUES: Record<string, number> = {
  yes: 1.0,
  maybe: 0.5,
  no: -1.0,
};

/** 70% yes-only threshold for auto-confirmation */
export const VOTE_CONFIRM_THRESHOLD = 0.7;
