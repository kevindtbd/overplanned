/**
 * Unit tests for apps/web/lib/climate.ts — getClimateContext()
 */

import { describe, it, expect } from "vitest";
import { getClimateContext } from "../../lib/climate";

describe("getClimateContext", () => {
  it("returns formatted string for known city 'tokyo' month 7", () => {
    const result = getClimateContext("tokyo", 7);
    expect(result).not.toBeNull();
    expect(result).toContain("23-31C");
    expect(result).toContain("Tokyo");
    expect(result).toContain("July");
    expect(result).toContain("12 rainy days typical");
  });

  it("normalizes capitalized 'Tokyo' to same result as lowercase", () => {
    const lower = getClimateContext("tokyo", 7);
    const upper = getClimateContext("Tokyo", 7);
    expect(upper).toEqual(lower);
  });

  it("returns string including 'snow' for new_york month 1", () => {
    const result = getClimateContext("new_york", 1);
    expect(result).not.toBeNull();
    expect(result).toContain("snow");
  });

  it("normalizes 'New York' (with space) to same as 'new_york'", () => {
    const withUnderscore = getClimateContext("new_york", 1);
    const withSpace = getClimateContext("New York", 1);
    expect(withSpace).toEqual(withUnderscore);
  });

  it("returns null for unknown city 'paris'", () => {
    const result = getClimateContext("paris", 6);
    expect(result).toBeNull();
  });

  it("returns null for month 0 (out of range)", () => {
    const result = getClimateContext("tokyo", 0);
    expect(result).toBeNull();
  });

  it("returns null for month 13 (out of range)", () => {
    const result = getClimateContext("tokyo", 13);
    expect(result).toBeNull();
  });

  it("handles month 1 boundary correctly", () => {
    const result = getClimateContext("tokyo", 1);
    expect(result).not.toBeNull();
    expect(result).toContain("January");
    expect(result).toContain("2-10C");
  });

  it("handles month 12 boundary correctly", () => {
    const result = getClimateContext("tokyo", 12);
    expect(result).not.toBeNull();
    expect(result).toContain("December");
    expect(result).toContain("4-12C");
  });
});
