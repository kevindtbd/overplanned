"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { UserAvatar } from "@/components/shared/UserAvatar";

// --- Types ---

interface ExpenseTrackerProps {
  tripId: string;
  currentUserId: string;
  currency: string;
  members: Array<{
    id: string;
    userId: string;
    user: { id: string; name: string | null; avatarUrl: string | null };
  }>;
}

interface Expense {
  id: string;
  description: string;
  amountCents: number;
  paidById: string;
  paidBy: { id: string; name: string | null; avatarUrl: string | null };
  splitWith: string[];
  createdAt: string;
}

interface Settlement {
  fromId: string;
  fromName: string;
  toId: string;
  toName: string;
  amountCents: number;
}

// --- Currency helpers ---

const ZERO_DECIMAL = ["JPY", "KRW", "VND", "CLP"];

function isZeroDecimal(currency: string): boolean {
  return ZERO_DECIMAL.includes(currency.toUpperCase());
}

function formatAmount(amountCents: number, currency: string): string {
  const code = currency.toUpperCase();
  const value = isZeroDecimal(code) ? amountCents : amountCents / 100;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
      minimumFractionDigits: isZeroDecimal(code) ? 0 : 2,
      maximumFractionDigits: isZeroDecimal(code) ? 0 : 2,
    }).format(value);
  } catch {
    // Fallback if currency code is unsupported
    return `${code} ${value.toLocaleString()}`;
  }
}

function parseInputToAmountCents(input: string, currency: string): number | null {
  const num = parseFloat(input);
  if (isNaN(num) || num <= 0) return null;
  if (isZeroDecimal(currency)) {
    return Math.round(num);
  }
  return Math.round(num * 100);
}

// --- SVG Icons ---

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M4 6L8 10L12 6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M7 2V12M2 7H12"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M3 3L9 9M9 3L3 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M6.5 10L9 12.5L13.5 7.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// --- Skeleton loader ---

function ExpenseSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-[13px] bg-base border border-ink-700 p-3"
        >
          <div className="flex items-center gap-3">
            <div className="h-6 w-6 rounded-full bg-ink-700" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 w-24 rounded bg-ink-700" />
              <div className="h-2.5 w-16 rounded bg-ink-700" />
            </div>
            <div className="h-4 w-14 rounded bg-ink-700" />
          </div>
        </div>
      ))}
    </div>
  );
}

// --- Main Component ---

export function ExpenseTracker({
  tripId,
  currentUserId,
  currency,
  members,
}: ExpenseTrackerProps) {
  const [expanded, setExpanded] = useState(true);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [description, setDescription] = useState("");
  const [amountInput, setAmountInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const descriptionRef = useRef<HTMLInputElement>(null);

  const fetchData = useCallback(async () => {
    try {
      const [expRes, settleRes] = await Promise.all([
        fetch(`/api/trips/${tripId}/expenses`),
        fetch(`/api/trips/${tripId}/expenses/settle`),
      ]);

      if (!expRes.ok || !settleRes.ok) {
        setError("Failed to load expenses");
        return;
      }

      const expData = await expRes.json();
      const settleData = await settleRes.json();

      setExpenses(expData.expenses ?? []);
      setSettlements(settleData.settlements ?? []);
      setError(null);
    } catch {
      setError("Network error loading expenses");
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAdd = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setFormError(null);

      const trimmedDesc = description.trim();
      if (!trimmedDesc) {
        setFormError("Description is required");
        return;
      }

      const amountCents = parseInputToAmountCents(amountInput, currency);
      if (amountCents === null) {
        setFormError("Enter a valid amount greater than 0");
        return;
      }

      setSubmitting(true);
      try {
        const res = await fetch(`/api/trips/${tripId}/expenses`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: trimmedDesc, amountCents }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setFormError(data.error || "Failed to add expense");
          return;
        }

        setDescription("");
        setAmountInput("");
        setShowForm(false);
        await fetchData();
      } catch {
        setFormError("Network error");
      } finally {
        setSubmitting(false);
      }
    },
    [description, amountInput, currency, tripId, fetchData]
  );

  const handleDelete = useCallback(
    async (expenseId: string) => {
      setDeleting(expenseId);
      try {
        const res = await fetch(
          `/api/trips/${tripId}/expenses/${expenseId}`,
          { method: "DELETE" }
        );
        if (res.ok) {
          await fetchData();
        }
      } catch {
        // Silently fail — next refresh will sync
      } finally {
        setDeleting(null);
      }
    },
    [tripId, fetchData]
  );

  // Compute total
  const totalCents = expenses.reduce((sum, e) => sum + e.amountCents, 0);

  // Resolve settlements relative to current user
  const mySettlements = settlements.filter(
    (s) => s.fromId === currentUserId || s.toId === currentUserId
  );

  const zeroDecimal = isZeroDecimal(currency);
  const amountPlaceholder = zeroDecimal ? "4200" : "42.50";
  const amountStep = zeroDecimal ? "1" : "0.01";

  return (
    <div className="rounded-xl bg-surface border border-ink-700">
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between p-4 text-left"
        aria-expanded={expanded}
        aria-controls="expense-tracker-content"
      >
        <div className="flex items-center gap-3">
          <h3 className="font-sora text-lg text-ink-100">Expenses</h3>
          {!loading && (
            <span className="font-dm-mono text-xs text-ink-400">
              {formatAmount(totalCents, currency)}
            </span>
          )}
        </div>
        <ChevronDownIcon
          className={`text-ink-400 transition-transform duration-200 ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {expanded && (
        <div id="expense-tracker-content" className="px-4 pb-4 space-y-5">
          {/* --- Expense List --- */}
          {loading ? (
            <ExpenseSkeleton />
          ) : expenses.length === 0 && !showForm ? (
            <p className="text-sm text-ink-400 font-dm-mono py-2">
              No expenses yet. Add one to start tracking.
            </p>
          ) : (
            <div className="space-y-2">
              {expenses.map((expense) => (
                <div
                  key={expense.id}
                  className="rounded-[13px] bg-base border border-ink-700 p-3 flex items-center gap-3"
                >
                  <UserAvatar name={expense.paidBy.name} avatarUrl={expense.paidBy.avatarUrl} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-ink-100 truncate">
                      {expense.description}
                    </p>
                    <p className="font-dm-mono text-xs text-ink-400 mt-0.5">
                      {expense.paidBy.name ?? "Someone"} paid
                      {expense.splitWith.length > 1
                        ? ` / split ${expense.splitWith.length} ways`
                        : ""}
                    </p>
                  </div>
                  <span className="font-dm-mono text-sm text-ink-100 flex-shrink-0">
                    {formatAmount(expense.amountCents, currency)}
                  </span>
                  {expense.paidById === currentUserId && (
                    <button
                      onClick={() => handleDelete(expense.id)}
                      disabled={deleting === expense.id}
                      className="flex-shrink-0 p-1 rounded text-ink-400 hover:text-error transition-colors disabled:opacity-50"
                      aria-label={`Delete expense: ${expense.description}`}
                    >
                      <XIcon />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* --- Add Expense --- */}
          {!loading && (
            <div>
              {!showForm ? (
                <button
                  onClick={() => {
                    setShowForm(true);
                    setTimeout(() => descriptionRef.current?.focus(), 0);
                  }}
                  className="flex items-center gap-1.5 text-sm text-accent hover:text-accent/80 transition-colors font-dm-mono"
                >
                  <PlusIcon />
                  Add expense
                </button>
              ) : (
                <form
                  onSubmit={handleAdd}
                  className="rounded-[13px] bg-base border border-ink-700 p-3 space-y-3"
                >
                  <input
                    ref={descriptionRef}
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What was it for?"
                    maxLength={200}
                    className="block w-full rounded-lg border border-ink-700 bg-surface px-3 py-2 font-dm-mono text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent focus:outline-none"
                    aria-label="Expense description"
                  />
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={amountInput}
                      onChange={(e) => setAmountInput(e.target.value)}
                      placeholder={amountPlaceholder}
                      step={amountStep}
                      min="0"
                      className="block flex-1 rounded-lg border border-ink-700 bg-surface px-3 py-2 font-dm-mono text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent focus:outline-none"
                      aria-label={`Amount in ${currency}`}
                    />
                    <button
                      type="submit"
                      disabled={submitting}
                      className="rounded-lg bg-accent px-4 py-2 font-dm-mono text-xs text-white transition hover:bg-accent/90 disabled:opacity-50"
                    >
                      {submitting ? "Adding..." : "Add"}
                    </button>
                  </div>
                  {formError && (
                    <p className="text-sm text-error">{formError}</p>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setShowForm(false);
                      setFormError(null);
                    }}
                    className="text-xs font-dm-mono text-ink-400 hover:text-ink-200 transition-colors"
                  >
                    Cancel
                  </button>
                </form>
              )}
            </div>
          )}

          {/* --- Settle Up Section --- */}
          {!loading && (
            <div>
              <h4 className="font-sora text-base text-ink-100 mb-3">
                Settle Up
              </h4>
              {mySettlements.length === 0 ? (
                <div className="flex items-center gap-2 text-ink-400 py-2">
                  <CheckCircleIcon />
                  <span className="font-dm-mono text-sm">All settled up!</span>
                </div>
              ) : (
                <div className="space-y-2">
                  {mySettlements.map((s, idx) => {
                    const iOwe = s.fromId === currentUserId;
                    const otherName = iOwe ? s.toName : s.fromName;
                    const otherId = iOwe ? s.toId : s.fromId;
                    const label = iOwe
                      ? `You owe ${otherName}`
                      : `${otherName} owes you`;

                    const otherUser = members.find((m) => m.userId === otherId)?.user ?? { name: otherName, avatarUrl: null };
                    const myUser = members.find((m) => m.userId === currentUserId)?.user ?? { name: "You", avatarUrl: null };

                    return (
                      <div
                        key={`${s.fromId}-${s.toId}-${idx}`}
                        className="rounded-[13px] bg-base border border-ink-700 p-3 flex items-center gap-3"
                      >
                        <div className="flex -space-x-1.5">
                          <UserAvatar name={(iOwe ? myUser : otherUser).name} avatarUrl={(iOwe ? myUser : otherUser).avatarUrl} size="sm" />
                          <UserAvatar name={(iOwe ? otherUser : myUser).name} avatarUrl={(iOwe ? otherUser : myUser).avatarUrl} size="sm" />
                        </div>
                        <p className="flex-1 text-sm text-ink-200">{label}</p>
                        <span
                          className={`font-dm-mono text-sm flex-shrink-0 ${
                            iOwe ? "text-error" : "text-success"
                          }`}
                        >
                          {formatAmount(s.amountCents, currency)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
