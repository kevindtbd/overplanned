// Rate limiting (in-memory, per-user sliding window)
// Extracted from route.ts so tests can access rateLimitMap without
// exporting from a Next.js route file (which rejects non-handler exports).

const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute
const MAX_SIGNALS_PER_WINDOW = 120;  // 2 per second average

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

export const rateLimitMap = new Map<string, RateLimitEntry>();

export function isRateLimited(userId: string): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(userId);

  if (!entry || now - entry.windowStart >= RATE_LIMIT_WINDOW_MS) {
    rateLimitMap.set(userId, { count: 1, windowStart: now });
    return false;
  }

  entry.count += 1;
  return entry.count > MAX_SIGNALS_PER_WINDOW;
}

export const ALLOWED_SIGNAL_TYPES = new Set([
  // Explicit (Tier 1)
  "slot_confirmed", "slot_rejected",
  "pre_trip_slot_swap", "pre_trip_slot_removed",
  // Strong implicit (Tier 2)
  "slot_locked", "pre_trip_slot_added", "pre_trip_reorder", "discover_shortlist",
  // Weak implicit (Tier 3)
  "card_viewed", "card_dismissed", "slot_moved",
  "discover_swipe_right", "discover_swipe_left",
  // Passive (Tier 4)
  "card_impression", "pivot_accepted", "pivot_rejected",
]);
