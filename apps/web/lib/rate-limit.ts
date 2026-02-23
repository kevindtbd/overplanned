import { NextRequest, NextResponse } from "next/server";

interface RateLimitConfig {
  limit: number;
  windowMs: number;
}

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

const store = new Map<string, RateLimitEntry>();

// Cleanup expired entries every 5 minutes
setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of store.entries()) {
    if (entry.resetAt < now) {
      store.delete(key);
    }
  }
}, 5 * 60 * 1000);

function getKey(req: NextRequest, identifier?: string): string {
  if (identifier) return identifier;

  // Try to get IP from headers
  const forwarded = req.headers.get("x-forwarded-for");
  const ip = forwarded ? forwarded.split(",")[0].trim() : "unknown";

  return ip;
}

function checkLimit(key: string, config: RateLimitConfig): boolean {
  const now = Date.now();
  const entry = store.get(key);

  if (!entry || entry.resetAt < now) {
    // First request or window expired
    store.set(key, {
      count: 1,
      resetAt: now + config.windowMs,
    });
    return true;
  }

  if (entry.count >= config.limit) {
    return false;
  }

  entry.count++;
  return true;
}

export function rateLimit(
  req: NextRequest,
  config: RateLimitConfig,
  identifier?: string
): NextResponse | null {
  const key = getKey(req, identifier);
  const allowed = checkLimit(key, config);

  if (!allowed) {
    return NextResponse.json(
      { error: "Too many requests, please try again later" },
      { status: 429 }
    );
  }

  return null;
}

// Preset configurations
export const rateLimitPresets = {
  public: { limit: 30, windowMs: 60 * 1000 }, // 30 req/min
  authenticated: { limit: 10, windowMs: 60 * 1000 }, // 10 req/min
  llm: { limit: 3, windowMs: 60 * 60 * 1000 }, // 3 req/hour
};
