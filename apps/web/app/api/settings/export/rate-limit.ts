const RATE_LIMIT_MS = 10 * 60 * 1000; // 10 minutes
const rateLimitMap = new Map<string, number>();

export function checkRateLimit(userId: string): boolean {
  const lastExport = rateLimitMap.get(userId);
  return !!(lastExport && Date.now() - lastExport < RATE_LIMIT_MS);
}

export function recordRateLimit(userId: string): void {
  rateLimitMap.set(userId, Date.now());
}

// Exposed for test reset only
export function _resetRateLimitForTest(): void {
  rateLimitMap.clear();
}
