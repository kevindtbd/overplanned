import type { SubscriptionTier } from "@prisma/client";

/**
 * Get effective access tier for a user based on their subscriptionTier
 * Beta, lifetime, and pro users all have access during beta phase
 */
export function getEffectiveTier(
  tier: SubscriptionTier
): "beta" | "pro" | "lifetime" | "free" {
  return tier;
}

/**
 * Check if user has access to app features
 * During beta: beta, lifetime, and pro users have access
 */
export function hasAccess(tier: SubscriptionTier): boolean {
  return ["beta", "lifetime", "pro"].includes(tier);
}

/**
 * Feature gate configuration
 * Maps feature names to required subscription tiers
 * During beta mode, all features are accessible to beta/lifetime/pro users
 */
export const FEATURE_GATES = {
  // Core features - available to all beta users
  trip_planning: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  itinerary_creation: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  activity_discovery: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  behavioral_tracking: ["beta", "lifetime", "pro"] as SubscriptionTier[],

  // Advanced features - available during beta, may be gated later
  group_trips: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  real_time_pivots: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  post_trip_analysis: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  vibe_tagging: ["beta", "lifetime", "pro"] as SubscriptionTier[],

  // Premium features - currently available during beta
  unlimited_trips: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  priority_support: ["beta", "lifetime", "pro"] as SubscriptionTier[],
  export_itinerary: ["beta", "lifetime", "pro"] as SubscriptionTier[],

  // Future features (placeholder - not implemented yet)
  offline_mode: ["lifetime", "pro"] as SubscriptionTier[],
  advanced_analytics: ["lifetime", "pro"] as SubscriptionTier[],
} as const;

export type FeatureName = keyof typeof FEATURE_GATES;

/**
 * Check if user's tier has access to a specific feature
 */
export function hasFeatureAccess(
  tier: SubscriptionTier,
  feature: FeatureName
): boolean {
  const requiredTiers = FEATURE_GATES[feature];
  return requiredTiers.includes(tier);
}

/**
 * Get all accessible features for a user's tier
 */
export function getAccessibleFeatures(
  tier: SubscriptionTier
): FeatureName[] {
  return Object.entries(FEATURE_GATES)
    .filter(([_, requiredTiers]) => requiredTiers.includes(tier))
    .map(([feature]) => feature as FeatureName);
}

/**
 * Check if user is admin
 */
export function isAdmin(systemRole: string): boolean {
  return systemRole === "admin";
}
