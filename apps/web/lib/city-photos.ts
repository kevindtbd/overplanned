// City photo URLs from Unsplash.
// Single source of truth for city destination photos across the app.
// Keyed by slug (not city name) to handle Portland OR vs Portland ME.

/**
 * City photo URLs from Unsplash (without query parameters).
 * Keyed by city slug from lib/cities.ts.
 */
const CITY_PHOTOS: Record<string, string> = {
  asheville:
    "https://images.unsplash.com/photo-1558618666-fcd25c85f82e",
  austin:
    "https://images.unsplash.com/photo-1531218150217-54595bc2b934",
  bend:
    "https://images.unsplash.com/photo-1516786786037-0c4e2ba4e95b",
  bozeman:
    "https://images.unsplash.com/photo-1506748686214-e9df14d4d9d0",
  burlington:
    "https://images.unsplash.com/photo-1601312319960-0dae50e3b6cb",
  columbus:
    "https://images.unsplash.com/photo-1564250804908-e3247c15dda5",
  denver:
    "https://images.unsplash.com/photo-1546156929-a4c0ac411f47",
  detroit:
    "https://images.unsplash.com/photo-1534430480872-3498386e7856",
  durango:
    "https://images.unsplash.com/photo-1501785888041-af3ef285b470",
  durham:
    "https://images.unsplash.com/photo-1572120360610-d971b9d7767c",
  flagstaff:
    "https://images.unsplash.com/photo-1474044159687-1ee9f3a51722",
  "fort-collins":
    "https://images.unsplash.com/photo-1500534623283-312aade485b7",
  "hood-river":
    "https://images.unsplash.com/photo-1548041347-390744c58da9",
  "jackson-hole":
    "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4",
  madison:
    "https://images.unsplash.com/photo-1596003903657-7e9b3cf704e9",
  "mammoth-lakes":
    "https://images.unsplash.com/photo-1491002052546-bf38f186af56",
  "mexico-city":
    "https://images.unsplash.com/photo-1585464231875-d9ef1f5ad396",
  missoula:
    "https://images.unsplash.com/photo-1472396961693-142e6e269027",
  moab:
    "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800",
  nashville:
    "https://images.unsplash.com/photo-1545419913-775295e2ef69",
  "new-orleans":
    "https://images.unsplash.com/photo-1568402102990-bc541580b59f",
  portland:
    "https://images.unsplash.com/photo-1544892709-22b04bffc780",
  "portland-me":
    "https://images.unsplash.com/photo-1576669801775-ff43c5ab079d",
  seattle:
    "https://images.unsplash.com/photo-1502175353174-a7a70e73b4c3",
  sedona:
    "https://images.unsplash.com/photo-1527549993586-dff825b37782",
  tacoma:
    "https://images.unsplash.com/photo-1542362567-b07e54358753",
  taos:
    "https://images.unsplash.com/photo-1499678329028-101435549a4e",
  telluride:
    "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b",
  truckee:
    "https://images.unsplash.com/photo-1485470733090-0aae1788d668",
  tucson:
    "https://images.unsplash.com/photo-1518791841217-8f162f1e1131",
};

const FALLBACK_PHOTO =
  "https://images.unsplash.com/photo-1488646953014-85cb44e25828";

/**
 * Get the Unsplash photo URL for a given city with size parameters.
 * Accepts slug (preferred) or city name as fallback.
 * @param cityOrSlug - City slug or display name
 * @param width - Image width in pixels (default: 1200)
 * @param quality - Image quality 1-100 (default: 80)
 * @returns Unsplash URL with size parameters, or fallback photo if not found
 */
export function getCityPhoto(
  cityOrSlug: string,
  width: number = 1200,
  quality: number = 80
): string {
  const baseUrl = CITY_PHOTOS[cityOrSlug] ?? FALLBACK_PHOTO;
  return `${baseUrl}?w=${width}&q=${quality}`;
}
