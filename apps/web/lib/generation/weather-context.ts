/**
 * Weather context utility for RankingEvent denormalization.
 *
 * Provides structured climate context for a city + travel date.
 * Uses the existing climate_averages.json data when available,
 * falling back to month/season placeholders for unseeded cities.
 */

import { getClimateContext as getClimateString } from "@/lib/climate";

export interface WeatherContext {
  city: string;
  month: number;
  season: string;
  climateDescription: string | null;
}

/**
 * Build a weather context object for a city at a given travel date.
 * Returns structured data suitable for JSON serialization into RankingEvent.
 */
export function getWeatherContext(
  cityName: string,
  travelDate: Date,
): WeatherContext {
  const month = travelDate.getMonth() + 1;
  const season = getSeason(travelDate);

  // Try to get real climate data from the climate_averages.json
  const climateDescription = getClimateString(cityName, month);

  return {
    city: cityName,
    month,
    season,
    climateDescription,
  };
}

function getSeason(date: Date): string {
  const month = date.getMonth() + 1;
  if (month >= 3 && month <= 5) return "spring";
  if (month >= 6 && month <= 8) return "summer";
  if (month >= 9 && month <= 11) return "autumn";
  return "winter";
}
