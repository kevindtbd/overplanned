/**
 * In-memory sliding window rate limiter for admin proxy.
 *
 * Keyed on userId (not IP -- all requests come from same proxy).
 * Separate limits for reads (GET) and mutations (POST/PATCH/DELETE).
 *
 * Known limitation: resets on cold start / multi-instance.
 * Acceptable for 1-2 admin users in beta.
 */

interface WindowEntry {
  timestamps: number[];
}

const READ_LIMIT = 60; // requests per minute
const MUTATION_LIMIT = 10; // requests per minute
const WINDOW_MS = 60_000; // 1 minute
const CLEANUP_INTERVAL_MS = 5 * 60_000; // 5 minutes

const readWindows = new Map<string, WindowEntry>();
const mutationWindows = new Map<string, WindowEntry>();

// Periodic cleanup of stale entries
let cleanupTimer: ReturnType<typeof setInterval> | null = null;

function ensureCleanup(): void {
  if (cleanupTimer) return;
  cleanupTimer = setInterval(() => {
    const cutoff = Date.now() - WINDOW_MS;
    for (const [key, entry] of readWindows) {
      entry.timestamps = entry.timestamps.filter((t) => t > cutoff);
      if (entry.timestamps.length === 0) readWindows.delete(key);
    }
    for (const [key, entry] of mutationWindows) {
      entry.timestamps = entry.timestamps.filter((t) => t > cutoff);
      if (entry.timestamps.length === 0) mutationWindows.delete(key);
    }
  }, CLEANUP_INTERVAL_MS);
  // Don't prevent Node.js from exiting
  if (cleanupTimer && typeof cleanupTimer === "object" && "unref" in cleanupTimer) {
    cleanupTimer.unref();
  }
}

export interface RateLimitResult {
  allowed: boolean;
  retryAfter?: number; // seconds until next allowed request
}

/**
 * Check and record a rate-limited request.
 *
 * @param userId - Admin user ID (rate limit key)
 * @param method - HTTP method (GET = read, others = mutation)
 * @returns Whether the request is allowed
 */
export function checkRateLimit(
  userId: string,
  method: string
): RateLimitResult {
  ensureCleanup();

  const isRead = method === "GET";
  const windows = isRead ? readWindows : mutationWindows;
  const limit = isRead ? READ_LIMIT : MUTATION_LIMIT;

  const now = Date.now();
  const cutoff = now - WINDOW_MS;

  let entry = windows.get(userId);
  if (!entry) {
    entry = { timestamps: [] };
    windows.set(userId, entry);
  }

  // Prune expired timestamps
  entry.timestamps = entry.timestamps.filter((t) => t > cutoff);

  if (entry.timestamps.length >= limit) {
    // Calculate retry-after from oldest timestamp in window
    const oldestInWindow = entry.timestamps[0];
    const retryAfter = Math.ceil((oldestInWindow + WINDOW_MS - now) / 1000);
    return { allowed: false, retryAfter: Math.max(1, retryAfter) };
  }

  // Record this request
  entry.timestamps.push(now);
  return { allowed: true };
}

/**
 * Reset rate limit state (for testing).
 */
export function resetRateLimits(): void {
  readWindows.clear();
  mutationWindows.clear();
}
