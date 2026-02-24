/**
 * Derives a booking hint for an activity node based on available contact info and hours.
 *
 * Priority chain:
 * 1. URL with booking keyword in path -> "reservable online"
 * 2. URL without booking keyword -> "check website"
 * 3. Phone only (no URL) -> "call ahead"
 * 4. Hours with any window < 4h (no URL, no phone) -> "limited hours"
 * 5. Otherwise -> "walk-in"
 */
export function deriveBookingHint(
  node: {
    phoneNumber?: string | null;
    websiteUrl?: string | null;
    hours?: unknown;
  } | null
): string {
  if (!node) return "walk-in";

  const { phoneNumber, websiteUrl, hours } = node;

  // Check URL first (highest priority)
  if (websiteUrl) {
    try {
      const url = new URL(websiteUrl);
      const pathname = url.pathname.toLowerCase();
      if (
        pathname.includes("/reserve") ||
        pathname.includes("/book") ||
        pathname.includes("/reservation")
      ) {
        return "reservable online";
      }
    } catch {
      // Invalid URL — treat as no URL, fall through
      if (phoneNumber) return "call ahead";
      return checkHours(hours);
    }
    // Valid URL, no booking keywords
    return "check website";
  }

  // Phone only (no URL)
  if (phoneNumber) return "call ahead";

  // Check hours (no URL, no phone)
  return checkHours(hours);
}

function checkHours(hours: unknown): string {
  if (hours && typeof hours === "object" && !Array.isArray(hours)) {
    try {
      const record = hours as Record<string, unknown>;
      for (const day of Object.keys(record)) {
        const slots = record[day];
        if (!Array.isArray(slots)) continue;
        for (const slot of slots) {
          if (
            slot &&
            typeof slot === "object" &&
            "open" in slot &&
            "close" in slot &&
            typeof slot.open === "string" &&
            typeof slot.close === "string"
          ) {
            const openMinutes = parseTimeToMinutes(slot.open);
            const closeMinutes = parseTimeToMinutes(slot.close);
            if (openMinutes !== null && closeMinutes !== null) {
              const window = closeMinutes - openMinutes;
              if (window > 0 && window < 240) {
                return "limited hours";
              }
            }
          }
        }
      }
    } catch {
      // Malformed hours — skip gracefully
    }
  }
  return "walk-in";
}

function parseTimeToMinutes(time: string): number | null {
  const parts = time.split(":");
  if (parts.length !== 2) return null;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) return null;
  return h * 60 + m;
}
