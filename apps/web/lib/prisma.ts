import { Prisma, PrismaClient } from "@prisma/client";

// Re-export so route files don't need direct @prisma/client imports
export type TransactionClient = Prisma.TransactionClient;
export const PrismaJsonNull = Prisma.JsonNull;

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
