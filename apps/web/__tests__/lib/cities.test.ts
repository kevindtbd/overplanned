import { describe, it, expect } from "vitest";
import { LAUNCH_CITIES, findCity, getCityByName } from "@/lib/cities";

describe("LAUNCH_CITIES", () => {
  it("has exactly 30 cities", () => {
    expect(LAUNCH_CITIES).toHaveLength(30);
  });

  it("every city has a unique slug", () => {
    const slugs = LAUNCH_CITIES.map((c) => c.slug);
    expect(new Set(slugs).size).toBe(30);
  });

  it("Portland OR and Portland ME have distinct slugs", () => {
    const pdx = LAUNCH_CITIES.find((c) => c.slug === "portland");
    expect(pdx).toMatchObject({ city: "Portland", state: "OR" });

    const pme = LAUNCH_CITIES.find((c) => c.slug === "portland-me");
    expect(pme).toMatchObject({ city: "Portland", state: "ME" });
  });

  it("city.city is NOT unique — Portland appears twice", () => {
    const names = LAUNCH_CITIES.map((c) => c.city);
    const hasDuplicateNames = names.length !== new Set(names).size;
    expect(hasDuplicateNames).toBe(true);
  });

  it("US cities have a non-empty state", () => {
    for (const city of LAUNCH_CITIES) {
      if (city.country === "United States") {
        expect(city.state).not.toBe("");
      }
    }
  });

  it("Mexico City has empty state", () => {
    const mex = findCity("mexico-city");
    expect(mex?.state).toBe("");
    expect(mex?.country).toBe("Mexico");
  });

  it("every city has valid lat/lng", () => {
    for (const city of LAUNCH_CITIES) {
      expect(city.lat).toBeGreaterThan(-90);
      expect(city.lat).toBeLessThan(90);
      expect(city.lng).toBeGreaterThan(-180);
      expect(city.lng).toBeLessThan(180);
    }
  });
});

describe("findCity", () => {
  it("returns a city for a valid slug", () => {
    expect(findCity("bend")).toMatchObject({ city: "Bend", state: "OR" });
  });

  it("returns undefined for an unknown slug", () => {
    expect(findCity("tokyo")).toBeUndefined();
    expect(findCity("nonexistent")).toBeUndefined();
  });
});

describe("getCityByName", () => {
  it("returns first match for a unique name", () => {
    expect(getCityByName("Austin")?.slug).toBe("austin");
  });

  it("returns Portland OR (first in list) for ambiguous 'Portland'", () => {
    expect(getCityByName("Portland")?.slug).toBe("portland");
  });

  it("is case-insensitive", () => {
    expect(getCityByName("bend")?.slug).toBe("bend");
    expect(getCityByName("BEND")?.slug).toBe("bend");
  });

  it("returns undefined for unknown city name", () => {
    expect(getCityByName("Tokyo")).toBeUndefined();
  });
});
