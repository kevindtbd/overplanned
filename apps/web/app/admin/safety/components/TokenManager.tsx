'use client';

import { useState, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SharedTokenRow {
  id: string;
  tripId: string;
  tripDestination: string | null;
  token: string;
  createdBy: string;
  creatorEmail: string | null;
  expiresAt: string;
  revokedAt: string | null;
  viewCount: number;
  importCount: number;
  createdAt: string;
  isExpired: boolean;
  isRevoked: boolean;
}

interface InviteTokenRow {
  id: string;
  tripId: string;
  tripDestination: string | null;
  token: string;
  createdBy: string;
  creatorEmail: string | null;
  maxUses: number;
  usedCount: number;
  role: string;
  expiresAt: string;
  revokedAt: string | null;
  createdAt: string;
  isExpired: boolean;
  isRevoked: boolean;
}

type TokenType = 'shared' | 'invite';
type StatusFilter = 'all' | 'active' | 'revoked' | 'expired';

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  revoked: 'bg-red-100 text-error',
  expired: 'bg-ink-800 text-ink-500',
};

function tokenStatus(isRevoked: boolean, isExpired: boolean): string {
  if (isRevoked) return 'revoked';
  if (isExpired) return 'expired';
  return 'active';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TokenManager() {
  const [tokenType, setTokenType] = useState<TokenType>('shared');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sharedTokens, setSharedTokens] = useState<SharedTokenRow[]>([]);
  const [inviteTokens, setInviteTokens] = useState<InviteTokenRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchTokens = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      params.set('skip', String(page * pageSize));
      params.set('take', String(pageSize));

      const endpoint = tokenType === 'shared'
        ? '/api/admin/safety/tokens/shared'
        : '/api/admin/safety/tokens/invite';

      const res = await fetch(`${endpoint}?${params.toString()}`);
      if (!res.ok) throw new Error(`Failed to fetch tokens: ${res.status}`);
      const data = await res.json();

      if (tokenType === 'shared') {
        setSharedTokens(data.data);
      } else {
        setInviteTokens(data.data);
      }
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tokenType, statusFilter, page]);

  useEffect(() => {
    fetchTokens();
  }, [fetchTokens]);

  useEffect(() => {
    setPage(0);
  }, [tokenType, statusFilter]);

  const handleRevoke = async (tokenId: string) => {
    setRevoking(tokenId);
    try {
      const endpoint = tokenType === 'shared'
        ? `/api/admin/safety/tokens/shared/${tokenId}/revoke`
        : `/api/admin/safety/tokens/invite/${tokenId}/revoke`;

      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Revoke failed: ${res.status}`);
      }
      await fetchTokens();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setRevoking(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      {/* Token type tabs */}
      <div className="mb-4 flex items-center gap-4">
        <div className="flex rounded border border-ink-700">
          {(['shared', 'invite'] as TokenType[]).map((t) => (
            <button
              key={t}
              onClick={() => setTokenType(t)}
              className={`px-3 py-1.5 font-dm-mono text-xs capitalize transition-colors ${
                tokenType === t
                  ? 'bg-accent text-white'
                  : 'bg-surface text-ink-500 hover:bg-base'
              } ${t === 'shared' ? 'rounded-l' : 'rounded-r'}`}
            >
              {t === 'shared' ? 'Shared Trip' : 'Invite'} Tokens
            </button>
          ))}
        </div>

        {/* Status filter */}
        <div className="flex rounded border border-ink-700">
          {(['all', 'active', 'revoked', 'expired'] as StatusFilter[]).map((s, i, arr) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 font-dm-mono text-xs capitalize transition-colors ${
                statusFilter === s
                  ? 'bg-accent text-white'
                  : 'bg-surface text-ink-500 hover:bg-base'
              } ${i === 0 ? 'rounded-l' : ''} ${i === arr.length - 1 ? 'rounded-r' : ''}`}
            >
              {s}
            </button>
          ))}
        </div>

        <span className="rounded bg-base px-3 py-1 font-dm-mono text-sm text-ink-500">
          {total} token{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded border border-error/30 bg-error-bg px-4 py-2">
          <p className="font-dm-mono text-sm text-error">{error}</p>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded border border-ink-700">
        <table className="w-full font-dm-mono text-sm">
          <thead>
            <tr className="border-b border-ink-700 bg-base text-left text-xs text-ink-500">
              <th className="px-3 py-2">Token</th>
              <th className="px-3 py-2">Trip</th>
              <th className="px-3 py-2">Created By</th>
              <th className="px-3 py-2">Status</th>
              {tokenType === 'shared' ? (
                <>
                  <th className="px-3 py-2">Views</th>
                  <th className="px-3 py-2">Imports</th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2">Uses</th>
                  <th className="px-3 py-2">Role</th>
                </>
              )}
              <th className="px-3 py-2">Expires</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-ink-600">
                  Loading...
                </td>
              </tr>
            ) : tokenType === 'shared' ? (
              sharedTokens.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-ink-600">
                    No shared tokens match filters
                  </td>
                </tr>
              ) : (
                sharedTokens.map((t) => {
                  const status = tokenStatus(t.isRevoked, t.isExpired);
                  return (
                    <tr
                      key={t.id}
                      className="border-b border-ink-700/50 transition-colors hover:bg-base/50"
                    >
                      <td className="px-3 py-2 text-ink-500">{t.token}</td>
                      <td className="px-3 py-2">
                        <span className="text-ink-100">{t.tripDestination ?? t.tripId.slice(0, 8)}</span>
                      </td>
                      <td className="px-3 py-2 text-ink-500">{t.creatorEmail ?? t.createdBy.slice(0, 8)}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_COLORS[status]}`}>
                          {status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-ink-500">{t.viewCount}</td>
                      <td className="px-3 py-2 text-ink-500">{t.importCount}</td>
                      <td className="px-3 py-2 text-xs text-ink-600">
                        {new Date(t.expiresAt).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-600">
                        {new Date(t.createdAt).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">
                        {status === 'active' && (
                          <button
                            onClick={() => handleRevoke(t.id)}
                            disabled={revoking === t.id}
                            className="text-xs text-error hover:underline disabled:opacity-40"
                          >
                            {revoking === t.id ? 'Revoking...' : 'Revoke'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )
            ) : (
              inviteTokens.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-ink-600">
                    No invite tokens match filters
                  </td>
                </tr>
              ) : (
                inviteTokens.map((t) => {
                  const status = tokenStatus(t.isRevoked, t.isExpired);
                  return (
                    <tr
                      key={t.id}
                      className="border-b border-ink-700/50 transition-colors hover:bg-base/50"
                    >
                      <td className="px-3 py-2 text-ink-500">{t.token}</td>
                      <td className="px-3 py-2">
                        <span className="text-ink-100">{t.tripDestination ?? t.tripId.slice(0, 8)}</span>
                      </td>
                      <td className="px-3 py-2 text-ink-500">{t.creatorEmail ?? t.createdBy.slice(0, 8)}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_COLORS[status]}`}>
                          {status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-ink-500">{t.usedCount}/{t.maxUses}</td>
                      <td className="px-3 py-2">
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                          {t.role}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-600">
                        {new Date(t.expiresAt).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-600">
                        {new Date(t.createdAt).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">
                        {status === 'active' && (
                          <button
                            onClick={() => handleRevoke(t.id)}
                            disabled={revoking === t.id}
                            className="text-xs text-error hover:underline disabled:opacity-40"
                          >
                            {revoking === t.id ? 'Revoking...' : 'Revoke'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="font-dm-mono text-xs text-ink-600">
            Showing {page * pageSize + 1}--{Math.min((page + 1) * pageSize, total)} of {total}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-ink-700 px-2 py-1 font-dm-mono text-xs text-ink-500 hover:bg-base disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-ink-700 px-2 py-1 font-dm-mono text-xs text-ink-500 hover:bg-base disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
