/**
 * Backfill migration: Create TripLeg records for trips that have none.
 *
 * Phase A removed city/country/destination/timezone from the Trip model
 * and moved them to TripLeg. Existing trips created before the migration
 * have zero legs, breaking image lookups and display.
 *
 * Strategy (in priority order):
 * 1. Infer city/country from the trip's first slot's ActivityNode
 * 2. Parse city name from trip.name (e.g. "Tokyo Feb 2026" → "Tokyo")
 * 3. Skip — log warning for manual review
 *
 * Usage:
 *   npx tsx scripts/backfill-trip-legs.ts          # dry run (default)
 *   npx tsx scripts/backfill-trip-legs.ts --apply   # actually write to DB
 */

import { PrismaClient } from "@prisma/client";
import { randomUUID } from "crypto";

const prisma = new PrismaClient();

const DRY_RUN = !process.argv.includes("--apply");

// Known cities from city-photos.ts + common test cities
const KNOWN_CITIES: Record<string, { country: string; timezone: string }> = {
  Tokyo: { country: "Japan", timezone: "Asia/Tokyo" },
  Kyoto: { country: "Japan", timezone: "Asia/Tokyo" },
  Osaka: { country: "Japan", timezone: "Asia/Tokyo" },
  Bangkok: { country: "Thailand", timezone: "Asia/Bangkok" },
  Seoul: { country: "South Korea", timezone: "Asia/Seoul" },
  Taipei: { country: "Taiwan", timezone: "Asia/Taipei" },
  Lisbon: { country: "Portugal", timezone: "Europe/Lisbon" },
  Barcelona: { country: "Spain", timezone: "Europe/Madrid" },
  "Mexico City": { country: "Mexico", timezone: "America/Mexico_City" },
  "New York": { country: "United States", timezone: "America/New_York" },
  London: { country: "United Kingdom", timezone: "Europe/London" },
  Paris: { country: "France", timezone: "Europe/Paris" },
  Berlin: { country: "Germany", timezone: "Europe/Berlin" },
  Rome: { country: "Italy", timezone: "Europe/Rome" },
  Istanbul: { country: "Turkey", timezone: "Europe/Istanbul" },
};

function parseCityFromName(name: string | null): string | null {
  if (!name) return null;
  // Try matching known cities in the trip name
  for (const city of Object.keys(KNOWN_CITIES)) {
    if (name.toLowerCase().includes(city.toLowerCase())) {
      return city;
    }
  }
  return null;
}

async function main() {
  console.log(`\n=== Backfill TripLeg Migration ${DRY_RUN ? "(DRY RUN)" : "(APPLYING)"} ===\n`);

  // Find all trips with zero legs
  const orphanTrips = await prisma.trip.findMany({
    where: { legs: { none: {} } },
    select: {
      id: true,
      name: true,
      status: true,
      startDate: true,
      endDate: true,
      slots: {
        select: {
          activityNode: {
            select: { city: true, country: true },
          },
        },
        take: 1,
      },
    },
    orderBy: { createdAt: "desc" },
  });

  console.log(`Found ${orphanTrips.length} trips with zero legs.\n`);

  let inferred = 0;
  let parsed = 0;
  let skipped = 0;
  const legsToCreate: Array<{
    id: string;
    tripId: string;
    position: number;
    city: string;
    country: string;
    timezone: string;
    destination: string;
    startDate: Date;
    endDate: Date;
  }> = [];

  for (const trip of orphanTrips) {
    let city: string | null = null;
    let country: string | null = null;
    let timezone: string | null = null;
    let source = "";

    // Strategy 1: Infer from first slot's activity node
    const slotCity = trip.slots[0]?.activityNode?.city;
    const slotCountry = trip.slots[0]?.activityNode?.country;
    if (slotCity) {
      city = slotCity;
      country = slotCountry ?? KNOWN_CITIES[slotCity]?.country ?? "Unknown";
      timezone = KNOWN_CITIES[slotCity]?.timezone ?? null;
      source = "slot";
      inferred++;
    }

    // Strategy 2: Parse from trip name
    if (!city) {
      const parsedCity = parseCityFromName(trip.name);
      if (parsedCity) {
        city = parsedCity;
        country = KNOWN_CITIES[parsedCity]?.country ?? "Unknown";
        timezone = KNOWN_CITIES[parsedCity]?.timezone ?? null;
        source = "name";
        parsed++;
      }
    }

    // Strategy 3: Skip
    if (!city) {
      skipped++;
      console.log(`  SKIP ${trip.id.slice(0, 8)} | ${trip.status} | name=${trip.name ?? "(unnamed)"}`);
      continue;
    }

    const destination = `${city}, ${country}`;

    console.log(`  ${source.padEnd(4).toUpperCase()} ${trip.id.slice(0, 8)} | ${trip.status.padEnd(10)} | ${destination}`);

    legsToCreate.push({
      id: randomUUID(),
      tripId: trip.id,
      position: 0,
      city,
      country,
      timezone: timezone ?? "UTC",
      destination,
      startDate: trip.startDate,
      endDate: trip.endDate,
    });
  }

  console.log(`\n--- Summary ---`);
  console.log(`  Inferred from slots: ${inferred}`);
  console.log(`  Parsed from name:    ${parsed}`);
  console.log(`  Skipped:             ${skipped}`);
  console.log(`  Total legs to create: ${legsToCreate.length}`);

  if (DRY_RUN) {
    console.log(`\n  DRY RUN — no changes written. Run with --apply to execute.\n`);
  } else {
    console.log(`\n  Writing ${legsToCreate.length} legs to database...`);

    // Batch in chunks of 500
    const BATCH_SIZE = 500;
    for (let i = 0; i < legsToCreate.length; i += BATCH_SIZE) {
      const batch = legsToCreate.slice(i, i + BATCH_SIZE);
      await prisma.tripLeg.createMany({ data: batch });
      console.log(`    Batch ${Math.floor(i / BATCH_SIZE) + 1}: ${batch.length} legs created`);
    }

    console.log(`\n  Done. ${legsToCreate.length} legs created.\n`);
  }

  await prisma.$disconnect();
}

main().catch((err) => {
  console.error("Migration failed:", err);
  process.exit(1);
});
