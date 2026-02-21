'use client';

import { useState, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LLMCostRow {
  model: string;
  date: string;
  pipeline_stage: string;
  call_count: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

interface LLMCostSummary {
  rows: LLMCostRow[];
  total_cost_usd: number;
  total_calls: number;
  period_start: string;
  period_end: string;
}

interface APICallRow {
  provider: string;
  date: string;
  call_count: number;
  error_count: number;
  avg_latency_ms: number;
}

interface APICallSummary {
  rows: APICallRow[];
  total_calls: number;
  total_errors: number;
  period_start: string;
  period_end: string;
}

interface PipelineJobRow {
  job_id: string;
  job_type: string;
  city: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  items_processed: number;
  items_failed: number;
  error: string | null;
}

interface PipelineJobSummary {
  jobs: PipelineJobRow[];
  total_jobs: number;
  success_count: number;
  failure_count: number;
  running_count: number;
  success_rate: number;
}

interface CostAlertStatus {
  pipeline_stage: string;
  daily_limit_usd: number;
  current_spend_usd: number;
  enabled: boolean;
  exceeded: boolean;
  pct_used: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

const DAYS_OPTIONS = [
  { value: 1, label: '24h' },
  { value: 7, label: '7d' },
  { value: 14, label: '14d' },
  { value: 30, label: '30d' },
];

const JOB_STATUS_COLORS: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-error',
  running: 'bg-blue-100 text-blue-800',
  pending: 'bg-yellow-100 text-yellow-800',
};

const PROVIDER_LABELS: Record<string, string> = {
  foursquare: 'Foursquare',
  google: 'Google Places',
  openweathermap: 'OpenWeatherMap',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatUSD(val: number): string {
  return `$${val.toFixed(2)}`;
}

function formatNumber(val: number): string {
  return val.toLocaleString();
}

function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function pctBar(pct: number): string {
  if (pct >= 100) return 'bg-error-bg0';
  if (pct >= 80) return 'bg-yellow-500';
  return 'bg-accent';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-ink-700 bg-surface p-4">
      <span className="block font-mono text-xs text-ink-500">{label}</span>
      <span className="block font-display text-2xl font-semibold text-ink-100 mt-1">
        {value}
      </span>
      {sub && (
        <span className="block font-mono text-xs text-ink-600 mt-0.5">
          {sub}
        </span>
      )}
    </div>
  );
}

function SectionHeader({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h3 className="font-display text-lg font-semibold text-ink-100">
        {title}
      </h3>
      {children}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-error/30 bg-error-bg p-3 font-mono text-sm text-error">
      {message}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-surface p-8 text-center">
      <p className="font-mono text-sm text-ink-600">{message}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function PipelineHealthPage() {
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  // Data state
  const [llmCosts, setLlmCosts] = useState<LLMCostSummary | null>(null);
  const [apiCalls, setApiCalls] = useState<APICallSummary | null>(null);
  const [jobs, setJobs] = useState<PipelineJobSummary | null>(null);
  const [alerts, setAlerts] = useState<CostAlertStatus[]>([]);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Alert editing
  const [editingAlerts, setEditingAlerts] = useState(false);
  const [alertDrafts, setAlertDrafts] = useState<
    { pipeline_stage: string; daily_limit_usd: number; enabled: boolean }[]
  >([]);
  const [alertSaving, setAlertSaving] = useState(false);

  // ------ Fetchers ------

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [costsRes, callsRes, jobsRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/admin/pipeline/llm-costs?days=${days}`, {
          credentials: 'include',
        }),
        fetch(`${API_BASE}/admin/pipeline/api-calls?days=${days}`, {
          credentials: 'include',
        }),
        fetch(`${API_BASE}/admin/pipeline/jobs?limit=50`, {
          credentials: 'include',
        }),
        fetch(`${API_BASE}/admin/pipeline/alerts`, {
          credentials: 'include',
        }),
      ]);

      if (!costsRes.ok) throw new Error(`LLM costs: ${costsRes.status}`);
      if (!callsRes.ok) throw new Error(`API calls: ${callsRes.status}`);
      if (!jobsRes.ok) throw new Error(`Jobs: ${jobsRes.status}`);
      if (!alertsRes.ok) throw new Error(`Alerts: ${alertsRes.status}`);

      const [costsJson, callsJson, jobsJson, alertsJson] = await Promise.all([
        costsRes.json(),
        callsRes.json(),
        jobsRes.json(),
        alertsRes.json(),
      ]);

      setLlmCosts(costsJson.data);
      setApiCalls(callsJson.data);
      setJobs(jobsJson.data);
      setAlerts(alertsJson.data);
    } catch (err: any) {
      setError(err.message ?? 'Failed to load pipeline data');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ------ Alert Editing ------

  function startEditingAlerts() {
    setAlertDrafts(
      alerts.map((a) => ({
        pipeline_stage: a.pipeline_stage,
        daily_limit_usd: a.daily_limit_usd,
        enabled: a.enabled,
      }))
    );
    setEditingAlerts(true);
  }

  async function saveAlerts() {
    setAlertSaving(true);
    try {
      const res = await fetch(`${API_BASE}/admin/pipeline/alerts`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ thresholds: alertDrafts }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEditingAlerts(false);
      fetchAll();
    } catch (err: any) {
      setError(err.message ?? 'Failed to save alerts');
    } finally {
      setAlertSaving(false);
    }
  }

  // ------ Aggregation Helpers ------

  function groupLLMByModel(
    rows: LLMCostRow[]
  ): Record<string, { calls: number; cost: number; avgLatency: number }> {
    const groups: Record<
      string,
      { calls: number; cost: number; latencySum: number }
    > = {};
    for (const r of rows) {
      if (!groups[r.model])
        groups[r.model] = { calls: 0, cost: 0, latencySum: 0 };
      groups[r.model].calls += r.call_count;
      groups[r.model].cost += r.total_cost_usd;
      groups[r.model].latencySum += r.avg_latency_ms * r.call_count;
    }
    const result: Record<
      string,
      { calls: number; cost: number; avgLatency: number }
    > = {};
    for (const [k, v] of Object.entries(groups)) {
      result[k] = {
        calls: v.calls,
        cost: v.cost,
        avgLatency: v.calls > 0 ? v.latencySum / v.calls : 0,
      };
    }
    return result;
  }

  function groupAPIByProvider(
    rows: APICallRow[]
  ): Record<string, { calls: number; errors: number; avgLatency: number }> {
    const groups: Record<
      string,
      { calls: number; errors: number; latencySum: number }
    > = {};
    for (const r of rows) {
      if (!groups[r.provider])
        groups[r.provider] = { calls: 0, errors: 0, latencySum: 0 };
      groups[r.provider].calls += r.call_count;
      groups[r.provider].errors += r.error_count;
      groups[r.provider].latencySum += r.avg_latency_ms * r.call_count;
    }
    const result: Record<
      string,
      { calls: number; errors: number; avgLatency: number }
    > = {};
    for (const [k, v] of Object.entries(groups)) {
      result[k] = {
        calls: v.calls,
        errors: v.errors,
        avgLatency: v.calls > 0 ? v.latencySum / v.calls : 0,
      };
    }
    return result;
  }

  // ------ Render ------

  const exceededAlerts = alerts.filter((a) => a.exceeded);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-semibold text-ink-100">
            Pipeline Health
          </h2>
          <p className="mt-1 font-mono text-sm text-ink-500">
            LLM costs, API usage, job health, and cost alerts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-mono text-sm text-ink-300"
          >
            {DAYS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            onClick={fetchAll}
            disabled={loading}
            className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-mono text-sm text-ink-500 transition-colors hover:bg-ink-800 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Global error */}
      {error && <ErrorBanner message={error} />}

      {/* Cost alert warnings */}
      {exceededAlerts.length > 0 && (
        <div className="rounded-md border border-error/50 bg-error-bg p-4">
          <p className="font-display text-sm font-semibold text-error mb-2">
            Cost Alerts Exceeded
          </p>
          <div className="space-y-1">
            {exceededAlerts.map((a) => (
              <p key={a.pipeline_stage} className="font-mono text-xs text-error">
                {a.pipeline_stage}: {formatUSD(a.current_spend_usd)} /{' '}
                {formatUSD(a.daily_limit_usd)} daily limit ({a.pct_used}%)
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && !llmCosts && (
        <div className="py-12 text-center font-mono text-sm text-ink-600">
          Loading pipeline data...
        </div>
      )}

      {/* ================================================================ */}
      {/* LLM Costs Section                                                */}
      {/* ================================================================ */}
      {llmCosts && (
        <section>
          <SectionHeader title="LLM Costs" />

          {/* Summary cards */}
          <div className="grid grid-cols-2 gap-4 mb-4 sm:grid-cols-4">
            <StatCard
              label="Total Cost"
              value={formatUSD(llmCosts.total_cost_usd)}
              sub={`${llmCosts.period_start} - ${llmCosts.period_end}`}
            />
            <StatCard
              label="Total Calls"
              value={formatNumber(llmCosts.total_calls)}
            />
            {(() => {
              const byModel = groupLLMByModel(llmCosts.rows);
              const models = Object.keys(byModel);
              return (
                <>
                  <StatCard label="Models Used" value={String(models.length)} />
                  <StatCard
                    label="Avg Cost/Call"
                    value={
                      llmCosts.total_calls > 0
                        ? formatUSD(
                            llmCosts.total_cost_usd / llmCosts.total_calls
                          )
                        : '$0.00'
                    }
                  />
                </>
              );
            })()}
          </div>

          {/* Cost by model */}
          {llmCosts.rows.length > 0 ? (
            <div className="rounded-lg border border-ink-700 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ink-700 bg-base">
                    <th className="px-4 py-2 text-left font-mono text-xs text-ink-500">
                      Model
                    </th>
                    <th className="px-4 py-2 text-left font-mono text-xs text-ink-500">
                      Stage
                    </th>
                    <th className="px-4 py-2 text-left font-mono text-xs text-ink-500">
                      Date
                    </th>
                    <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                      Calls
                    </th>
                    <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                      Cost
                    </th>
                    <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                      Avg Latency
                    </th>
                    <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                      Tokens (in/out)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {llmCosts.rows.map((row, i) => (
                    <tr
                      key={`${row.model}-${row.date}-${row.pipeline_stage}`}
                      className={
                        i % 2 === 0 ? 'bg-surface' : 'bg-base/30'
                      }
                    >
                      <td className="px-4 py-2 font-mono text-sm text-ink-200">
                        {row.model}
                      </td>
                      <td className="px-4 py-2">
                        <span className="rounded-full bg-ink-800 px-2 py-0.5 font-mono text-xs text-ink-500">
                          {row.pipeline_stage}
                        </span>
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-ink-500">
                        {row.date}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-sm text-ink-300">
                        {formatNumber(row.call_count)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-sm font-medium text-ink-100">
                        {formatUSD(row.total_cost_usd)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                        {formatLatency(row.avg_latency_ms)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                        {formatNumber(row.total_input_tokens)} /{' '}
                        {formatNumber(row.total_output_tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="No LLM calls recorded in this period." />
          )}
        </section>
      )}

      {/* ================================================================ */}
      {/* API Calls Section                                                */}
      {/* ================================================================ */}
      {apiCalls && (
        <section>
          <SectionHeader title="External API Calls" />

          {/* Provider summary cards */}
          {(() => {
            const byProvider = groupAPIByProvider(apiCalls.rows);
            const providers = Object.entries(byProvider);
            if (providers.length === 0)
              return (
                <EmptyState message="No external API calls recorded in this period." />
              );

            return (
              <>
                <div className="grid grid-cols-3 gap-4 mb-4">
                  {providers.map(([provider, stats]) => (
                    <div
                      key={provider}
                      className="rounded-lg border border-ink-700 bg-surface p-4"
                    >
                      <span className="block font-mono text-xs text-ink-500">
                        {PROVIDER_LABELS[provider] ?? provider}
                      </span>
                      <span className="block font-display text-xl font-semibold text-ink-100 mt-1">
                        {formatNumber(stats.calls)}
                      </span>
                      <div className="flex items-center gap-3 mt-1 font-mono text-xs">
                        <span
                          className={
                            stats.errors > 0 ? 'text-error' : 'text-ink-600'
                          }
                        >
                          {stats.errors} errors
                        </span>
                        <span className="text-ink-600">
                          {formatLatency(stats.avgLatency)} avg
                        </span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Daily breakdown table */}
                <div className="rounded-lg border border-ink-700 overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-ink-700 bg-base">
                        <th className="px-4 py-2 text-left font-mono text-xs text-ink-500">
                          Provider
                        </th>
                        <th className="px-4 py-2 text-left font-mono text-xs text-ink-500">
                          Date
                        </th>
                        <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                          Calls
                        </th>
                        <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                          Errors
                        </th>
                        <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                          Error Rate
                        </th>
                        <th className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                          Avg Latency
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {apiCalls.rows.map((row, i) => (
                        <tr
                          key={`${row.provider}-${row.date}`}
                          className={
                            i % 2 === 0
                              ? 'bg-surface'
                              : 'bg-base/30'
                          }
                        >
                          <td className="px-4 py-2 font-mono text-sm text-ink-200">
                            {PROVIDER_LABELS[row.provider] ?? row.provider}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-ink-500">
                            {row.date}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-sm text-ink-300">
                            {formatNumber(row.call_count)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-sm text-error">
                            {row.error_count > 0 ? row.error_count : '-'}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                            {row.call_count > 0
                              ? `${((row.error_count / row.call_count) * 100).toFixed(1)}%`
                              : '-'}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs text-ink-500">
                            {formatLatency(row.avg_latency_ms)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            );
          })()}
        </section>
      )}

      {/* ================================================================ */}
      {/* Pipeline Jobs Section                                            */}
      {/* ================================================================ */}
      {jobs && (
        <section>
          <SectionHeader title="Pipeline Jobs" />

          {/* Stats row */}
          <div className="grid grid-cols-2 gap-4 mb-4 sm:grid-cols-5">
            <StatCard label="Total (30d)" value={String(jobs.total_jobs)} />
            <StatCard label="Succeeded" value={String(jobs.success_count)} />
            <StatCard label="Failed" value={String(jobs.failure_count)} />
            <StatCard label="Running" value={String(jobs.running_count)} />
            <StatCard
              label="Success Rate"
              value={`${(jobs.success_rate * 100).toFixed(1)}%`}
            />
          </div>

          {/* Job list */}
          {jobs.jobs.length > 0 ? (
            <div className="space-y-2">
              {jobs.jobs.map((job) => (
                <div
                  key={job.job_id}
                  className="flex items-center gap-4 rounded-lg border border-ink-700 bg-surface px-4 py-3"
                >
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-xs ${
                      JOB_STATUS_COLORS[job.status] ?? 'bg-ink-800 text-ink-500'
                    }`}
                  >
                    {job.status}
                  </span>

                  <span className="font-mono text-sm text-ink-200">
                    {job.job_type}
                  </span>

                  {job.city && (
                    <span className="font-mono text-xs text-ink-500">
                      {job.city}
                    </span>
                  )}

                  <div className="ml-auto flex items-center gap-4">
                    <span className="font-mono text-xs text-ink-500">
                      {job.items_processed} processed
                      {job.items_failed > 0 && (
                        <span className="text-error">
                          {' '}/ {job.items_failed} failed
                        </span>
                      )}
                    </span>

                    <span className="font-mono text-xs text-ink-600">
                      {formatDuration(job.duration_seconds)}
                    </span>

                    <span className="font-mono text-[10px] text-ink-700">
                      {job.job_id.slice(0, 8)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState message="No pipeline jobs recorded." />
          )}
        </section>
      )}

      {/* ================================================================ */}
      {/* Cost Alerts Section                                              */}
      {/* ================================================================ */}
      <section>
        <SectionHeader title="Cost Alerts">
          {!editingAlerts && alerts.length > 0 && (
            <button
              onClick={startEditingAlerts}
              className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-mono text-sm text-ink-500 transition-colors hover:bg-ink-800"
            >
              Edit Thresholds
            </button>
          )}
        </SectionHeader>

        {alerts.length === 0 && !editingAlerts && (
          <EmptyState message="No cost alert thresholds configured." />
        )}

        {!editingAlerts && alerts.length > 0 && (
          <div className="space-y-3">
            {alerts.map((a) => (
              <div
                key={a.pipeline_stage}
                className={`rounded-lg border p-4 ${
                  a.exceeded
                    ? 'border-error/50 bg-error-bg'
                    : 'border-ink-700 bg-surface'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium text-ink-200">
                      {a.pipeline_stage}
                    </span>
                    {!a.enabled && (
                      <span className="rounded-full bg-ink-800 px-2 py-0.5 font-mono text-[10px] text-ink-500">
                        disabled
                      </span>
                    )}
                    {a.exceeded && (
                      <span className="rounded-full bg-red-200 px-2 py-0.5 font-mono text-[10px] text-error">
                        exceeded
                      </span>
                    )}
                  </div>
                  <span className="font-mono text-sm text-ink-500">
                    {formatUSD(a.current_spend_usd)} /{' '}
                    {formatUSD(a.daily_limit_usd)}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="h-2 w-full rounded-full bg-ink-800">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${pctBar(a.pct_used)}`}
                    style={{ width: `${Math.min(a.pct_used, 100)}%` }}
                  />
                </div>
                <span className="block mt-1 font-mono text-[10px] text-ink-600 text-right">
                  {a.pct_used.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Editing mode */}
        {editingAlerts && (
          <div className="rounded-lg border border-ink-700 bg-surface p-4 space-y-4">
            {alertDrafts.map((draft, idx) => (
              <div
                key={draft.pipeline_stage}
                className="flex items-center gap-4"
              >
                <span className="font-mono text-sm text-ink-200 w-40">
                  {draft.pipeline_stage}
                </span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-ink-500">$</span>
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    value={draft.daily_limit_usd}
                    onChange={(e) => {
                      const next = [...alertDrafts];
                      next[idx] = {
                        ...next[idx],
                        daily_limit_usd: parseFloat(e.target.value) || 0,
                      };
                      setAlertDrafts(next);
                    }}
                    className="w-24 rounded border border-ink-700 bg-white px-2 py-1 font-mono text-sm text-ink-100 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <span className="font-mono text-xs text-ink-500">
                    /day
                  </span>
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(e) => {
                      const next = [...alertDrafts];
                      next[idx] = { ...next[idx], enabled: e.target.checked };
                      setAlertDrafts(next);
                    }}
                    className="h-4 w-4 rounded border-ink-700 text-accent focus:ring-accent"
                  />
                  <span className="font-mono text-xs text-ink-500">
                    Enabled
                  </span>
                </label>
              </div>
            ))}

            <div className="flex items-center gap-3 pt-3 border-t border-ink-700">
              <button
                onClick={saveAlerts}
                disabled={alertSaving}
                className="rounded bg-accent px-4 py-2 font-mono text-sm text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
              >
                {alertSaving ? 'Saving...' : 'Save Thresholds'}
              </button>
              <button
                onClick={() => setEditingAlerts(false)}
                className="font-mono text-sm text-ink-500 hover:text-ink-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
