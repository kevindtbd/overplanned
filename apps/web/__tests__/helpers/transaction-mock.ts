import { vi } from "vitest";
import { PrismaClient } from "@prisma/client";

/**
 * Mock Prisma transaction for tests
 *
 * Usage:
 * ```typescript
 * const mockTx = createTransactionMock();
 * await prisma.$transaction(async (tx) => {
 *   // tx will be mockTx
 * });
 * ```
 */
export function createTransactionMock(): PrismaClient {
  return new Proxy({} as PrismaClient, {
    get(target, prop) {
      // Return jest.fn() for any property access
      // This allows tx.user.create(), tx.trip.findUnique(), etc.
      if (typeof prop === "string") {
        return new Proxy(
          {},
          {
            get() {
              return vi.fn().mockResolvedValue(null);
            },
          }
        );
      }
      return undefined;
    },
  });
}

/**
 * Mock Prisma $transaction method
 *
 * Usage:
 * ```typescript
 * prisma.$transaction = mockTransaction();
 * ```
 */
export function mockTransaction() {
  return vi.fn(async (fn: (tx: PrismaClient) => Promise<unknown>) => {
    const mockTx = createTransactionMock();
    return fn(mockTx);
  });
}
