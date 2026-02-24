/**
 * Settle-up utility for computing minimal settlements from group expenses.
 *
 * Pure function — no side effects, no DB access.
 */

export interface Settlement {
  fromId: string;
  toId: string;
  amountCents: number;
}

export function computeSettlements(
  expenses: { paidById: string; amountCents: number; splitWith: string[] }[],
  allMemberIds: string[]
): Settlement[] {
  if (expenses.length === 0 || allMemberIds.length <= 1) {
    return [];
  }

  // Net balance for each member: positive = owed money, negative = owes money
  const balances = new Map<string, number>();
  for (const memberId of allMemberIds) {
    balances.set(memberId, 0);
  }

  for (const expense of expenses) {
    // Determine who's in the split
    const splitMembers =
      !expense.splitWith || expense.splitWith.length === 0
        ? allMemberIds
        : expense.splitWith;

    const splitCount = splitMembers.length;
    if (splitCount === 0) continue;

    const share = Math.floor(expense.amountCents / splitCount);
    const remainder = expense.amountCents - share * splitCount;

    // Credit the payer for the full amount
    const payerBalance = balances.get(expense.paidById) ?? 0;
    balances.set(expense.paidById, payerBalance + expense.amountCents);

    // Debit each split member for their share
    for (const memberId of splitMembers) {
      const current = balances.get(memberId) ?? 0;
      if (memberId === expense.paidById) {
        // Payer absorbs the remainder — they owe share + remainder to themselves
        balances.set(memberId, current - share - remainder);
      } else {
        balances.set(memberId, current - share);
      }
    }
  }

  // Separate into creditors (positive balance) and debtors (negative balance)
  const creditors: { id: string; amount: number }[] = [];
  const debtors: { id: string; amount: number }[] = [];

  for (const [id, balance] of balances) {
    if (balance > 0) {
      creditors.push({ id, amount: balance });
    } else if (balance < 0) {
      debtors.push({ id, amount: -balance }); // store as positive
    }
  }

  // Sort descending by amount
  creditors.sort((a, b) => b.amount - a.amount);
  debtors.sort((a, b) => b.amount - a.amount);

  // Greedy pairing
  const settlements: Settlement[] = [];
  let ci = 0;
  let di = 0;

  while (ci < creditors.length && di < debtors.length) {
    const transfer = Math.min(debtors[di].amount, creditors[ci].amount);
    if (transfer > 0) {
      settlements.push({
        fromId: debtors[di].id,
        toId: creditors[ci].id,
        amountCents: transfer,
      });
    }
    debtors[di].amount -= transfer;
    creditors[ci].amount -= transfer;

    if (debtors[di].amount === 0) di++;
    if (creditors[ci].amount === 0) ci++;
  }

  return settlements;
}
