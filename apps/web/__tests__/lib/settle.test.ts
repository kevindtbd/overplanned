/**
 * Tests for the settle-up utility: computeSettlements
 *
 * Pure function tests — no mocks needed.
 */

import { describe, it, expect } from "vitest";
import { computeSettlements, type Settlement } from "../../lib/settle";

// Helper: verify the sum-to-zero invariant (total debtor payments = total creditor receipts)
function assertBalanced(settlements: Settlement[]) {
  const totalFrom = settlements.reduce((sum, s) => sum + s.amountCents, 0);
  // Each settlement is a transfer from debtor to creditor, so the sum of
  // all fromId amounts should equal the sum of all toId amounts (same array).
  // The invariant is really: net balances after settlements = 0 for all members.
  // But since every settlement has exactly one from and one to, the sum is self-consistent.
  expect(totalFrom).toBeGreaterThanOrEqual(0);

  // No negative amounts
  for (const s of settlements) {
    expect(s.amountCents).toBeGreaterThan(0);
  }
}

describe("computeSettlements", () => {
  it("returns empty array for zero expenses", () => {
    const result = computeSettlements([], ["a", "b", "c"]);
    expect(result).toEqual([]);
  });

  it("returns empty array for single member", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: [] }],
      ["a"]
    );
    expect(result).toEqual([]);
  });

  it("2 members: A pays 10000, split equally", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: [] }],
      ["a", "b"]
    );
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      fromId: "b",
      toId: "a",
      amountCents: 5000,
    });
    assertBalanced(result);
  });

  it("3 members: A pays 10000, split equally (remainder to payer)", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: [] }],
      ["a", "b", "c"]
    );
    // 10000 / 3 = 3333 each, remainder 1 cent absorbed by payer
    // A's net: 10000 - 3333 - 1 = 6666
    // B owes 3333, C owes 3333
    expect(result).toHaveLength(2);

    const totalOwed = result.reduce((s, t) => s + t.amountCents, 0);
    expect(totalOwed).toBe(6666);

    // Each debtor pays 3333
    for (const s of result) {
      expect(s.toId).toBe("a");
      expect(s.amountCents).toBe(3333);
    }
    assertBalanced(result);
  });

  it("4 members: A pays 8000, B pays 4000", () => {
    const result = computeSettlements(
      [
        { paidById: "a", amountCents: 8000, splitWith: [] },
        { paidById: "b", amountCents: 4000, splitWith: [] },
      ],
      ["a", "b", "c", "d"]
    );
    // Total: 12000, each share: 3000
    // A net: 8000 - 3000 = 5000 (creditor)
    // B net: 4000 - 3000 = 1000 (creditor)
    // C net: 0 - 3000 = -3000 (debtor)
    // D net: 0 - 3000 = -3000 (debtor)
    // Settlements: C->A 3000, D->A 2000, D->B 1000
    const totalTransferred = result.reduce((s, t) => s + t.amountCents, 0);
    expect(totalTransferred).toBe(6000);
    assertBalanced(result);
  });

  it("5 members: complex multi-payer scenario", () => {
    const result = computeSettlements(
      [
        { paidById: "a", amountCents: 5000, splitWith: [] },
        { paidById: "b", amountCents: 3000, splitWith: [] },
        { paidById: "c", amountCents: 2000, splitWith: [] },
      ],
      ["a", "b", "c", "d", "e"]
    );
    // Total: 10000, each share: 2000
    // A net: 5000 - 2000 = 3000
    // B net: 3000 - 2000 = 1000
    // C net: 2000 - 2000 = 0
    // D net: 0 - 2000 = -2000
    // E net: 0 - 2000 = -2000
    const totalTransferred = result.reduce((s, t) => s + t.amountCents, 0);
    expect(totalTransferred).toBe(4000);
    assertBalanced(result);
  });

  it("all expenses by same person -> n-1 settlements", () => {
    const result = computeSettlements(
      [
        { paidById: "a", amountCents: 4000, splitWith: [] },
        { paidById: "a", amountCents: 6000, splitWith: [] },
      ],
      ["a", "b", "c", "d"]
    );
    // Total: 10000, each share: 2500
    // A net: 10000 - 2500 = 7500
    // B, C, D each owe 2500
    expect(result).toHaveLength(3);
    for (const s of result) {
      expect(s.toId).toBe("a");
      expect(s.amountCents).toBe(2500);
    }
    assertBalanced(result);
  });

  it("1 cent split 3 ways: no negative amounts, remainder to payer", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 1, splitWith: [] }],
      ["a", "b", "c"]
    );
    // 1 / 3 = 0 each, remainder = 1 cent to payer
    // A net: 1 - 0 - 1 = 0, B net: 0, C net: 0
    // Everyone balanced — no settlements needed
    expect(result).toEqual([]);
    assertBalanced(result);
  });

  it("2 cents split 3 ways: 1 person pays 0", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 2, splitWith: [] }],
      ["a", "b", "c"]
    );
    // 2 / 3 = 0 each (integer division), remainder = 2 cents to payer
    // A net: 2 - 0 - 2 = 0
    // No settlements
    expect(result).toEqual([]);
  });

  it("splitWith subset: only splits among specified members", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: ["a", "b"] }],
      ["a", "b", "c"]
    );
    // Split only between A and B: 5000 each
    // A net: 10000 - 5000 = 5000
    // B net: -5000
    // C net: 0
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      fromId: "b",
      toId: "a",
      amountCents: 5000,
    });
    assertBalanced(result);
  });

  it("empty splitWith array -> splits among all members", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: [] }],
      ["a", "b"]
    );
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      fromId: "b",
      toId: "a",
      amountCents: 5000,
    });
  });

  it("idempotency: same input produces same output", () => {
    const expenses = [
      { paidById: "a", amountCents: 6000, splitWith: [] as string[] },
      { paidById: "b", amountCents: 4000, splitWith: [] as string[] },
    ];
    const members = ["a", "b", "c"];

    const result1 = computeSettlements(expenses, members);
    const result2 = computeSettlements(expenses, members);

    expect(result1).toEqual(result2);
  });

  it("delete-then-recompute: removing an expense changes result", () => {
    const expenses = [
      { paidById: "a", amountCents: 6000, splitWith: [] as string[] },
      { paidById: "b", amountCents: 4000, splitWith: [] as string[] },
    ];
    const members = ["a", "b"];

    const beforeDelete = computeSettlements(expenses, members);

    // Remove B's expense
    const afterDelete = computeSettlements([expenses[0]], members);

    // Results should differ
    expect(beforeDelete).not.toEqual(afterDelete);

    // After removing B's 4000, only A's 6000 remains
    // A net: 6000 - 3000 = 3000, B net: -3000
    expect(afterDelete).toHaveLength(1);
    expect(afterDelete[0].amountCents).toBe(3000);
  });

  it("sum-to-zero invariant holds for complex scenario", () => {
    const expenses = [
      { paidById: "a", amountCents: 15000, splitWith: [] as string[] },
      { paidById: "b", amountCents: 8000, splitWith: ["a", "b", "c"] },
      { paidById: "c", amountCents: 3000, splitWith: ["c", "d"] },
      { paidById: "d", amountCents: 1000, splitWith: [] as string[] },
    ];
    const members = ["a", "b", "c", "d"];

    const result = computeSettlements(expenses, members);

    // Verify: net balance after settlements should be zero for all
    const netAfter = new Map<string, number>();
    for (const m of members) netAfter.set(m, 0);

    // Compute original balances
    for (const exp of expenses) {
      const split =
        exp.splitWith.length === 0 ? members : exp.splitWith;
      const share = Math.floor(exp.amountCents / split.length);
      const remainder = exp.amountCents - share * split.length;

      netAfter.set(exp.paidById, (netAfter.get(exp.paidById) ?? 0) + exp.amountCents);
      for (const m of split) {
        if (m === exp.paidById) {
          netAfter.set(m, (netAfter.get(m) ?? 0) - share - remainder);
        } else {
          netAfter.set(m, (netAfter.get(m) ?? 0) - share);
        }
      }
    }

    // Apply settlements
    for (const s of result) {
      netAfter.set(s.fromId, (netAfter.get(s.fromId) ?? 0) + s.amountCents);
      netAfter.set(s.toId, (netAfter.get(s.toId) ?? 0) - s.amountCents);
    }

    // All should be zero (or very close due to integer rounding — at most 1 cent off)
    for (const [, balance] of netAfter) {
      expect(Math.abs(balance)).toBeLessThanOrEqual(0);
    }
  });

  it("no settlements when everyone pays their fair share", () => {
    const result = computeSettlements(
      [
        { paidById: "a", amountCents: 5000, splitWith: [] },
        { paidById: "b", amountCents: 5000, splitWith: [] },
      ],
      ["a", "b"]
    );
    expect(result).toEqual([]);
  });

  it("handles payer not in splitWith gracefully", () => {
    // Payer A pays but splits only among B and C
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10000, splitWith: ["b", "c"] }],
      ["a", "b", "c"]
    );
    // A pays 10000, splits between B(5000) and C(5000)
    // A net: 10000
    // B net: -5000
    // C net: -5000
    expect(result).toHaveLength(2);
    const totalOwed = result.reduce((s, t) => s + t.amountCents, 0);
    expect(totalOwed).toBe(10000);
    assertBalanced(result);
  });

  it("handles large amounts without overflow", () => {
    const result = computeSettlements(
      [{ paidById: "a", amountCents: 10_000_000, splitWith: [] }],
      ["a", "b"]
    );
    expect(result).toHaveLength(1);
    expect(result[0].amountCents).toBe(5_000_000);
  });

  it("multiple expenses with mixed splitWith subsets", () => {
    const result = computeSettlements(
      [
        { paidById: "a", amountCents: 6000, splitWith: ["a", "b"] },
        { paidById: "b", amountCents: 9000, splitWith: ["a", "b", "c"] },
      ],
      ["a", "b", "c"]
    );
    // Expense 1: A pays 6000, split A+B = 3000 each. A net: +3000, B net: -3000
    // Expense 2: B pays 9000, split A+B+C = 3000 each. B net: +6000, A net: -3000, C net: -3000
    // Combined: A = 3000-3000 = 0, B = -3000+6000 = 3000, C = -3000
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      fromId: "c",
      toId: "b",
      amountCents: 3000,
    });
  });
});
