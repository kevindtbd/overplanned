// Canonical city data for all seeded launch cities.
// Single source of truth — imported by CityCombobox, DestinationStep, city-resolver, QuickStartGrid.
// Must be isomorphic (no "server-only") — used by client components.
//
// Slugs are a closed vocabulary. Any route accepting a slug as a URL param
// must validate against LAUNCH_CITIES.map(c => c.slug) before use.

export interface CityData {
  slug: string;
  city: string;
  state: string;
  country: string;
  timezone: string;
  destination: string;
  lat: number;
  lng: number;
}

export const LAUNCH_CITIES: CityData[] = [
  { slug: "asheville", city: "Asheville", state: "NC", country: "United States", timezone: "America/New_York", destination: "Asheville, NC", lat: 35.55, lng: -82.55 },
  { slug: "austin", city: "Austin", state: "TX", country: "United States", timezone: "America/Chicago", destination: "Austin, TX", lat: 30.33, lng: -97.75 },
  { slug: "bend", city: "Bend", state: "OR", country: "United States", timezone: "America/Los_Angeles", destination: "Bend, OR", lat: 44.05, lng: -121.31 },
  { slug: "bozeman", city: "Bozeman", state: "MT", country: "United States", timezone: "America/Denver", destination: "Bozeman, MT", lat: 45.67, lng: -111.04 },
  { slug: "burlington", city: "Burlington", state: "VT", country: "United States", timezone: "America/New_York", destination: "Burlington, VT", lat: 44.47, lng: -73.21 },
  { slug: "columbus", city: "Columbus", state: "OH", country: "United States", timezone: "America/New_York", destination: "Columbus, OH", lat: 40.0, lng: -82.96 },
  { slug: "denver", city: "Denver", state: "CO", country: "United States", timezone: "America/Denver", destination: "Denver, CO", lat: 39.76, lng: -104.91 },
  { slug: "detroit", city: "Detroit", state: "MI", country: "United States", timezone: "America/Detroit", destination: "Detroit, MI", lat: 42.37, lng: -83.1 },
  { slug: "durango", city: "Durango", state: "CO", country: "United States", timezone: "America/Denver", destination: "Durango, CO", lat: 37.27, lng: -107.88 },
  { slug: "durham", city: "Durham", state: "NC", country: "United States", timezone: "America/New_York", destination: "Durham, NC", lat: 35.99, lng: -78.92 },
  { slug: "flagstaff", city: "Flagstaff", state: "AZ", country: "United States", timezone: "America/Phoenix", destination: "Flagstaff, AZ", lat: 35.2, lng: -111.65 },
  { slug: "fort-collins", city: "Fort Collins", state: "CO", country: "United States", timezone: "America/Denver", destination: "Fort Collins, CO", lat: 40.56, lng: -105.08 },
  { slug: "hood-river", city: "Hood River", state: "OR", country: "United States", timezone: "America/Los_Angeles", destination: "Hood River, OR", lat: 45.71, lng: -121.53 },
  { slug: "jackson-hole", city: "Jackson Hole", state: "WY", country: "United States", timezone: "America/Denver", destination: "Jackson Hole, WY", lat: 43.48, lng: -110.76 },
  { slug: "madison", city: "Madison", state: "WI", country: "United States", timezone: "America/Chicago", destination: "Madison, WI", lat: 43.08, lng: -89.4 },
  { slug: "mammoth-lakes", city: "Mammoth Lakes", state: "CA", country: "United States", timezone: "America/Los_Angeles", destination: "Mammoth Lakes, CA", lat: 37.65, lng: -118.97 },
  { slug: "mexico-city", city: "Mexico City", state: "", country: "Mexico", timezone: "America/Mexico_City", destination: "Mexico City, Mexico", lat: 19.4, lng: -99.15 },
  { slug: "missoula", city: "Missoula", state: "MT", country: "United States", timezone: "America/Denver", destination: "Missoula, MT", lat: 46.87, lng: -114.0 },
  { slug: "moab", city: "Moab", state: "UT", country: "United States", timezone: "America/Denver", destination: "Moab, UT", lat: 38.57, lng: -109.54 },
  { slug: "nashville", city: "Nashville", state: "TN", country: "United States", timezone: "America/Chicago", destination: "Nashville, TN", lat: 36.1, lng: -86.84 },
  { slug: "new-orleans", city: "New Orleans", state: "LA", country: "United States", timezone: "America/Chicago", destination: "New Orleans, LA", lat: 29.97, lng: -90.03 },
  { slug: "portland", city: "Portland", state: "OR", country: "United States", timezone: "America/Los_Angeles", destination: "Portland, OR", lat: 45.52, lng: -122.67 },
  { slug: "portland-me", city: "Portland", state: "ME", country: "United States", timezone: "America/New_York", destination: "Portland, ME", lat: 43.67, lng: -70.28 },
  { slug: "seattle", city: "Seattle", state: "WA", country: "United States", timezone: "America/Los_Angeles", destination: "Seattle, WA", lat: 47.62, lng: -122.34 },
  { slug: "sedona", city: "Sedona", state: "AZ", country: "United States", timezone: "America/Phoenix", destination: "Sedona, AZ", lat: 34.87, lng: -111.77 },
  { slug: "tacoma", city: "Tacoma", state: "WA", country: "United States", timezone: "America/Los_Angeles", destination: "Tacoma, WA", lat: 47.25, lng: -122.47 },
  { slug: "taos", city: "Taos", state: "NM", country: "United States", timezone: "America/Denver", destination: "Taos, NM", lat: 36.41, lng: -105.57 },
  { slug: "telluride", city: "Telluride", state: "CO", country: "United States", timezone: "America/Denver", destination: "Telluride, CO", lat: 37.94, lng: -107.81 },
  { slug: "truckee", city: "Truckee", state: "CA", country: "United States", timezone: "America/Los_Angeles", destination: "Truckee, CA", lat: 39.33, lng: -120.18 },
  { slug: "tucson", city: "Tucson", state: "AZ", country: "United States", timezone: "America/Phoenix", destination: "Tucson, AZ", lat: 32.24, lng: -110.92 },
];

/** Find a city by its unique slug. Returns undefined if not found. */
export function findCity(slug: string): CityData | undefined {
  return LAUNCH_CITIES.find((c) => c.slug === slug);
}

/** Find a city by display name (exact, case-insensitive). Returns first match for ambiguous names like "Portland". */
export function getCityByName(name: string): CityData | undefined {
  const normalized = name.trim().toLowerCase();
  return LAUNCH_CITIES.find((c) => c.city.toLowerCase() === normalized);
}
