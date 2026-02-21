'use client';

import { useState, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FlaggedInputRow {
  id: string;
  userId: string;
  userEmail: string | null;
  sessionId: string;
  tripId: string | null;
  eventType: string;
  surface: string | null;
  payload: Record<string, any>;
  createdAt: string;
  reviewStatus: string;
}

type ReviewFilter = 'all' | 'pending' | 'dismissed' | 'confirmed';

const REVIEW_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  dismissed: 'bg-ink-800 text-ink-500',
  confirmed: 'bg-red-100 text-error',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function InjectionQueue() {
  const [items, setItems] = useState<FlaggedInputRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('pending');
  const [actioning, setActioning] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (reviewFilter !== 'all') params.set('review_status', reviewFilter);
      params.set('skip', String(page * pageSize));
      params.set('take', String(pageSize));

      const res = await fetch(`/api/admin/safety/injection-queue?${params.toString()}`);
      if (!res.ok) throw new Error(`Failed to fetch queue: ${res.status}`);
      const data = await res.json();
      setItems(data.data);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [reviewFilter, page]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  useEffect(() => {
    setPage(0);
  }, [reviewFilter]);

  const handleReview = async (eventId: string, status: 'dismissed' | 'confirmed') => {
    setActioning(eventId);
    try {
      const res = await fetch(`/api/admin/safety/injection-queue/${eventId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Review failed: ${res.status}`);
      }
      await fetchQueue();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActioning(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      {/* Filter tabs */}
      <div className="mb-4 flex items-center gap-4">
        <div className="flex rounded border border-ink-700">
          {(['pending', 'confirmed', 'dismissed', 'all'] as ReviewFilter[]).map((f, i, arr) => (
            <button
              key={f}
              onClick={() => setReviewFilter(f)}
              className={`px-3 py-1.5 font-mono text-xs capitalize transition-colors ${
                reviewFilter === f
                  ? 'bg-accent text-white'
                  : 'bg-surface text-ink-500 hover:bg-base'
              } ${i === 0 ? 'rounded-l' : ''} ${i === arr.length - 1 ? 'rounded-r' : ''}`}
            >
              {f}
            </button>
          ))}
        </div>

        <span className="rounded bg-base px-3 py-1 font-mono text-sm text-ink-500">
          {total} flagged input{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded border border-error/30 bg-error-bg px-4 py-2">
          <p className="font-mono text-sm text-error">{error}</p>
        </div>
      )}

      {/* Queue */}
      <div className="space-y-2">
        {loading ? (
          <div className="py-8 text-center font-mono text-sm text-ink-600">
            Loading...
          </div>
        ) : items.length === 0 ? (
          <div className="py-8 text-center font-mono text-sm text-ink-600">
            No flagged inputs match filters
          </div>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              className="rounded border border-ink-700 bg-surface"
            >
              {/* Header row */}
              <div className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${REVIEW_COLORS[item.reviewStatus]}`}>
                    {item.reviewStatus}
                  </span>
                  <span className="font-mono text-sm text-ink-100">
                    {item.userEmail ?? item.userId.slice(0, 8)}
                  </span>
                  {item.surface && (
                    <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-xs text-blue-700">
                      {item.surface}
                    </span>
                  )}
                  <span className="font-mono text-xs text-ink-600">
                    {new Date(item.createdAt).toLocaleString()}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                    className="font-mono text-xs text-accent hover:underline"
                  >
                    {expandedId === item.id ? 'Collapse' : 'Details'}
                  </button>
                  {item.reviewStatus === 'pending' && (
                    <>
                      <button
                        onClick={() => handleReview(item.id, 'dismissed')}
                        disabled={actioning === item.id}
                        className="rounded border border-ink-700 px-2 py-1 font-mono text-xs text-ink-500 hover:bg-base disabled:opacity-40"
                      >
                        Dismiss
                      </button>
                      <button
                        onClick={() => handleReview(item.id, 'confirmed')}
                        disabled={actioning === item.id}
                        className="rounded bg-red-600 px-2 py-1 font-mono text-xs text-white hover:bg-red-700 disabled:opacity-40"
                      >
                        Confirm Threat
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Flagged content preview */}
              <div className="border-t border-ink-700/50 px-4 py-2">
                <p className="font-mono text-sm text-ink-300">
                  {item.payload?.inputText
                    ? String(item.payload.inputText).slice(0, 200)
                    : JSON.stringify(item.payload).slice(0, 200)}
                  {((item.payload?.inputText && String(item.payload.inputText).length > 200) ||
                    (!item.payload?.inputText && JSON.stringify(item.payload).length > 200)) && '...'}
                </p>
              </div>

              {/* Expanded details */}
              {expandedId === item.id && (
                <div className="border-t border-ink-700/50 px-4 py-3">
                  <div className="grid grid-cols-2 gap-4 font-mono text-xs">
                    <div>
                      <span className="text-ink-600">Event ID:</span>{' '}
                      <span className="text-ink-500">{item.id}</span>
                    </div>
                    <div>
                      <span className="text-ink-600">User ID:</span>{' '}
                      <span className="text-ink-500">{item.userId}</span>
                    </div>
                    <div>
                      <span className="text-ink-600">Session:</span>{' '}
                      <span className="text-ink-500">{item.sessionId.slice(0, 12)}...</span>
                    </div>
                    {item.tripId && (
                      <div>
                        <span className="text-ink-600">Trip:</span>{' '}
                        <span className="text-ink-500">{item.tripId.slice(0, 12)}...</span>
                      </div>
                    )}
                    {item.payload?.detectionReason && (
                      <div className="col-span-2">
                        <span className="text-ink-600">Detection reason:</span>{' '}
                        <span className="text-ink-500">{String(item.payload.detectionReason)}</span>
                      </div>
                    )}
                    {item.payload?.confidenceScore !== undefined && (
                      <div>
                        <span className="text-ink-600">Confidence:</span>{' '}
                        <span className="text-ink-500">{item.payload.confidenceScore}</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-3">
                    <p className="mb-1 font-mono text-xs text-ink-600">Full payload:</p>
                    <pre className="max-h-40 overflow-auto rounded bg-base p-2 font-mono text-xs text-ink-500">
                      {JSON.stringify(item.payload, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="font-mono text-xs text-ink-600">
            Showing {page * pageSize + 1}--{Math.min((page + 1) * pageSize, total)} of {total}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-ink-700 px-2 py-1 font-mono text-xs text-ink-500 hover:bg-base disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-ink-700 px-2 py-1 font-mono text-xs text-ink-500 hover:bg-base disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
