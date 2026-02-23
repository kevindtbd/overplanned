import { Session } from "next-auth";
import { User } from "@prisma/client";

export interface MockSessionOptions {
  userId?: string;
  email?: string;
  subscriptionTier?: "free" | "beta" | "pro" | "lifetime";
  systemRole?: "user" | "admin";
}

/**
 * Create a mock NextAuth session for testing
 *
 * Usage:
 * ```typescript
 * const session = createMockSession({
 *   userId: "user-1",
 *   subscriptionTier: "beta"
 * });
 * ```
 */
export function createMockSession(
  options: MockSessionOptions = {}
): Session {
  return {
    user: {
      id: options.userId || "test-user-id",
      email: options.email || "test@example.com",
      name: "Test User",
      image: null,
      subscriptionTier: options.subscriptionTier || "beta",
      systemRole: options.systemRole || "user",
    },
    expires: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  };
}

/**
 * Create a mock User for database operations
 *
 * Usage:
 * ```typescript
 * const user = createMockUser({
 *   subscriptionTier: "lifetime"
 * });
 * prisma.user.findUnique.mockResolvedValue(user);
 * ```
 */
export function createMockUser(
  options: Partial<User> = {}
): User {
  return {
    id: options.id || "test-user-id",
    email: options.email || "test@example.com",
    name: options.name || "Test User",
    emailVerified: options.emailVerified || new Date(),
    image: options.image || null,
    googleId: options.googleId || "google-id-123",
    subscriptionTier: options.subscriptionTier || "beta",
    systemRole: options.systemRole || "user",
    onboardingCompleted: options.onboardingCompleted ?? true,
    createdAt: options.createdAt || new Date(),
    updatedAt: options.updatedAt || new Date(),
    lastActiveAt: options.lastActiveAt || new Date(),
  };
}

/**
 * Create an unauthenticated session (null)
 */
export function createUnauthenticatedSession(): null {
  return null;
}
