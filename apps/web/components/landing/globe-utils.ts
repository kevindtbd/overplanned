/* ------------------------------------------------------------------ */
/*  Globe utility functions — pure, testable, no React dependency      */
/* ------------------------------------------------------------------ */

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface ProjectedPoint {
  x: number;
  y: number;
  z: number;
  vis: boolean;
}

/* Fixed X-axis tilt: -20 degrees */
const TILT_X = -20 * (Math.PI / 180);
const cTilt = Math.cos(TILT_X);
const sTilt = Math.sin(TILT_X);

/**
 * Convert lat/lng (degrees) to a unit-sphere Vec3.
 * Standard geographic: lat [-90,90], lng [-180,180].
 */
export function latLngToVec3(lat: number, lng: number): Vec3 {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lng + 180) * Math.PI) / 180;
  return {
    x: -Math.sin(phi) * Math.cos(theta),
    y: Math.cos(phi),
    z: Math.sin(phi) * Math.sin(theta),
  };
}

/**
 * Project a Vec3 onto 2D screen coordinates with compound rotation:
 *   1. Y-axis spin (animated `rotation` param)
 *   2. X-axis tilt (fixed -20 degrees)
 *
 * Returns screen {x, y}, depth z, and visibility flag.
 * `rotation` is explicit (not a ref) so this stays pure.
 */
export function projectPoint(
  v: Vec3,
  cx: number,
  cy: number,
  R: number,
  rotation: number,
): ProjectedPoint {
  // Y-axis spin
  const cY = Math.cos(rotation);
  const sY = Math.sin(rotation);
  const x1 = v.x * cY + v.z * sY;
  const z1 = -v.x * sY + v.z * cY;

  // X-axis tilt (fixed)
  const y2 = v.y * cTilt - z1 * sTilt;
  const z2 = v.y * sTilt + z1 * cTilt;

  return {
    x: cx + x1 * R,
    y: cy - y2 * R,
    z: z2,
    vis: z2 > -0.12,
  };
}

/* ------------------------------------------------------------------ */
/*  AABB anti-collision for tooltip cards                              */
/* ------------------------------------------------------------------ */

export interface CardRect {
  x: number;
  y: number;
  width: number;
  height: number;
  cityIdx: number;
}

/**
 * Resolve overlapping card positions via AABB force repulsion.
 * Runs 3 iterations of pairwise overlap detection + push-apart.
 * Fans vertical stagger upward (globe is below-center).
 *
 * Pure function: input cards are not mutated; returns new array.
 */
export function resolveCardPositions(
  cards: CardRect[],
  bounds: { width: number; height: number },
): CardRect[] {
  if (cards.length <= 1) return cards.map((c) => ({ ...c }));

  const result = cards.map((c) => ({ ...c }));
  const ITERATIONS = 3;
  const PADDING = 6; // px gap between cards

  for (let iter = 0; iter < ITERATIONS; iter++) {
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        const a = result[i];
        const b = result[j];

        // AABB overlap check
        const overlapX =
          a.x < b.x + b.width + PADDING && a.x + a.width + PADDING > b.x;
        const overlapY =
          a.y < b.y + b.height + PADDING && a.y + a.height + PADDING > b.y;

        if (overlapX && overlapY) {
          // Push apart vertically (fan upward — globe is below center)
          const pushY = (a.height + PADDING) / 2;
          // Card with smaller y (higher on screen) goes up, other goes down
          if (a.y <= b.y) {
            a.y -= pushY * 0.6;
            b.y += pushY * 0.4;
          } else {
            b.y -= pushY * 0.6;
            a.y += pushY * 0.4;
          }
        }
      }
    }
  }

  // Clamp to bounds
  for (const card of result) {
    card.x = Math.max(0, Math.min(card.x, bounds.width - card.width));
    card.y = Math.max(0, Math.min(card.y, bounds.height - card.height));
  }

  return result;
}
