// City photo URLs from Unsplash.
// Single source of truth for city destination photos across the app.

/**
 * City photo URLs from Unsplash (without query parameters).
 */
const CITY_PHOTOS: Record<string, string> = {
  Tokyo:
    "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf",
  Kyoto:
    "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e",
  Osaka:
    "https://images.unsplash.com/photo-1590559899731-a382839e5549",
  Bangkok:
    "https://images.unsplash.com/photo-1508009603885-50cf7c579365",
  Seoul:
    "https://images.unsplash.com/photo-1534274988757-a28bf1a57c17",
  Taipei:
    "https://images.unsplash.com/photo-1470004914212-05527e49370b",
  Lisbon:
    "https://images.unsplash.com/photo-1558618666-fcd25c85f82e",
  Barcelona:
    "https://images.unsplash.com/photo-1583422409516-2895a77efded",
  "Mexico City":
    "https://images.unsplash.com/photo-1585464231875-d9ef1f5ad396",
  "New York":
    "https://images.unsplash.com/photo-1496442226666-8d4d0e62e6e9",
  London:
    "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad",
  Paris:
    "https://images.unsplash.com/photo-1502602898657-3e91760cbb34",
  Berlin:
    "https://images.unsplash.com/photo-1560969184-10fe8719e047",
  Rome:
    "https://images.unsplash.com/photo-1552832230-c0197dd311b5",
  Istanbul:
    "https://images.unsplash.com/photo-1524231757912-21f4fe3a7200",
};

const FALLBACK_PHOTO =
  "https://images.unsplash.com/photo-1488646953014-85cb44e25828";

/**
 * Get the Unsplash photo URL for a given city with size parameters.
 * @param city - City name (case-sensitive, matches keys in CITY_PHOTOS)
 * @param width - Image width in pixels (default: 1200)
 * @param quality - Image quality 1-100 (default: 80)
 * @returns Unsplash URL with size parameters, or fallback photo if city not found
 */
export function getCityPhoto(
  city: string,
  width: number = 1200,
  quality: number = 80
): string {
  const baseUrl = CITY_PHOTOS[city] ?? FALLBACK_PHOTO;
  return `${baseUrl}?w=${width}&q=${quality}`;
}
