import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

/**
 * Enforce concurrent session limit for a user
 * Max 5 active sessions per user - delete oldest if limit exceeded
 */
export async function enforceConcurrentSessionLimit(
  userId: string,
  maxSessions: number = 5
): Promise<void> {
  const now = new Date();

  // Get all active (non-expired) sessions for user, ordered by creation time
  const sessions = await prisma.session.findMany({
    where: {
      userId,
      expires: { gt: now },
    },
    orderBy: {
      createdAt: "asc", // oldest first
    },
    select: {
      id: true,
      createdAt: true,
    },
  });

  // If user has more than maxSessions, delete the oldest ones
  if (sessions.length > maxSessions) {
    const sessionsToDelete = sessions.slice(0, sessions.length - maxSessions);
    const idsToDelete = sessionsToDelete.map((s) => s.id);

    await prisma.session.deleteMany({
      where: {
        id: { in: idsToDelete },
      },
    });
  }
}

/**
 * Update user's lastActiveAt timestamp
 * Called on every authenticated request
 */
export async function updateUserActivity(userId: string): Promise<void> {
  await prisma.user.update({
    where: { id: userId },
    data: { lastActiveAt: new Date() },
  });
}

/**
 * Get active session count for a user
 */
export async function getActiveSessionCount(userId: string): Promise<number> {
  const now = new Date();
  return prisma.session.count({
    where: {
      userId,
      expires: { gt: now },
    },
  });
}

/**
 * Revoke all sessions for a user (logout from all devices)
 */
export async function revokeAllUserSessions(userId: string): Promise<void> {
  await prisma.session.deleteMany({
    where: { userId },
  });
}

/**
 * Clean up expired sessions (should be run as cron job)
 */
export async function cleanupExpiredSessions(): Promise<number> {
  const now = new Date();
  const result = await prisma.session.deleteMany({
    where: {
      expires: { lte: now },
    },
  });
  return result.count;
}
