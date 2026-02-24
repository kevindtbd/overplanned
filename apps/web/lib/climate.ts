/**
 * Climate lookup utility for packing list generation.
 * Provides formatted weather context for LLM prompts.
 */

import climateData from "../../../data/climate_averages.json";

type ClimateEntry = {
  tempLowC: number;
  tempHighC: number;
  rainDays: number;
  conditions: string;
};

type ClimateCity = Record<string, ClimateEntry>;
type ClimateDB = Record<string, ClimateCity>;

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

let db: ClimateDB | null = null;

function getDb(): ClimateDB | null {
  if (db !== null) return db;
  try {
    db = climateData as ClimateDB;
    return db;
  } catch {
    return null;
  }
}

/**
 * Returns a formatted climate context string for a city + month, or null if not found.
 *
 * @param city   City name — normalized to lowercase, trimmed, spaces → underscores
 * @param month  Month number 1–12
 */
export function getClimateContext(city: string, month: number): string | null {
  try {
    if (month < 1 || month > 12 || !Number.isInteger(month)) return null;

    const database = getDb();
    if (!database) return null;

    const slug = city.trim().toLowerCase().replace(/\s+/g, "_");
    const cityData = database[slug];
    if (!cityData) return null;

    const entry = cityData[String(month)];
    if (!entry) return null;

    const monthName = MONTH_NAMES[month - 1];
    // Capitalize city slug for display: new_york → New York
    const cityDisplay = slug
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");

    return (
      `Typical weather for ${cityDisplay} in ${monthName}: ` +
      `${entry.tempLowC}-${entry.tempHighC}C, ` +
      `${entry.rainDays} rainy days typical. ` +
      `${entry.conditions}.`
    );
  } catch {
    return null;
  }
}
