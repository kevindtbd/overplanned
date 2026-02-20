// @overplanned/db
// Re-exports Prisma client for workspace consumers.
// Frontend (apps/web) should NOT import this — use @overplanned/shared-types instead.

export { PrismaClient } from '@prisma/client';
export type { Prisma } from '@prisma/client';

// Singleton client for server-side usage
import { PrismaClient } from '@prisma/client';

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query', 'error', 'warn'] : ['error'],
  });

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma;
