'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StepStatus {
  status: 'completed' | 'in_progress' | 'failed' | 'pending';
  duration_s: number | null;
  error: string | null;
}

interface CategoryEntry {
  name: string;
  count: number;
  pct: number;
}

interface CityData {
  city: string;
  overall_status: 'completed' | 'in_progress' | 'failed' | 'pending';
  nodes_scraped: number;
  nodes_resolved: number;
  nodes_tagged: number;
  nodes_indexed: number;
  nodes_in_db: number;
  category_count: number;
  top_category: string | null;
  top_category_pct: number;
  duration_seconds: number | null;
  llm_cost_usd: number;
  steps: Record<string, StepStatus>;
  categories: CategoryEntry[];
}

interface Totals {
  cities_total: number;
  completed: number;
  in_progress: number;
  failed: number;
  pending: number;
  total_nodes: number;
  total_cost_usd: number;
}

interface OverviewData {
  cities: CityData[];
  totals: Totals;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STEP_ORDER = [
  'reddit_download',
  'scrape',
  'llm_fallback',
  'geocode_backfill',
  'business_status',
  'entity_resolution',
  'vibe_extraction',
  'rule_inference',
  'convergence',
  'qdrant_sync',
] as const;

const STEP_LABELS: Record<string, string> = {
  reddit_download: 'Reddit DL',
  scrape: 'Scrape',
  llm_fallback: 'LLM FB',
  geocode_backfill: 'Geocode',
  business_status: 'Biz Status',
  entity_resolution: 'Entity Res',
  vibe_extraction: 'Vibes',
  rule_inference: 'Rules',
  convergence: 'Converge',
  qdrant_sync: 'Qdrant',
};

const STATUS_BADGE: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  in_progress: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-700',
  pending: 'bg-ink-800 text-ink-500',
};

// Known categories from the vibe_tags vocabulary
const ALL_CATEGORIES = [
  'dining',
  'drinks',
  'shopping',
  'entertainment',
  'culture',
  'outdoors',
  'experience',
  'nightlife',
  'wellness',
  'active',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatUSD(val: number): string {
  if (val === 0) return '$0.00';
  if (val < 0.01) return `<$0.01`;
  return `$${val.toFixed(2)}`;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
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
      <span className="block font-dm-mono text-xs text-ink-500">{label}</span>
      <span className="block font-display text-2xl font-semibold text-ink-100 mt-1">
        {value}
      </span>
      {sub && (
        <span className="block font-dm-mono text-xs text-ink-600 mt-0.5">
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
    <div className="rounded-md border border-red-300 bg-red-50 p-3 font-dm-mono text-sm text-red-700">
      {message}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-surface p-8 text-center">
      <p className="font-dm-mono text-sm text-ink-600">{message}</p>
    </div>
  );
}

// Colored dot for each pipeline step cell
function StepDot({ step }: { step: StepStatus }) {
  const base = 'inline-block h-3 w-3 rounded-full flex-shrink-0';
  if (step.status === 'completed') return <span className={`${base} bg-green-500`} />;
  if (step.status === 'in_progress') return <span className={`${base} bg-blue-500 animate-pulse`} />;
  if (step.status === 'failed') return <span className={`${base} bg-red-500`} />;
  return <span className={`${base} bg-ink-700`} />;
}

// Inline bar for category distribution (pure CSS width)
function CategoryBar({ name, count, pct }: CategoryEntry) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 font-dm-mono text-xs text-ink-400 truncate">{name}</span>
      <div className="flex-1 h-2 rounded-full bg-ink-800 overflow-hidden">
        <div
          className="h-2 rounded-full bg-accent transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-12 text-right font-dm-mono text-xs text-ink-500">
        {count} <span className="text-ink-700">({pct}%)</span>
      </span>
    </div>
  );
}

// Duration bar for steps (relative to the longest step)
function DurationBar({
  label,
  duration,
  maxDuration,
}: {
  label: string;
  duration: number | null;
  maxDuration: number;
}) {
  const pct = duration != null && maxDuration > 0 ? (duration / maxDuration) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 font-dm-mono text-xs text-ink-400 truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-ink-800 overflow-hidden">
        <div
          className="h-1.5 rounded-full bg-ink-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-12 text-right font-dm-mono text-xs text-ink-600">
        {formatDuration(duration)}
      </span>
    </div>
  );
}

// Expanded row detail panel
function CityDetailPanel({ city }: { city: CityData }) {
  // Find max step duration for relative bars
  const durations = STEP_ORDER.map((s) => city.steps[s]?.duration_s ?? 0);
  const maxDuration = Math.max(...durations, 1);

  // Collect errors
  const stepErrors = STEP_ORDER.filter(
    (s) => city.steps[s]?.error
  ).map((s) => ({ step: s, error: city.steps[s].error! }));

  return (
    <tr>
      <td
        colSpan={9}
        className="px-4 pb-4 pt-0 bg-base/50"
      >
        <div className="mt-2 grid grid-cols-2 gap-6">
          {/* Category distribution */}
          <div>
            <p className="font-dm-mono text-xs text-ink-500 mb-2 uppercase tracking-wide">
              Category Distribution
            </p>
            {city.categories.length > 0 ? (
              <div className="space-y-1.5">
                {city.categories.map((cat) => (
                  <CategoryBar key={cat.name} {...cat} />
                ))}
              </div>
            ) : (
              <p className="font-dm-mono text-xs text-ink-700">No DB nodes yet</p>
            )}
          </div>

          {/* Step durations */}
          <div>
            <p className="font-dm-mono text-xs text-ink-500 mb-2 uppercase tracking-wide">
              Step Durations
            </p>
            <div className="space-y-1.5">
              {STEP_ORDER.map((stepName) => (
                <DurationBar
                  key={stepName}
                  label={STEP_LABELS[stepName] ?? stepName}
                  duration={city.steps[stepName]?.duration_s ?? null}
                  maxDuration={maxDuration}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Errors */}
        {stepErrors.length > 0 && (
          <div className="mt-3 space-y-1">
            <p className="font-dm-mono text-xs text-ink-500 uppercase tracking-wide mb-1">
              Errors
            </p>
            {stepErrors.map(({ step, error }) => (
              <div
                key={step}
                className="rounded border border-red-300/30 bg-red-50/10 px-3 py-2"
              >
                <span className="font-dm-mono text-xs font-medium text-red-400">
                  {STEP_LABELS[step] ?? step}:
                </span>{' '}
                <span className="font-dm-mono text-xs text-ink-400">{error}</span>
              </div>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function SeedVizPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCities, setExpandedCities] = useState<Set<string>>(new Set());
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchOverview = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/seed-viz/overview');
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load seed viz data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  // Polling — every 10s while any city is in_progress
  useEffect(() => {
    const hasInProgress = data?.cities.some((c) => c.overall_status === 'in_progress');

    if (hasInProgress) {
      if (!pollingRef.current) {
        pollingRef.current = setInterval(fetchOverview, 10_000);
      }
    } else {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [data, fetchOverview]);

  function toggleCity(city: string) {
    setExpandedCities((prev) => {
      const next = new Set(prev);
      if (next.has(city)) {
        next.delete(city);
      } else {
        next.add(city);
      }
      return next;
    });
  }

  const hasInProgress = data?.cities.some((c) => c.overall_status === 'in_progress');

  // Gather all categories present across completed cities
  const observedCategories = data
    ? Array.from(
        new Set(
          data.cities
            .filter((c) => c.overall_status === 'completed')
            .flatMap((c) => c.categories.map((cat) => cat.name))
        )
      )
    : [];

  // Merge known + observed category vocab for the coverage grid
  const coverageCategories = Array.from(
    new Set([...ALL_CATEGORIES, ...observedCategories])
  ).sort();

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-semibold text-ink-100">
            Seed Pipeline Viz
          </h2>
          <p className="mt-1 font-dm-mono text-sm text-ink-500">
            City seeding progress, step health, and category coverage
          </p>
        </div>
        <div className="flex items-center gap-3">
          {hasInProgress && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 font-dm-mono text-xs text-blue-800">
              polling every 10s
            </span>
          )}
          {lastUpdated && (
            <span className="font-dm-mono text-xs text-ink-600">
              {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => {
              setLoading(true);
              fetchOverview();
            }}
            disabled={loading}
            className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-dm-mono text-sm text-ink-500 transition-colors hover:bg-ink-800 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && <ErrorBanner message={error} />}

      {/* Loading state */}
      {loading && !data && (
        <div className="py-12 text-center font-dm-mono text-sm text-ink-600">
          Loading seed pipeline data...
        </div>
      )}

      {data && (
        <>
          {/* ============================================================ */}
          {/* Section 1: Summary Stat Cards                                */}
          {/* ============================================================ */}
          <section>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatCard
                label="Cities Completed"
                value={`${data.totals.completed} / ${data.totals.cities_total}`}
                sub={
                  data.totals.in_progress > 0
                    ? `${data.totals.in_progress} in progress`
                    : data.totals.pending > 0
                    ? `${data.totals.pending} pending`
                    : 'All done'
                }
              />
              <StatCard
                label="In Progress"
                value={String(data.totals.in_progress)}
                sub={data.totals.failed > 0 ? `${data.totals.failed} failed` : undefined}
              />
              <StatCard
                label="Total Nodes in DB"
                value={data.totals.total_nodes.toLocaleString()}
                sub="across all cities"
              />
              <StatCard
                label="Total LLM Cost"
                value={formatUSD(data.totals.total_cost_usd)}
                sub="estimated across pipeline"
              />
            </div>
          </section>

          {/* ============================================================ */}
          {/* Section 2: City Heatmap Table                                */}
          {/* ============================================================ */}
          <section>
            <SectionHeader title="City Heatmap">
              <span className="font-dm-mono text-xs text-ink-600">
                Click row to expand details
              </span>
            </SectionHeader>

            {data.cities.length === 0 ? (
              <EmptyState message="No seed progress files found." />
            ) : (
              <div className="rounded-lg border border-ink-700 overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-ink-700 bg-base">
                      <th className="px-4 py-2 text-left font-dm-mono text-xs text-ink-500">
                        City
                      </th>
                      <th className="px-4 py-2 text-left font-dm-mono text-xs text-ink-500">
                        Status
                      </th>
                      {/* Step column headers */}
                      {STEP_ORDER.map((s) => (
                        <th
                          key={s}
                          className="px-1 py-2 text-center font-dm-mono text-[10px] text-ink-600"
                          title={s}
                        >
                          {STEP_LABELS[s]}
                        </th>
                      ))}
                      <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                        Nodes
                      </th>
                      <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                        Cats
                      </th>
                      <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                        Duration
                      </th>
                      <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                        Cost
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cities.map((city, i) => {
                      const isExpanded = expandedCities.has(city.city);
                      return (
                        <>
                          <tr
                            key={city.city}
                            onClick={() => toggleCity(city.city)}
                            className={`cursor-pointer border-b border-ink-700/50 transition-colors hover:bg-ink-800/30 ${
                              i % 2 === 0 ? 'bg-surface' : 'bg-base/30'
                            } ${isExpanded ? 'border-b-0' : ''}`}
                          >
                            {/* City name */}
                            <td className="px-4 py-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className="font-dm-mono text-xs text-ink-300 select-none">
                                  {isExpanded ? '▼' : '▶'}
                                </span>
                                <span className="font-dm-mono text-sm text-ink-200">
                                  {capitalize(city.city)}
                                </span>
                              </div>
                            </td>

                            {/* Status badge */}
                            <td className="px-4 py-2.5">
                              <span
                                className={`rounded-full px-2 py-0.5 font-dm-mono text-xs ${
                                  STATUS_BADGE[city.overall_status] ??
                                  'bg-ink-800 text-ink-500'
                                }`}
                              >
                                {city.overall_status.replace('_', ' ')}
                              </span>
                            </td>

                            {/* Step dots */}
                            {STEP_ORDER.map((stepName) => {
                              const step = city.steps[stepName] ?? {
                                status: 'pending',
                                duration_s: null,
                                error: null,
                              };
                              return (
                                <td
                                  key={stepName}
                                  className="px-1 py-2.5 text-center"
                                  title={`${stepName}: ${step.status}${step.duration_s != null ? ` (${formatDuration(step.duration_s)})` : ''}${step.error ? ` — ${step.error}` : ''}`}
                                >
                                  <StepDot step={step} />
                                </td>
                              );
                            })}

                            {/* Nodes in DB */}
                            <td className="px-4 py-2.5 text-right font-dm-mono text-sm text-ink-300">
                              {city.nodes_in_db > 0
                                ? city.nodes_in_db.toLocaleString()
                                : <span className="text-ink-700">{city.nodes_scraped > 0 ? `~${city.nodes_scraped}` : '-'}</span>
                              }
                            </td>

                            {/* Category count */}
                            <td className="px-4 py-2.5 text-right font-dm-mono text-sm text-ink-300">
                              {city.category_count > 0 ? city.category_count : (
                                <span className="text-ink-700">-</span>
                              )}
                            </td>

                            {/* Duration */}
                            <td className="px-4 py-2.5 text-right font-dm-mono text-xs text-ink-500">
                              {formatDuration(city.duration_seconds)}
                            </td>

                            {/* LLM cost */}
                            <td className="px-4 py-2.5 text-right font-dm-mono text-xs text-ink-500">
                              {city.llm_cost_usd > 0 ? formatUSD(city.llm_cost_usd) : (
                                <span className="text-ink-700">-</span>
                              )}
                            </td>
                          </tr>

                          {/* Expanded detail */}
                          {isExpanded && (
                            <CityDetailPanel key={`${city.city}-detail`} city={city} />
                          )}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Step legend */}
            <div className="mt-3 flex items-center gap-4">
              {[
                { color: 'bg-green-500', label: 'Completed' },
                { color: 'bg-blue-500 animate-pulse', label: 'In Progress' },
                { color: 'bg-red-500', label: 'Failed' },
                { color: 'bg-ink-700', label: 'Pending' },
              ].map(({ color, label }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
                  <span className="font-dm-mono text-xs text-ink-600">{label}</span>
                </div>
              ))}
            </div>
          </section>

          {/* ============================================================ */}
          {/* Section 3: Category Coverage Grid                            */}
          {/* ============================================================ */}
          <section>
            <SectionHeader title="Category Coverage" />

            {data.cities.filter((c) => c.overall_status === 'completed').length === 0 ? (
              <EmptyState message="No completed cities yet — run a seed job to see category coverage." />
            ) : (
              <div className="rounded-lg border border-ink-700 bg-surface overflow-hidden">
                {/* Header row with category names */}
                <div className="border-b border-ink-700 bg-base px-4 py-2 flex items-center gap-2">
                  <span className="w-28 font-dm-mono text-xs text-ink-500 shrink-0">
                    City
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {coverageCategories.map((cat) => (
                      <span
                        key={cat}
                        className="font-dm-mono text-[10px] text-ink-500 w-20 text-center"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>

                {/* One row per completed city */}
                {data.cities
                  .filter((c) => c.overall_status === 'completed')
                  .map((city, i) => {
                    const cityCategories = new Set(city.categories.map((c) => c.name));
                    return (
                      <div
                        key={city.city}
                        className={`px-4 py-2 flex items-center gap-2 border-b border-ink-700/30 last:border-b-0 ${
                          i % 2 === 0 ? '' : 'bg-base/20'
                        }`}
                      >
                        <span className="w-28 font-dm-mono text-sm text-ink-300 shrink-0 truncate">
                          {capitalize(city.city)}
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {coverageCategories.map((cat) => {
                            const present = cityCategories.has(cat);
                            const entry = city.categories.find((c) => c.name === cat);
                            return (
                              <span
                                key={cat}
                                title={
                                  present && entry
                                    ? `${entry.count} nodes (${entry.pct}%)`
                                    : 'Not present'
                                }
                                className={`w-20 text-center rounded-full px-2 py-0.5 font-dm-mono text-xs transition-colors ${
                                  present
                                    ? 'bg-accent/20 text-accent'
                                    : 'bg-ink-800 text-ink-600 line-through'
                                }`}
                              >
                                {cat}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
          </section>

          {/* ============================================================ */}
          {/* Section 4: Raw Counts Reference Table                        */}
          {/* ============================================================ */}
          <section>
            <SectionHeader title="Pipeline Counts" />
            <div className="rounded-lg border border-ink-700 overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ink-700 bg-base">
                    <th className="px-4 py-2 text-left font-dm-mono text-xs text-ink-500">
                      City
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      Scraped
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      Resolved
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      Tagged
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      Indexed
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      In DB
                    </th>
                    <th className="px-4 py-2 text-right font-dm-mono text-xs text-ink-500">
                      Top Category
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.cities.map((city, i) => (
                    <tr
                      key={city.city}
                      className={`border-b border-ink-700/30 last:border-b-0 ${
                        i % 2 === 0 ? 'bg-surface' : 'bg-base/30'
                      }`}
                    >
                      <td className="px-4 py-2 font-dm-mono text-sm text-ink-200">
                        {capitalize(city.city)}
                      </td>
                      <td className="px-4 py-2 text-right font-dm-mono text-sm text-ink-400">
                        {city.nodes_scraped.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-dm-mono text-sm text-ink-400">
                        {city.nodes_resolved.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-dm-mono text-sm text-ink-400">
                        {city.nodes_tagged.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-dm-mono text-sm text-ink-400">
                        {city.nodes_indexed.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-dm-mono text-sm font-medium text-ink-200">
                        {city.nodes_in_db > 0 ? city.nodes_in_db.toLocaleString() : '-'}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {city.top_category ? (
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-dm-mono text-xs text-ink-400">
                              {city.top_category}
                            </span>
                            <span className="rounded-full bg-accent/10 px-2 py-0.5 font-dm-mono text-xs text-accent">
                              {city.top_category_pct}%
                            </span>
                          </div>
                        ) : (
                          <span className="font-dm-mono text-xs text-ink-700">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
