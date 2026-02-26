import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/climate", () => ({
  getClimateContext: vi.fn(),
}));

const { getClimateContext: mockGetClimateString } = await import(
  "@/lib/climate"
);
const { getWeatherContext } = await import(
  "@/lib/generation/weather-context"
);

const mockedClimate = vi.mocked(mockGetClimateString);

describe("getWeatherContext", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns correct season for spring months", () => {
    mockedClimate.mockReturnValue(null);

    const march = getWeatherContext("Tokyo", new Date("2026-03-15"));
    expect(march.season).toBe("spring");

    const may = getWeatherContext("Tokyo", new Date("2026-05-01"));
    expect(may.season).toBe("spring");
  });

  it("returns correct season for summer months", () => {
    mockedClimate.mockReturnValue(null);

    const june = getWeatherContext("Tokyo", new Date("2026-06-20"));
    expect(june.season).toBe("summer");

    const august = getWeatherContext("Tokyo", new Date("2026-08-31"));
    expect(august.season).toBe("summer");
  });

  it("returns correct season for autumn months", () => {
    mockedClimate.mockReturnValue(null);

    const sept = getWeatherContext("Kyoto", new Date("2026-09-15"));
    expect(sept.season).toBe("autumn");

    const nov = getWeatherContext("Kyoto", new Date("2026-11-30"));
    expect(nov.season).toBe("autumn");
  });

  it("returns correct season for winter months", () => {
    mockedClimate.mockReturnValue(null);

    const dec = getWeatherContext("Sapporo", new Date("2026-12-25"));
    expect(dec.season).toBe("winter");

    const jan = getWeatherContext("Sapporo", new Date("2026-01-15"));
    expect(jan.season).toBe("winter");

    const feb = getWeatherContext("Sapporo", new Date("2026-02-10"));
    expect(feb.season).toBe("winter");
  });

  it("returns correct month number (1-indexed)", () => {
    mockedClimate.mockReturnValue(null);

    const result = getWeatherContext("Tokyo", new Date("2026-07-04"));
    expect(result.month).toBe(7);
  });

  it("includes city name in result", () => {
    mockedClimate.mockReturnValue(null);

    const result = getWeatherContext("Osaka", new Date("2026-04-10"));
    expect(result.city).toBe("Osaka");
  });

  it("includes climate description when available", () => {
    const climateDesc =
      "Typical weather for Tokyo in March: 5-15C, 8 rainy days typical. Cool and dry.";
    mockedClimate.mockReturnValue(climateDesc);

    const result = getWeatherContext("Tokyo", new Date("2026-03-15"));
    expect(result.climateDescription).toBe(climateDesc);
  });

  it("returns null climateDescription for unseeded cities", () => {
    mockedClimate.mockReturnValue(null);

    const result = getWeatherContext("UnknownCity", new Date("2026-06-01"));
    expect(result.climateDescription).toBeNull();
  });

  it("passes correct arguments to climate lookup", () => {
    mockedClimate.mockReturnValue(null);

    getWeatherContext("Tokyo", new Date("2026-10-15"));

    expect(mockedClimate).toHaveBeenCalledWith("Tokyo", 10);
  });

  it("returns full structured object", () => {
    mockedClimate.mockReturnValue("Some climate info");

    const result = getWeatherContext("Kyoto", new Date("2026-04-20"));
    expect(result).toEqual({
      city: "Kyoto",
      month: 4,
      season: "spring",
      climateDescription: "Some climate info",
    });
  });
});
