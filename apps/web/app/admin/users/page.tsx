'use client';

import { useState, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserRow {
  id: string;
  email: string;
  name: string | null;
  avatarUrl: string | null;
  subscriptionTier: string;
  systemRole: string;
  featureFlags: Record<string, boolean> | null;
  onboardingComplete: boolean;
  lastActiveAt: string | null;
  createdAt: string;
}

interface UsersResponse {
  users: UserRow[];
  total: number;
  skip: number;
  take: number;
}

type TierFilter = 'all' | 'free' | 'beta' | 'pro' | 'lifetime';

const TIER_COLORS: Record<string, string> = {
  free: 'bg-ink-800 text-ink-500',
  beta: 'bg-blue-100 text-blue-800',
  pro: 'bg-purple-100 text-purple-800',
  lifetime: 'bg-amber-100 text-amber-800',
};

const ROLE_COLORS: Record<string, string> = {
  user: 'bg-ink-800 text-ink-500',
  admin: 'bg-red-100 text-error',
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [tierFilter, setTierFilter] = useState<TierFilter>('all');
  const [sortField, setSortField] = useState('createdAt');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.set('q', searchQuery);
      if (tierFilter !== 'all') params.set('tier', tierFilter);
      params.set('sort', sortField);
      params.set('order', sortOrder);
      params.set('skip', String(page * pageSize));
      params.set('take', String(pageSize));

      const res = await fetch(`/api/admin/users?${params.toString()}`);
      if (!res.ok) throw new Error(`Failed to fetch users: ${res.status}`);
      const data: UsersResponse = await res.json();
      setUsers(data.users);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, tierFilter, sortField, sortOrder, page]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Reset to page 0 when filters change
  useEffect(() => {
    setPage(0);
  }, [searchQuery, tierFilter]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const sortIndicator = (field: string) => {
    if (sortField !== field) return '';
    return sortOrder === 'asc' ? ' ^' : ' v';
  };

  const flagCount = (flags: Record<string, boolean> | null): number => {
    if (!flags) return 0;
    return Object.values(flags).filter(Boolean).length;
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl text-ink-100">Users</h2>
          <p className="font-mono text-sm text-ink-500">
            Search, view, and manage user accounts
          </p>
        </div>
        <span className="rounded bg-base px-3 py-1 font-mono text-sm text-ink-500">
          {total} user{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        {/* Tier tabs */}
        <div className="flex rounded border border-ink-700">
          {(['all', 'beta', 'free', 'pro', 'lifetime'] as TierFilter[]).map((t) => (
            <button
              key={t}
              onClick={() => setTierFilter(t)}
              className={`px-3 py-1.5 font-mono text-xs capitalize transition-colors ${
                tierFilter === t
                  ? 'bg-accent text-white'
                  : 'bg-surface text-ink-500 hover:bg-base'
              } ${t === 'all' ? 'rounded-l' : ''} ${t === 'lifetime' ? 'rounded-r' : ''}`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search email or name..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="min-w-[240px] rounded border border-ink-700 bg-base px-3 py-1.5 font-mono text-sm focus:border-accent focus:outline-none"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded border border-error/30 bg-error-bg px-4 py-2">
          <p className="font-mono text-sm text-error">{error}</p>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded border border-ink-700">
        <table className="w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-ink-700 bg-base text-left text-xs text-ink-500">
              <th className="px-3 py-2">User</th>
              <th
                className="cursor-pointer px-3 py-2"
                onClick={() => handleSort('email')}
              >
                Email{sortIndicator('email')}
              </th>
              <th className="px-3 py-2">Tier</th>
              <th className="px-3 py-2">Role</th>
              <th className="px-3 py-2">Flags</th>
              <th
                className="cursor-pointer px-3 py-2"
                onClick={() => handleSort('lastActiveAt')}
              >
                Last Active{sortIndicator('lastActiveAt')}
              </th>
              <th
                className="cursor-pointer px-3 py-2"
                onClick={() => handleSort('createdAt')}
              >
                Joined{sortIndicator('createdAt')}
              </th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-ink-600">
                  Loading...
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-ink-600">
                  No users match filters
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr
                  key={user.id}
                  className="border-b border-ink-700/50 transition-colors hover:bg-base/50"
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      {user.avatarUrl ? (
                        <img
                          src={user.avatarUrl}
                          alt=""
                          className="h-6 w-6 rounded-full"
                        />
                      ) : (
                        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-base text-xs text-ink-600">
                          {(user.name ?? user.email)[0].toUpperCase()}
                        </div>
                      )}
                      <span className="text-ink-100">
                        {user.name ?? '--'}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-ink-500">{user.email}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        TIER_COLORS[user.subscriptionTier] ?? 'bg-ink-800 text-ink-500'
                      }`}
                    >
                      {user.subscriptionTier}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        ROLE_COLORS[user.systemRole] ?? 'bg-ink-800 text-ink-500'
                      }`}
                    >
                      {user.systemRole}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-ink-500">
                    {flagCount(user.featureFlags) > 0 ? (
                      <span className="rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">
                        {flagCount(user.featureFlags)} active
                      </span>
                    ) : (
                      <span className="text-xs text-ink-600">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-600">
                    {user.lastActiveAt
                      ? new Date(user.lastActiveAt).toLocaleDateString()
                      : '--'}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-600">
                    {new Date(user.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2">
                    <a
                      href={`/admin/users/${user.id}`}
                      className="text-xs text-accent hover:underline"
                    >
                      View
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="font-mono text-xs text-ink-600">
            Showing {page * pageSize + 1}--{Math.min((page + 1) * pageSize, total)} of{' '}
            {total}
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
