import "server-only";
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { LAUNCH_CITIES } from "@/lib/cities";

// ---------- Zod schema for LLM output ----------

const resolvedCitySchema = z.object({
  city: z.string().min(1).max(100),
  country: z.string().min(1).max(100),
  timezone: z.string().min(1).max(100),
  destination: z.string().min(1).max(200),
});

export type ResolvedCity = z.infer<typeof resolvedCitySchema>;

// ---------- Rate limiter ----------

const rateLimitMap = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 20;
const RATE_WINDOW_MS = 60 * 60 * 1000; // 1 hour

/**
 * Returns true if the userId is within the allowed rate limit, false if exceeded.
 */
export function checkRateLimit(userId: string): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(userId);

  if (!entry || entry.resetAt < now) {
    rateLimitMap.set(userId, { count: 1, resetAt: now + RATE_WINDOW_MS });
    return true;
  }

  if (entry.count >= RATE_LIMIT) {
    return false;
  }

  entry.count++;
  return true;
}

// ---------- Anthropic client ----------

const client = new Anthropic();

// ---------- City resolver ----------

/**
 * Resolves a freeform city name to structured city data.
 *
 * 1. Checks LAUNCH_CITIES for a case-insensitive match first.
 * 2. Falls back to claude-haiku-4-5-20251001 via tool_use for unknown cities.
 * 3. Validates the LLM response against resolvedCitySchema before returning.
 */
export async function resolveCity(cityInput: string): Promise<ResolvedCity> {
  const normalized = cityInput.trim().toLowerCase();

  // Fast path: check launch cities
  const match = LAUNCH_CITIES.find(
    (c) => c.city.toLowerCase() === normalized
  );
  if (match) {
    return match;
  }

  // Slow path: LLM resolution for unknown cities
  const response = await client.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 200,
    tool_choice: { type: "any" },
    tools: [
      {
        name: "resolve_city",
        description:
          "Resolve a freeform city name to structured city data. Return the canonical city name, country, IANA timezone identifier, and a destination string formatted as 'City, Country'.",
        input_schema: {
          type: "object",
          properties: {
            city: {
              type: "string",
              description: "Canonical city name, e.g. 'Barcelona'",
            },
            country: {
              type: "string",
              description: "Country name in English, e.g. 'Spain'",
            },
            timezone: {
              type: "string",
              description: "IANA timezone identifier, e.g. 'Europe/Madrid'",
            },
            destination: {
              type: "string",
              description: "Formatted destination string, e.g. 'Barcelona, Spain'",
            },
          },
          required: ["city", "country", "timezone", "destination"],
        },
      },
    ],
    messages: [
      {
        role: "user",
        content: `Resolve this city name to structured data: <user_city_name>${cityInput}</user_city_name>`,
      },
    ],
  });

  // Extract tool_use block
  const toolUse = response.content.find((block) => block.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") {
    throw new Error(
      `[city-resolver] LLM did not return a tool_use block for input: "${cityInput}"`
    );
  }

  // Validate against schema
  const parsed = resolvedCitySchema.safeParse(toolUse.input);
  if (!parsed.success) {
    const issues = parsed.error.flatten().fieldErrors;
    throw new Error(
      `[city-resolver] LLM response failed schema validation for input "${cityInput}": ${JSON.stringify(issues)}`
    );
  }

  return parsed.data;
}
