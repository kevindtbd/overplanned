import { z } from "zod";

export const inviteCreateSchema = z.object({
  maxUses: z.number().int().min(1).max(100).default(10),
  expiresInDays: z.number().int().min(1).max(30).default(7),
});

export const joinQuerySchema = z.object({
  token: z.string().min(10).max(64).regex(/^[A-Za-z0-9_-]+$/),
});
