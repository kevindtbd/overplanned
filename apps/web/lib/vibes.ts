/**
 * Vibe archetype configuration — single source of truth.
 *
 * Used by: /explore page (UI), /api/explore/vibes (scoring),
 * and the seeding pipeline that computes CityVibeProfile scores.
 *
 * vibeKey values match the CityVibeProfile.vibeKey column
 * (underscore format: warm_slow, dense_late, etc.)
 *
 * Tag slugs reference the locked vibe vocabulary (42 tags).
 */

export type VibeKey =
  | "warm_slow"
  | "dense_late"
  | "remote_physical"
  | "old_layered";

export interface VibeArchetype {
  key: VibeKey;
  label: string;
  description: string;
  tags: string[];
}

export const VIBE_ARCHETYPES: Record<VibeKey, VibeArchetype> = {
  warm_slow: {
    key: "warm_slow",
    label: "Warm + Slow",
    description: "Sun-soaked mornings, long lunches, nowhere to be",
    tags: [
      "slow-burn",
      "local-institution",
      "solo-friendly",
      "intimate",
      "easy-walk",
    ],
  },
  dense_late: {
    key: "dense_late",
    label: "Dense + Late",
    description:
      "Packed streets, late nights, always something happening",
    tags: [
      "late-night",
      "high-energy",
      "lively",
      "street-food",
      "social-scene",
    ],
  },
  remote_physical: {
    key: "remote_physical",
    label: "Remote + Physical",
    description: "Trails, coastlines, and earning your views",
    tags: [
      "physically-demanding",
      "nature-immersive",
      "easy-walk",
      "low-interaction",
    ],
  },
  old_layered: {
    key: "old_layered",
    label: "Old + Layered",
    description:
      "History underfoot, temples, markets, lived-in places",
    tags: [
      "deep-history",
      "hands-on",
      "contemporary-culture",
      "immersive",
    ],
  },
} as const;

/** Ordered array for rendering the 2x2 grid */
export const VIBE_ARCHETYPE_LIST: VibeArchetype[] = [
  VIBE_ARCHETYPES.warm_slow,
  VIBE_ARCHETYPES.dense_late,
  VIBE_ARCHETYPES.remote_physical,
  VIBE_ARCHETYPES.old_layered,
];
