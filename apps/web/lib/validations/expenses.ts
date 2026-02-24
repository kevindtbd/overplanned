import { z } from "zod";

export const expenseCreateSchema = z.object({
  description: z.string().min(1).max(200).trim(),
  amountCents: z.number().int().positive().max(10_000_000),
  splitWith: z.array(z.string().uuid()).max(20).optional(),
  slotId: z.string().uuid().optional(),
});

export type ExpenseCreate = z.infer<typeof expenseCreateSchema>;
