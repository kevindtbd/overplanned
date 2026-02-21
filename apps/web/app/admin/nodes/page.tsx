'use client';

import { useState, useEffect, useCallback } from 'react';
import NodeEditor from './components/NodeEditor';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeRow {
  id: string;
  name: string;
  canonicalName: string;
  city: string;
  country: string;
  category: string;
  status: string;
  convergenceScore: number | null;
  sourceCount: number;
  flagReason: string | null;
  aliasCount: number;
  updatedAt: string;
}

interface NodesResponse {
  nodes: NodeRow[];
  total: number;
  skip: number;
  take: number;
}

type StatusFilter = 'all' | 'flagged' | 'pending' | 'approved' | 'archived';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  flagged: 'bg-red-100 text-red-800',
  archived: 'bg-ink-800 text-ink-500',
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminNodesPage() {
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [cityFilter, setCityFilter] = useState('');
  const [maxConvergence, setMaxConvergence] = useState<string>('');
  const [sortField, setSortField] = useState('convergenceScore');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Editor
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);

  const fetchNodes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (searchQuery) params.set('search', searchQuery);
      if (cityFilter) params.set('city', cityFilter);
      if (maxConvergence) params.set('max_convergence', maxConvergence);
      params.set('sort', sortField);
      params.set('order', sortOrder);
      params.set('skip', String(page * pageSize));
      params.set('take', String(pageSize));

      const res = await fetch(`/api/admin/nodes?${params.toString()}`);
      if (!res.ok) throw new Error(`Failed to fetch nodes: ${res.status}`);
      const data: NodesResponse = await res.json();
      setNodes(data.nodes);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchQuery, cityFilter, maxConvergence, sortField, sortOrder, page]);

  useEffect(() => {
    fetchNodes();
  }, [fetchNodes]);

  // Reset to page 0 when filters change
  useEffect(() => {
    setPage(0);
  }, [statusFilter, searchQuery, cityFilter, maxConvergence]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const sortIndicator = (field: string) => {
    if (sortField !== field) return '';
    return sortOrder === 'asc' ? ' ^' : ' v';
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl text-ink-100">Node Queue</h2>
          <p className="font-mono text-sm text-ink-500">
            Flagged and low-convergence nodes requiring admin review
          </p>
        </div>
        <span className="rounded bg-base px-3 py-1 font-mono text-sm text-ink-500">
          {total} node{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        {/* Status tabs */}
        <div className="flex rounded border border-ink-700">
          {(['all', 'flagged', 'pending', 'approved', 'archived'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 font-mono text-xs capitalize transition-colors ${
                statusFilter === s
                  ? 'bg-accent text-white'
                  : 'bg-surface text-ink-500 hover:bg-base'
              } ${s === 'all' ? 'rounded-l' : ''} ${s === 'archived' ? 'rounded-r' : ''}`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search name..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="rounded border border-ink-700 bg-base px-3 py-1.5 font-mono text-sm focus:border-accent focus:outline-none"
        />

        {/* City */}
        <input
          type="text"
          placeholder="City..."
          value={cityFilter}
          onChange={(e) => setCityFilter(e.target.value)}
          className="w-32 rounded border border-ink-700 bg-base px-3 py-1.5 font-mono text-sm focus:border-accent focus:outline-none"
        />

        {/* Max convergence */}
        <label className="flex items-center gap-1">
          <span className="font-mono text-xs text-ink-500">Conv &le;</span>
          <input
            type="number"
            step="0.1"
            min="0"
            max="1"
            placeholder="1.0"
            value={maxConvergence}
            onChange={(e) => setMaxConvergence(e.target.value)}
            className="w-20 rounded border border-ink-700 bg-base px-2 py-1.5 font-mono text-sm focus:border-accent focus:outline-none"
          />
        </label>
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
              <th className="cursor-pointer px-3 py-2" onClick={() => handleSort('name')}>
                Name{sortIndicator('name')}
              </th>
              <th className="px-3 py-2">City</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Status</th>
              <th className="cursor-pointer px-3 py-2" onClick={() => handleSort('convergenceScore')}>
                Conv.{sortIndicator('convergenceScore')}
              </th>
              <th className="cursor-pointer px-3 py-2" onClick={() => handleSort('sourceCount')}>
                Sources{sortIndicator('sourceCount')}
              </th>
              <th className="px-3 py-2">Flag Reason</th>
              <th className="cursor-pointer px-3 py-2" onClick={() => handleSort('updatedAt')}>
                Updated{sortIndicator('updatedAt')}
              </th>
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
            ) : nodes.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-ink-600">
                  No nodes match filters
                </td>
              </tr>
            ) : (
              nodes.map((node) => (
                <tr
                  key={node.id}
                  className="border-b border-ink-700/50 hover:bg-base/50 transition-colors"
                >
                  <td className="px-3 py-2">
                    <button
                      onClick={() => setEditingNodeId(node.id)}
                      className="text-left text-ink-100 hover:text-accent"
                    >
                      {node.name}
                    </button>
                    {node.aliasCount > 0 && (
                      <span className="ml-1 text-xs text-ink-600">+{node.aliasCount}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink-500">{node.city}</td>
                  <td className="px-3 py-2 text-ink-500">{node.category}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_COLORS[node.status] ?? 'bg-ink-800 text-ink-500'}`}>
                      {node.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-ink-500">
                    {node.convergenceScore !== null ? node.convergenceScore.toFixed(3) : '--'}
                  </td>
                  <td className="px-3 py-2 text-ink-500">{node.sourceCount}</td>
                  <td className="max-w-[200px] truncate px-3 py-2 text-xs text-ink-500">
                    {node.flagReason ?? '--'}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-600">
                    {new Date(node.updatedAt).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => setEditingNodeId(node.id)}
                      className="text-xs text-accent hover:underline"
                    >
                      Edit
                    </button>
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
            Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}
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

      {/* Node editor modal */}
      {editingNodeId && (
        <NodeEditor
          nodeId={editingNodeId}
          onClose={() => setEditingNodeId(null)}
          onSaved={() => fetchNodes()}
        />
      )}
    </div>
  );
}
