import { describe, it, expect } from "vitest";
import { deriveBookingHint } from "../../lib/booking-hint";

describe("deriveBookingHint", () => {
  it("returns 'call ahead' when only phone is provided", () => {
    expect(deriveBookingHint({ phoneNumber: "+81-3-1234-5678" })).toBe("call ahead");
  });

  it("returns 'reservable online' when URL path contains /reserve", () => {
    expect(
      deriveBookingHint({ websiteUrl: "https://example.com/reserve" })
    ).toBe("reservable online");
  });

  it("returns 'reservable online' when URL path contains /book", () => {
    expect(
      deriveBookingHint({ websiteUrl: "https://example.com/book" })
    ).toBe("reservable online");
  });

  it("returns 'reservable online' when URL path ends with /reservation", () => {
    expect(
      deriveBookingHint({ websiteUrl: "https://example.com/reservation" })
    ).toBe("reservable online");
  });

  it("returns 'check website' when URL has /menu (no booking keyword)", () => {
    expect(
      deriveBookingHint({ websiteUrl: "https://example.com/menu" })
    ).toBe("check website");
  });

  it("returns 'check website' when both phone and non-booking URL exist", () => {
    expect(
      deriveBookingHint({
        phoneNumber: "+1-555-1234",
        websiteUrl: "https://example.com/menu",
      })
    ).toBe("check website");
  });

  it("returns 'check website' when booking keyword is in domain not path", () => {
    expect(
      deriveBookingHint({ websiteUrl: "https://reserved-dining.com/menu" })
    ).toBe("check website");
  });

  it("returns 'limited hours' when any time window is < 4 hours (no URL, no phone)", () => {
    expect(
      deriveBookingHint({
        hours: {
          monday: [{ open: "09:00", close: "12:00" }],
          tuesday: [{ open: "08:00", close: "17:00" }],
        },
      })
    ).toBe("limited hours");
  });

  it("returns 'walk-in' when hours is null", () => {
    expect(deriveBookingHint({ hours: null })).toBe("walk-in");
  });

  it("returns 'walk-in' when hours is an empty object", () => {
    expect(deriveBookingHint({ hours: {} })).toBe("walk-in");
  });

  it("returns 'walk-in' when hours is a malformed string", () => {
    expect(deriveBookingHint({ hours: "9am-5pm" })).toBe("walk-in");
  });

  it("returns 'walk-in' when node is null", () => {
    expect(deriveBookingHint(null)).toBe("walk-in");
  });

  it("returns 'walk-in' when no phone, no URL, no hours", () => {
    expect(deriveBookingHint({})).toBe("walk-in");
  });

  it("treats invalid URL string as no URL (falls through to walk-in)", () => {
    expect(deriveBookingHint({ websiteUrl: "not a valid url" })).toBe("walk-in");
  });

  it("treats invalid URL string with phone as 'call ahead'", () => {
    expect(
      deriveBookingHint({
        websiteUrl: "not a valid url",
        phoneNumber: "+1-555-9999",
      })
    ).toBe("call ahead");
  });

  it("returns 'walk-in' when all hours windows are >= 4 hours", () => {
    expect(
      deriveBookingHint({
        hours: {
          monday: [{ open: "08:00", close: "12:00" }],
          tuesday: [{ open: "09:00", close: "17:00" }],
        },
      })
    ).toBe("walk-in");
  });

  it("returns 'reservable online' for deep nested /book path", () => {
    expect(
      deriveBookingHint({
        websiteUrl: "https://example.com/dining/book/table",
      })
    ).toBe("reservable online");
  });
});
