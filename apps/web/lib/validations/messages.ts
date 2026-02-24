import { z } from "zod";

export const messageCreateSchema = z
  .object({
    body: z.string().max(2000).default(""),
    slotRefId: z.string().uuid().optional(),
  })
  .refine((d) => d.slotRefId || (d.body && d.body.trim().length > 0), {
    message: "Body required when no slot reference",
  });

export const messageCursorSchema = z.object({
  cursor: z.string().uuid().optional(),
  limit: z.coerce.number().int().min(1).max(50).default(50),
});

export type MessageCreate = z.infer<typeof messageCreateSchema>;
export type MessageCursor = z.infer<typeof messageCursorSchema>;
