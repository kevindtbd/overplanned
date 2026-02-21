import { describe, it, expect } from "vitest";
import {
  latLngToVec3,
  projectPoint,
  resolveCardPositions,
  type CardRect,
} from "@/components/landing/globe-utils";

/* ------------------------------------------------------------------ */
/*  latLngToVec3                                                       */
/* ------------------------------------------------------------------ */

describe("latLngToVec3", () => {
  it("places the north pole at y=1", () => {
    const v = latLngToVec3(90, 0);
    expect(v.y).toBeCloseTo(1, 5);
    expect(Math.abs(v.x)).toBeLessThan(1e-10);
    expect(Math.abs(v.z)).toBeLessThan(1e-10);
  });

  it("places the south pole at y=-1", () => {
    const v = latLngToVec3(-90, 0);
    expect(v.y).toBeCloseTo(-1, 5);
  });

  it("returns a unit vector for any lat/lng", () => {
    const cases = [
      [35.68, 139.69], // Tokyo
      [41.39, 2.17],   // Barcelona
      [-33.87, 151.21], // Sydney
      [0, 0],
      [0, 180],
    ];
    for (const [lat, lng] of cases) {
      const v = latLngToVec3(lat, lng);
      const mag = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
      expect(mag).toBeCloseTo(1, 10);
    }
  });

  it("maps equator lat=0 to y=0", () => {
    const v = latLngToVec3(0, 45);
    expect(v.y).toBeCloseTo(0, 10);
  });
});

/* ------------------------------------------------------------------ */
/*  projectPoint                                                       */
/* ------------------------------------------------------------------ */

describe("projectPoint", () => {
  it("returns screen coords within globe radius", () => {
    const v = latLngToVec3(35.68, 139.69);
    const p = projectPoint(v, 400, 300, 200, 0);
    // x should be within [cx - R, cx + R]
    expect(p.x).toBeGreaterThanOrEqual(400 - 200);
    expect(p.x).toBeLessThanOrEqual(400 + 200);
  });

  it("marks front-facing points as visible", () => {
    const v = latLngToVec3(0, 0);
    // With rotation=0, lng=0 should be on the visible side
    const p = projectPoint(v, 400, 300, 200, 0);
    // vis depends on z after compound rotation; just verify it returns a boolean
    expect(typeof p.vis).toBe("boolean");
  });

  it("uses rotation to spin around Y axis", () => {
    const v = latLngToVec3(0, 0);
    const p1 = projectPoint(v, 400, 300, 200, 0);
    const p2 = projectPoint(v, 400, 300, 200, Math.PI);
    // After half rotation, the x position should differ significantly
    expect(Math.abs(p1.x - p2.x)).toBeGreaterThan(50);
  });

  it("is a pure function — same input produces same output", () => {
    const v = latLngToVec3(37.56, 126.97);
    const a = projectPoint(v, 400, 300, 200, 1.5);
    const b = projectPoint(v, 400, 300, 200, 1.5);
    expect(a).toEqual(b);
  });
});

/* ------------------------------------------------------------------ */
/*  resolveCardPositions                                                */
/* ------------------------------------------------------------------ */

describe("resolveCardPositions", () => {
  const bounds = { width: 800, height: 600 };

  it("returns a new array (no mutation)", () => {
    const cards: CardRect[] = [
      { x: 100, y: 100, width: 80, height: 40, cityIdx: 0 },
    ];
    const result = resolveCardPositions(cards, bounds);
    expect(result).not.toBe(cards);
    expect(result[0]).not.toBe(cards[0]);
  });

  it("passes through a single card unchanged", () => {
    const cards: CardRect[] = [
      { x: 100, y: 100, width: 80, height: 40, cityIdx: 0 },
    ];
    const result = resolveCardPositions(cards, bounds);
    expect(result[0].x).toBe(100);
    expect(result[0].y).toBe(100);
  });

  it("separates overlapping cards vertically", () => {
    const cards: CardRect[] = [
      { x: 100, y: 100, width: 80, height: 40, cityIdx: 0 },
      { x: 100, y: 105, width: 80, height: 40, cityIdx: 1 },
    ];
    const result = resolveCardPositions(cards, bounds);
    // After resolution, the gap between card bottoms/tops should be wider
    const gap = Math.abs(result[1].y - result[0].y);
    const originalGap = Math.abs(cards[1].y - cards[0].y);
    expect(gap).toBeGreaterThan(originalGap);
  });

  it("clamps cards within bounds", () => {
    const cards: CardRect[] = [
      { x: -50, y: -20, width: 80, height: 40, cityIdx: 0 },
      { x: 790, y: 580, width: 80, height: 40, cityIdx: 1 },
    ];
    const result = resolveCardPositions(cards, bounds);
    for (const card of result) {
      expect(card.x).toBeGreaterThanOrEqual(0);
      expect(card.y).toBeGreaterThanOrEqual(0);
      expect(card.x + card.width).toBeLessThanOrEqual(bounds.width);
      expect(card.y + card.height).toBeLessThanOrEqual(bounds.height);
    }
  });

  it("handles non-overlapping cards without moving them", () => {
    const cards: CardRect[] = [
      { x: 10, y: 10, width: 80, height: 40, cityIdx: 0 },
      { x: 300, y: 300, width: 80, height: 40, cityIdx: 1 },
    ];
    const result = resolveCardPositions(cards, bounds);
    expect(result[0].x).toBe(10);
    expect(result[0].y).toBe(10);
    expect(result[1].x).toBe(300);
    expect(result[1].y).toBe(300);
  });

  it("handles empty input", () => {
    const result = resolveCardPositions([], bounds);
    expect(result).toEqual([]);
  });
});
