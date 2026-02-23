/**
 * Tests for lib/trip-legs.ts — pure utility functions for multi-city trip computations.
 */

import { describe, it, expect } from "vitest";
import { legDayCount, computeAbsoluteDay, buildRouteString, autoTripName } from "@/lib/trip-legs";

describe("legDayCount", () => {
  it("returns day count from date range", () => {
    expect(legDayCount({ startDate: "2026-04-01", endDate: "2026-04-04" })).toBe(3);
  });

  it("returns 1 for same-day range", () => {
    expect(legDayCount({ startDate: "2026-04-01", endDate: "2026-04-01" })).toBe(1);
  });

  it("returns at least 1 even for zero diff", () => {
    const same = "2026-04-01T00:00:00.000Z";
    expect(legDayCount({ startDate: same, endDate: same })).toBe(1);
  });

  it("works with Date objects", () => {
    expect(legDayCount({
      startDate: new Date("2026-04-01"),
      endDate: new Date("2026-04-08"),
    })).toBe(7);
  });
});

describe("computeAbsoluteDay", () => {
  const legs = [
    { id: "leg-1", startDate: "2026-04-01", endDate: "2026-04-04" }, // 3 days
    { id: "leg-2", startDate: "2026-04-04", endDate: "2026-04-06" }, // 2 days
    { id: "leg-3", startDate: "2026-04-06", endDate: "2026-04-10" }, // 4 days
  ];

  it("returns day 1 for first leg, day 1", () => {
    expect(computeAbsoluteDay(legs, "leg-1", 1)).toBe(1);
  });

  it("returns day 3 for first leg, day 3", () => {
    expect(computeAbsoluteDay(legs, "leg-1", 3)).toBe(3);
  });

  it("returns day 4 for second leg, day 1", () => {
    expect(computeAbsoluteDay(legs, "leg-2", 1)).toBe(4);
  });

  it("returns day 6 for third leg, day 1", () => {
    expect(computeAbsoluteDay(legs, "leg-3", 1)).toBe(6);
  });

  it("returns day 9 for third leg, day 4", () => {
    expect(computeAbsoluteDay(legs, "leg-3", 4)).toBe(9);
  });

  it("returns legRelativeDay when leg not found", () => {
    expect(computeAbsoluteDay(legs, "nonexistent", 2)).toBe(2);
  });

  it("handles single leg", () => {
    const single = [{ id: "leg-1", startDate: "2026-04-01", endDate: "2026-04-05" }];
    expect(computeAbsoluteDay(single, "leg-1", 3)).toBe(3);
  });
});

describe("buildRouteString", () => {
  it("returns empty string for no legs", () => {
    expect(buildRouteString([])).toBe("");
  });

  it("returns destination for single leg", () => {
    expect(buildRouteString([
      { city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" },
    ])).toBe("Tokyo, Japan");
  });

  it("returns arrow-joined cities for multiple legs", () => {
    expect(buildRouteString([
      { city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" },
      { city: "Kyoto", country: "Japan", destination: "Kyoto, Japan" },
      { city: "Osaka", country: "Japan", destination: "Osaka, Japan" },
    ])).toBe("Tokyo → Kyoto → Osaka");
  });
});

describe("autoTripName", () => {
  // Use mid-month noon UTC to avoid timezone boundary issues
  const aprDate = "2026-04-15T12:00:00Z";
  const decDate = "2026-12-15T12:00:00Z";

  it("returns generic name for no legs", () => {
    const name = autoTripName([], aprDate);
    expect(name).toContain("Trip");
    expect(name).toContain("Apr");
    expect(name).toContain("2026");
  });

  it("returns 'City MonthYear' for single leg", () => {
    const name = autoTripName(
      [{ city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" }],
      aprDate
    );
    expect(name).toBe("Tokyo Apr 2026");
  });

  it("returns 'CityA to CityB MonthYear' for same-country multi-leg", () => {
    const name = autoTripName(
      [
        { city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" },
        { city: "Kyoto", country: "Japan", destination: "Kyoto, Japan" },
        { city: "Osaka", country: "Japan", destination: "Osaka, Japan" },
      ],
      aprDate
    );
    expect(name).toBe("Tokyo to Osaka Apr 2026");
  });

  it("returns 'CountryA & CountryB MonthYear' for two countries", () => {
    const name = autoTripName(
      [
        { city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" },
        { city: "Bangkok", country: "Thailand", destination: "Bangkok, Thailand" },
      ],
      aprDate
    );
    expect(name).toBe("Japan & Thailand Apr 2026");
  });

  it("returns 'CountryA, CountryB & more' for 3+ countries", () => {
    const name = autoTripName(
      [
        { city: "Tokyo", country: "Japan", destination: "Tokyo, Japan" },
        { city: "Bangkok", country: "Thailand", destination: "Bangkok, Thailand" },
        { city: "Seoul", country: "South Korea", destination: "Seoul, South Korea" },
      ],
      aprDate
    );
    expect(name).toBe("Japan, Thailand & more Apr 2026");
  });

  it("works with Date object for startDate", () => {
    const name = autoTripName(
      [{ city: "NYC", country: "USA", destination: "New York, USA" }],
      new Date(decDate)
    );
    expect(name).toContain("NYC");
    expect(name).toContain("Dec");
    expect(name).toContain("2026");
  });
});
