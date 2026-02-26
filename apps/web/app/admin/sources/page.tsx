'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SourceSummary {
  source_name: string;
  signal_count: number;
  node_count: number;
  avg_authority: number;
  min_authority: number;
  max_authority: number;
  last_scraped_at: string | null;
  oldest_signal_at: string | null;
  is_stale: boolean;
  staleness_hours: number | null;
}

interface StaleAlert {
  source_name: string;
  last_scraped_at: string | null;
  threshold_hours: number;
  hours_since_scrape: number | null;
  signal_count: number;
}

interface StalenessConfig {
  default_threshold_hours: number;
  per_source: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';
const POLL_INTERVAL_MS = 30_000;

const FRESHNESS_COLORS: Record<string, string> = {
  fresh: 'bg-green-100 text-green-800',
  aging: 'bg-yellow-100 text-yellow-800',
  stale: 'bg-red-100 text-error',
  unknown: 'bg-ink-800 text-ink-500',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function freshnessLabel(staleness_hours: number | null, is_stale: boolean): string {
  if (staleness_hours === null) return 'unknown';
  if (is_stale) return 'stale';
  if (staleness_hours > 48) return 'aging';
  return 'fresh';
}

function formatHours(hours: number | null): string {
  if (hours === null) return 'Never';
  if (hours < 1) return '<1h ago';
  if (hours < 24) return `${Math.round(hours)}h ago`;
  const days = Math.floor(hours / 24);
  const rem = Math.round(hours % 24);
  return `${days}d ${rem}h ago`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AdminSourcesPage() {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [alerts, setAlerts] = useState<StaleAlert[]>([]);
  const [config, setConfig] = useState<StalenessConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Authority edit state
  const [editingSource, setEditingSource] = useState<string | null>(null);
  const [editAuthority, setEditAuthority] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Config edit state
  const [editingConfig, setEditingConfig] = useState(false);
  const [configDraft, setConfigDraft] = useState('72');
  const [perSourceDraft, setPerSourceDraft] = useState('');
  const [configSaving, setConfigSaving] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ------ Fetchers ------

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/sources`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSources(data.sources ?? []);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    }
  }, []);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/sources/alerts`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlerts(data.alerts ?? []);
    } catch {
      // Alerts are supplementary; don't block on failure
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/sources/config`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: StalenessConfig = await res.json();
      setConfig(data);
      setConfigDraft(String(data.default_threshold_hours));
      setPerSourceDraft(
        Object.entries(data.per_source)
          .map(([k, v]) => `${k}=${v}`)
          .join('\n')
      );
    } catch {
      // Config fetch failure not critical
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchSources(), fetchAlerts(), fetchConfig()]);
    setLoading(false);
  }, [fetchSources, fetchAlerts, fetchConfig]);

  // ------ Polling ------

  useEffect(() => {
    fetchAll();
    pollRef.current = setInterval(() => {
      fetchSources();
      fetchAlerts();
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchAll, fetchSources, fetchAlerts]);

  // ------ Authority update ------

  const startEditAuthority = (source: SourceSummary) => {
    setEditingSource(source.source_name);
    setEditAuthority(source.avg_authority.toFixed(3));
    setSaveError(null);
  };

  const saveAuthority = async () => {
    if (!editingSource) return;
    const value = parseFloat(editAuthority);
    if (isNaN(value) || value < 0 || value > 1) {
      setSaveError('Authority must be between 0.0 and 1.0');
      return;
    }

    setSaving(true);
    setSaveError(null);

    try {
      const res = await fetch(
        `${API_BASE}/admin/sources/${encodeURIComponent(editingSource)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ authority_score: value }),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditingSource(null);
      fetchSources();
    } catch (err: any) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ------ Config update ------

  const saveConfig = async () => {
    const defaultHours = parseInt(configDraft, 10);
    if (isNaN(defaultHours) || defaultHours < 1) {
      setConfigError('Default threshold must be a positive integer');
      return;
    }

    // Parse per-source overrides (format: "source_name=hours" per line)
    const perSource: Record<string, number> = {};
    if (perSourceDraft.trim()) {
      for (const line of perSourceDraft.trim().split('\n')) {
        const parts = line.trim().split('=');
        if (parts.length !== 2) {
          setConfigError(`Invalid format: "${line.trim()}". Use: source_name=hours`);
          return;
        }
        const hours = parseInt(parts[1], 10);
        if (isNaN(hours) || hours < 1) {
          setConfigError(`Invalid hours for ${parts[0]}: ${parts[1]}`);
          return;
        }
        perSource[parts[0].trim()] = hours;
      }
    }

    setConfigSaving(true);
    setConfigError(null);

    try {
      const res = await fetch(`${API_BASE}/admin/sources/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          default_threshold_hours: defaultHours,
          per_source: perSource,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditingConfig(false);
      fetchAll();
    } catch (err: any) {
      setConfigError(err.message);
    } finally {
      setConfigSaving(false);
    }
  };

  // ------ Derived ------

  const staleCount = sources.filter((s) => s.is_stale).length;
  const totalSignals = sources.reduce((sum, s) => sum + s.signal_count, 0);

  // ------ Render ------

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl text-ink-100">
            Source Freshness
          </h2>
          <p className="mt-1 font-dm-mono text-sm text-ink-500">
            Monitor scraper health, data freshness, and authority scores
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-dm-mono text-sm text-ink-500">
            {sources.length} source{sources.length !== 1 ? 's' : ''}
          </span>
          {staleCount > 0 && (
            <span className="rounded bg-red-100 px-2.5 py-1 font-dm-mono text-xs text-error">
              {staleCount} stale
            </span>
          )}
        </div>
      </div>

      {/* Alerts banner */}
      {alerts.length > 0 && (
        <div className="rounded-lg border border-error/30 bg-error-bg p-4">
          <h3 className="font-display text-sm text-error mb-2">
            Stale Source Alerts
          </h3>
          <div className="space-y-1">
            {alerts.map((alert) => (
              <div
                key={alert.source_name}
                className="flex items-center justify-between font-dm-mono text-xs"
              >
                <span className="text-error font-medium">
                  {alert.source_name}
                </span>
                <span className="text-error">
                  {alert.hours_since_scrape !== null
                    ? `${Math.round(alert.hours_since_scrape)}h since last scrape (threshold: ${alert.threshold_hours}h)`
                    : `Never scraped (threshold: ${alert.threshold_hours}h)`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-ink-700 bg-surface p-4">
          <p className="font-dm-mono text-xs text-ink-500">Total Sources</p>
          <p className="font-display text-2xl text-ink-100 mt-1">
            {sources.length}
          </p>
        </div>
        <div className="rounded-lg border border-ink-700 bg-surface p-4">
          <p className="font-dm-mono text-xs text-ink-500">Total Signals</p>
          <p className="font-display text-2xl text-ink-100 mt-1">
            {totalSignals.toLocaleString()}
          </p>
        </div>
        <div className="rounded-lg border border-ink-700 bg-surface p-4">
          <p className="font-dm-mono text-xs text-ink-500">Healthy</p>
          <p className="font-display text-2xl text-green-700 mt-1">
            {sources.length - staleCount}
          </p>
        </div>
        <div className="rounded-lg border border-ink-700 bg-surface p-4">
          <p className="font-dm-mono text-xs text-ink-500">Stale</p>
          <p className={`font-display text-2xl mt-1 ${staleCount > 0 ? 'text-error' : 'text-ink-100'}`}>
            {staleCount}
          </p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded border border-error/30 bg-error-bg px-4 py-2">
          <p className="font-dm-mono text-sm text-error">{error}</p>
        </div>
      )}

      {/* Source table */}
      <div className="overflow-x-auto rounded border border-ink-700">
        <table className="w-full font-dm-mono text-sm">
          <thead>
            <tr className="border-b border-ink-700 bg-base text-left text-xs text-ink-500">
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Last Scraped</th>
              <th className="px-3 py-2">Signals</th>
              <th className="px-3 py-2">Nodes</th>
              <th className="px-3 py-2">Authority (avg)</th>
              <th className="px-3 py-2">Authority (range)</th>
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
            ) : sources.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-ink-600">
                  No sources found. Run the data pipeline to populate.
                </td>
              </tr>
            ) : (
              sources.map((source) => {
                const status = freshnessLabel(
                  source.staleness_hours,
                  source.is_stale
                );
                return (
                  <tr
                    key={source.source_name}
                    className={`border-b border-ink-700/50 transition-colors ${
                      source.is_stale
                        ? 'bg-error-bg/30 hover:bg-error-bg/50'
                        : 'hover:bg-base/50'
                    }`}
                  >
                    <td className="px-3 py-2 font-medium text-ink-100">
                      {source.source_name}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs ${FRESHNESS_COLORS[status]}`}
                      >
                        {status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-500">
                      <span title={formatDate(source.last_scraped_at)}>
                        {formatHours(source.staleness_hours)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-500">
                      {source.signal_count.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-ink-500">
                      {source.node_count.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-ink-500">
                      {source.avg_authority.toFixed(3)}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-600">
                      {source.min_authority.toFixed(2)} - {source.max_authority.toFixed(2)}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => startEditAuthority(source)}
                        className="text-xs text-accent hover:underline"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Authority editor modal */}
      {editingSource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-lg border border-ink-700 bg-white p-6 shadow-xl">
            <h3 className="font-display text-lg text-ink-100 mb-4">
              Edit Authority: {editingSource}
            </h3>
            <p className="font-dm-mono text-xs text-ink-500 mb-3">
              This will update the authority score for ALL quality signals from
              this source. The change is audit-logged.
            </p>
            <div className="mb-4">
              <label
                htmlFor="authority-input"
                className="block font-dm-mono text-xs text-ink-500 mb-1"
              >
                Authority Score (0.0 - 1.0)
              </label>
              <input
                id="authority-input"
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={editAuthority}
                onChange={(e) => setEditAuthority(e.target.value)}
                className="w-full rounded border border-ink-700 bg-white px-3 py-2 font-dm-mono text-sm text-ink-100 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            {saveError && (
              <p className="mb-3 font-dm-mono text-xs text-error">{saveError}</p>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={saveAuthority}
                disabled={saving}
                className="rounded bg-accent px-4 py-2 font-dm-mono text-sm text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setEditingSource(null)}
                className="font-dm-mono text-sm text-ink-500 hover:text-ink-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Staleness config section */}
      <section className="rounded-lg border border-ink-700 bg-surface p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-display text-lg text-ink-100">
              Staleness Thresholds
            </h3>
            <p className="font-dm-mono text-xs text-ink-500 mt-1">
              Configure when a source is considered stale. Changes are audit-logged.
            </p>
          </div>
          {!editingConfig && (
            <button
              onClick={() => setEditingConfig(true)}
              className="rounded border border-ink-700 px-3 py-1.5 font-dm-mono text-xs text-ink-500 hover:bg-base transition-colors"
            >
              Edit
            </button>
          )}
        </div>

        {!editingConfig ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="font-dm-mono text-xs text-ink-500">Default threshold:</span>
              <span className="font-dm-mono text-sm text-ink-100">
                {config?.default_threshold_hours ?? 72}h
              </span>
            </div>
            {config?.per_source && Object.keys(config.per_source).length > 0 && (
              <div>
                <span className="font-dm-mono text-xs text-ink-500 block mb-1">
                  Per-source overrides:
                </span>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(config.per_source).map(([name, hours]) => (
                    <span
                      key={name}
                      className="rounded bg-base px-2 py-0.5 font-dm-mono text-xs text-ink-300"
                    >
                      {name}: {hours}h
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label
                htmlFor="config-default"
                className="block font-dm-mono text-xs text-ink-500 mb-1"
              >
                Default threshold (hours)
              </label>
              <input
                id="config-default"
                type="number"
                min="1"
                value={configDraft}
                onChange={(e) => setConfigDraft(e.target.value)}
                className="w-32 rounded border border-ink-700 bg-white px-3 py-2 font-dm-mono text-sm text-ink-100 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label
                htmlFor="config-per-source"
                className="block font-dm-mono text-xs text-ink-500 mb-1"
              >
                Per-source overrides (one per line: source_name=hours)
              </label>
              <textarea
                id="config-per-source"
                rows={4}
                value={perSourceDraft}
                onChange={(e) => setPerSourceDraft(e.target.value)}
                placeholder={'reddit=168\natlas_obscura=72'}
                className="w-full rounded border border-ink-700 bg-white px-3 py-2 font-dm-mono text-xs text-ink-100 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            {configError && (
              <p className="font-dm-mono text-xs text-error">{configError}</p>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={saveConfig}
                disabled={configSaving}
                className="rounded bg-accent px-4 py-2 font-dm-mono text-sm text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
              >
                {configSaving ? 'Saving...' : 'Save Config'}
              </button>
              <button
                onClick={() => {
                  setEditingConfig(false);
                  setConfigError(null);
                }}
                className="font-dm-mono text-sm text-ink-500 hover:text-ink-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Polling indicator */}
      <p className="font-dm-mono text-[10px] text-ink-700 text-right">
        Auto-refreshing every {POLL_INTERVAL_MS / 1000}s
      </p>
    </div>
  );
}
