import { v4 as uuidv4 } from "uuid";

export interface MockLeg {
  id: string;
  tripId: string;
  position: number;
  city: string;
  country: string;
  timezone: string | null;
  destination: string;
  startDate: Date;
  endDate: Date;
  arrivalTime: string | null;
  departureTime: string | null;
  transitMode: string | null;
  transitDurationMin: number | null;
  transitCostHint: string | null;
  transitConfirmed: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export function makeLeg(overrides: Partial<MockLeg> = {}): MockLeg {
  return {
    id: uuidv4(),
    tripId: uuidv4(),
    position: 0,
    city: "Tokyo",
    country: "Japan",
    timezone: "Asia/Tokyo",
    destination: "Tokyo, Japan",
    startDate: new Date("2026-04-01T00:00:00.000Z"),
    endDate: new Date("2026-04-05T00:00:00.000Z"),
    arrivalTime: null,
    departureTime: null,
    transitMode: null,
    transitDurationMin: null,
    transitCostHint: null,
    transitConfirmed: false,
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides,
  };
}

export function makeLegs(
  tripId: string,
  count: number,
  base: Partial<MockLeg> = {}
): MockLeg[] {
  const cities = [
    { city: "Tokyo", country: "Japan", timezone: "Asia/Tokyo", destination: "Tokyo, Japan" },
    { city: "Kyoto", country: "Japan", timezone: "Asia/Tokyo", destination: "Kyoto, Japan" },
    { city: "Osaka", country: "Japan", timezone: "Asia/Tokyo", destination: "Osaka, Japan" },
    { city: "Bangkok", country: "Thailand", timezone: "Asia/Bangkok", destination: "Bangkok, Thailand" },
    { city: "Seoul", country: "South Korea", timezone: "Asia/Seoul", destination: "Seoul, South Korea" },
    { city: "Taipei", country: "Taiwan", timezone: "Asia/Taipei", destination: "Taipei, Taiwan" },
    { city: "Lisbon", country: "Portugal", timezone: "Europe/Lisbon", destination: "Lisbon, Portugal" },
    { city: "Barcelona", country: "Spain", timezone: "Europe/Madrid", destination: "Barcelona, Spain" },
  ];

  return Array.from({ length: count }, (_, i) => {
    const c = cities[i % cities.length];
    const start = new Date("2026-04-01T00:00:00.000Z");
    start.setDate(start.getDate() + i * 4);
    const end = new Date(start);
    end.setDate(end.getDate() + 3);

    return makeLeg({
      tripId,
      position: i,
      ...c,
      startDate: start,
      endDate: end,
      ...base,
    });
  });
}
