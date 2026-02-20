'use client';

import { useState, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Alias {
  id: string;
  alias: string;
  source: string;
  createdAt?: string;
}

interface QualitySignal {
  id: string;
  sourceName: string;
  sourceAuthority: number;
  signalType: string;
  extractedAt: string;
}

interface VibeTagEntry {
  id: string;
  tagName: string | null;
  tagSlug: string | null;
  score: number;
  source: string;
}

interface NodeDetail {
  id: string;
  name: string;
  canonicalName: string;
  city: string;
  country: string;
  neighborhood: string | null;
  category: string;
  subcategory: string | null;
  status: string;
  convergenceScore: number | null;
  sourceCount: number;
  flagReason: string | null;
  resolvedToId: string | null;
  isCanonical: boolean;
  priceLevel: number | null;
  address: string | null;
  phoneNumber: string | null;
  websiteUrl: string | null;
  descriptionShort: string | null;
  descriptionLong: string | null;
  slug: string;
  latitude: number;
  longitude: number;
  primaryImageUrl: string | null;
  lastScrapedAt: string | null;
  lastValidatedAt: string | null;
  createdAt: string;
  updatedAt: string;
  aliases: Alias[];
  qualitySignals: QualitySignal[];
  vibeTags: VibeTagEntry[];
}

interface NodeEditorProps {
  nodeId: string;
  onClose: () => void;
  onSaved: () => void;
}

type NodeStatus = 'pending' | 'approved' | 'flagged' | 'archived';

const STATUS_OPTIONS: { value: NodeStatus; label: string; color: string }[] = [
  { value: 'pending', label: 'Pending', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'approved', label: 'Approved', color: 'bg-green-100 text-green-800' },
  { value: 'flagged', label: 'Flagged', color: 'bg-red-100 text-red-800' },
  { value: 'archived', label: 'Archived', color: 'bg-gray-100 text-gray-600' },
];

const CATEGORY_OPTIONS = [
  'dining', 'drinks', 'culture', 'outdoors', 'active',
  'entertainment', 'shopping', 'experience', 'nightlife',
  'group_activity', 'wellness',
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function NodeEditor({ nodeId, onClose, onSaved }: NodeEditorProps) {
  const [node, setNode] = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editFields, setEditFields] = useState<Record<string, any>>({});
  const [newAlias, setNewAlias] = useState('');
  const [activeTab, setActiveTab] = useState<'details' | 'aliases' | 'signals'>('details');

  // Fetch node detail on mount
  const fetchNode = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/nodes/${nodeId}`);
      if (!res.ok) throw new Error(`Failed to load node: ${res.status}`);
      const data = await res.json();
      setNode(data);
      setEditFields({});
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [nodeId]);

  // Trigger fetch on first render
  useState(() => {
    fetchNode();
  });

  const setField = (key: string, value: any) => {
    setEditFields((prev) => ({ ...prev, [key]: value }));
  };

  const hasChanges = Object.keys(editFields).length > 0;

  // Save edited fields
  const handleSave = async () => {
    if (!hasChanges) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/nodes/${nodeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editFields),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Save failed: ${res.status}`);
      }
      await fetchNode();
      onSaved();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Status change shortcut (approve / archive / flag)
  const handleStatusChange = async (status: NodeStatus) => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, any> = { status };
      if (status !== 'flagged') body.flagReason = null;
      const res = await fetch(`/api/admin/nodes/${nodeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Status change failed: ${res.status}`);
      await fetchNode();
      onSaved();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Alias management
  const handleAddAlias = async () => {
    if (!newAlias.trim()) return;
    try {
      const res = await fetch(`/api/admin/nodes/${nodeId}/aliases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: newAlias.trim(), source: 'admin' }),
      });
      if (!res.ok) throw new Error(`Failed to add alias: ${res.status}`);
      setNewAlias('');
      await fetchNode();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleRemoveAlias = async (aliasId: string) => {
    try {
      const res = await fetch(`/api/admin/nodes/${nodeId}/aliases/${aliasId}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`Failed to remove alias: ${res.status}`);
      await fetchNode();
    } catch (err: any) {
      setError(err.message);
    }
  };

  // Current value (edited or original)
  const val = (key: keyof NodeDetail) =>
    key in editFields ? editFields[key] : node?.[key] ?? '';

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
        <div className="rounded-lg bg-warm-surface p-8 shadow-xl">
          <p className="font-mono text-sm text-gray-600">Loading node...</p>
        </div>
      </div>
    );
  }

  if (!node) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
        <div className="rounded-lg bg-warm-surface p-8 shadow-xl">
          <p className="font-mono text-sm text-red-600">{error || 'Node not found'}</p>
          <button onClick={onClose} className="mt-4 font-mono text-sm text-terracotta">
            Close
          </button>
        </div>
      </div>
    );
  }

  const currentStatus = STATUS_OPTIONS.find(
    (s) => s.value === (editFields.status ?? node.status)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 pt-8 pb-8">
      <div className="w-full max-w-3xl rounded-lg border border-warm-border bg-warm-surface shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-warm-border px-6 py-4">
          <div>
            <h2 className="font-display text-lg text-gray-900">{node.name}</h2>
            <p className="font-mono text-xs text-gray-500">
              {node.city}, {node.country} &middot; {node.slug}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {currentStatus && (
              <span className={`rounded px-2 py-0.5 font-mono text-xs ${currentStatus.color}`}>
                {currentStatus.label}
              </span>
            )}
            <button
              onClick={onClose}
              className="font-mono text-sm text-gray-500 hover:text-gray-800"
            >
              Close
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="border-b border-red-200 bg-red-50 px-6 py-2">
            <p className="font-mono text-xs text-red-700">{error}</p>
          </div>
        )}

        {/* Status actions */}
        <div className="flex gap-2 border-b border-warm-border px-6 py-3">
          {STATUS_OPTIONS.filter((s) => s.value !== node.status).map((s) => (
            <button
              key={s.value}
              onClick={() => handleStatusChange(s.value)}
              disabled={saving}
              className={`rounded px-3 py-1 font-mono text-xs transition-colors ${s.color} hover:opacity-80 disabled:opacity-40`}
            >
              {s.value === 'approved' ? 'Approve' : s.value === 'archived' ? 'Archive' : s.value === 'flagged' ? 'Flag' : 'Set Pending'}
            </button>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex gap-4 border-b border-warm-border px-6">
          {(['details', 'aliases', 'signals'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`border-b-2 px-1 py-2 font-mono text-sm capitalize transition-colors ${
                activeTab === tab
                  ? 'border-terracotta text-terracotta'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
              {tab === 'aliases' && node.aliases.length > 0 && (
                <span className="ml-1 text-xs text-gray-400">({node.aliases.length})</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="max-h-[60vh] overflow-y-auto px-6 py-4">
          {activeTab === 'details' && (
            <div className="grid grid-cols-2 gap-4">
              <FieldInput label="Name" value={val('name')} onChange={(v) => setField('name', v)} />
              <FieldInput label="Canonical Name" value={val('canonicalName')} onChange={(v) => setField('canonicalName', v)} />
              <FieldSelect label="Category" value={val('category')} options={CATEGORY_OPTIONS} onChange={(v) => setField('category', v)} />
              <FieldInput label="Subcategory" value={val('subcategory')} onChange={(v) => setField('subcategory', v)} />
              <FieldInput label="Neighborhood" value={val('neighborhood')} onChange={(v) => setField('neighborhood', v)} />
              <FieldInput label="Address" value={val('address')} onChange={(v) => setField('address', v)} />
              <FieldInput label="Phone" value={val('phoneNumber')} onChange={(v) => setField('phoneNumber', v)} />
              <FieldInput label="Website" value={val('websiteUrl')} onChange={(v) => setField('websiteUrl', v)} />
              <FieldInput label="Price Level" value={String(val('priceLevel') ?? '')} onChange={(v) => setField('priceLevel', v ? parseInt(v, 10) : null)} />
              <FieldInput label="Flag Reason" value={val('flagReason')} onChange={(v) => setField('flagReason', v || null)} />
              <div className="col-span-2">
                <FieldTextarea label="Short Description" value={val('descriptionShort')} onChange={(v) => setField('descriptionShort', v)} />
              </div>
              <div className="col-span-2">
                <FieldTextarea label="Long Description" value={val('descriptionLong')} onChange={(v) => setField('descriptionLong', v)} />
              </div>

              {/* Read-only metadata */}
              <div className="col-span-2 mt-2 grid grid-cols-3 gap-2 rounded border border-warm-border bg-warm-background p-3">
                <ReadonlyField label="Convergence" value={node.convergenceScore?.toFixed(3) ?? 'n/a'} />
                <ReadonlyField label="Sources" value={String(node.sourceCount)} />
                <ReadonlyField label="Canonical" value={node.isCanonical ? 'Yes' : 'No'} />
                <ReadonlyField label="Lat" value={String(node.latitude)} />
                <ReadonlyField label="Lng" value={String(node.longitude)} />
                <ReadonlyField label="Last Scraped" value={node.lastScrapedAt ?? 'never'} />
              </div>
            </div>
          )}

          {activeTab === 'aliases' && (
            <div>
              {/* Add alias */}
              <div className="mb-4 flex gap-2">
                <input
                  type="text"
                  value={newAlias}
                  onChange={(e) => setNewAlias(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddAlias()}
                  placeholder="Add alias..."
                  className="flex-1 rounded border border-warm-border bg-warm-background px-3 py-1.5 font-mono text-sm focus:border-terracotta focus:outline-none"
                />
                <button
                  onClick={handleAddAlias}
                  disabled={!newAlias.trim()}
                  className="rounded bg-terracotta px-3 py-1.5 font-mono text-sm text-white hover:opacity-90 disabled:opacity-40"
                >
                  Add
                </button>
              </div>

              {/* Alias list */}
              {node.aliases.length === 0 ? (
                <p className="font-mono text-sm text-gray-400">No aliases</p>
              ) : (
                <ul className="space-y-1">
                  {node.aliases.map((a) => (
                    <li key={a.id} className="flex items-center justify-between rounded border border-warm-border px-3 py-2">
                      <div>
                        <span className="font-mono text-sm text-gray-900">{a.alias}</span>
                        <span className="ml-2 font-mono text-xs text-gray-400">({a.source})</span>
                      </div>
                      <button
                        onClick={() => handleRemoveAlias(a.id)}
                        className="font-mono text-xs text-red-500 hover:text-red-700"
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {activeTab === 'signals' && (
            <div className="space-y-4">
              {/* Vibe tags */}
              {node.vibeTags.length > 0 && (
                <div>
                  <h4 className="mb-2 font-mono text-xs font-semibold uppercase text-gray-500">Vibe Tags</h4>
                  <div className="flex flex-wrap gap-1">
                    {node.vibeTags.map((vt) => (
                      <span key={vt.id} className="rounded bg-warm-background px-2 py-0.5 font-mono text-xs text-gray-700">
                        {vt.tagName} ({vt.score.toFixed(2)})
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Quality signals */}
              <div>
                <h4 className="mb-2 font-mono text-xs font-semibold uppercase text-gray-500">Quality Signals</h4>
                {node.qualitySignals.length === 0 ? (
                  <p className="font-mono text-sm text-gray-400">No signals</p>
                ) : (
                  <table className="w-full font-mono text-xs">
                    <thead>
                      <tr className="border-b border-warm-border text-left text-gray-500">
                        <th className="py-1">Source</th>
                        <th className="py-1">Authority</th>
                        <th className="py-1">Type</th>
                        <th className="py-1">Extracted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {node.qualitySignals.map((qs) => (
                        <tr key={qs.id} className="border-b border-warm-border/50">
                          <td className="py-1 text-gray-900">{qs.sourceName}</td>
                          <td className="py-1 text-gray-600">{qs.sourceAuthority.toFixed(2)}</td>
                          <td className="py-1 text-gray-600">{qs.signalType}</td>
                          <td className="py-1 text-gray-400">{new Date(qs.extractedAt).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between border-t border-warm-border px-6 py-3">
          <p className="font-mono text-xs text-gray-400">
            Updated {new Date(node.updatedAt).toLocaleString()}
          </p>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded border border-warm-border px-4 py-1.5 font-mono text-sm text-gray-600 hover:bg-warm-background"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              className="rounded bg-terracotta px-4 py-1.5 font-mono text-sm text-white hover:opacity-90 disabled:opacity-40"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

function FieldInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="font-mono text-xs text-gray-500">{label}</span>
      <input
        type="text"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 block w-full rounded border border-warm-border bg-warm-background px-2 py-1 font-mono text-sm focus:border-terracotta focus:outline-none"
      />
    </label>
  );
}

function FieldTextarea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="font-mono text-xs text-gray-500">{label}</span>
      <textarea
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="mt-0.5 block w-full rounded border border-warm-border bg-warm-background px-2 py-1 font-mono text-sm focus:border-terracotta focus:outline-none"
      />
    </label>
  );
}

function FieldSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="font-mono text-xs text-gray-500">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 block w-full rounded border border-warm-border bg-warm-background px-2 py-1 font-mono text-sm focus:border-terracotta focus:outline-none"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}

function ReadonlyField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-mono text-xs text-gray-400">{label}</span>
      <p className="font-mono text-sm text-gray-700">{value}</p>
    </div>
  );
}
