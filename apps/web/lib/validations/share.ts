import { z } from "zod";

/**
 * POST /api/trips/[id]/share — create a share token
 */
export const shareCreateSchema = z.object({
  expiresInDays: z.number().int().min(1).max(90).default(30),
});

/**
 * POST /api/shared/[token]/import — no body needed, just auth
 */
export const importSchema = z.object({}).optional();

/**
 * Token format validation — reused across GET + import routes
 * base64url charset only, 10-64 chars
 */
export const TOKEN_REGEX = /^[A-Za-z0-9\-_]{10,64}$/;

export function sanitizeToken(raw: string): string | null {
  const cleaned = raw.replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 64);
  if (!TOKEN_REGEX.test(cleaned)) return null;
  return cleaned;
}
