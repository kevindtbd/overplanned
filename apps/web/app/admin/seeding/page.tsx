'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SeedEstimate {
  city: string;
  country_code: string;
  estimated_api_calls: number;
  estimated_cost_usd: number;
  estimated_duration_minutes: number;
  sources: string[];
}

interface CityProgress {
  city: string;
  country_code: string;
  job_id: string;
  status: string;
  scraped: number;
  resolved: number;
  tagged: number;
  indexed: number;
  total_expected: number;
  error: string | null;
  started_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';
const POLL_INTERVAL_MS = 5_000;
const RATE_LIMIT_COOLDOWN_MS = 30_000;

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  scraping: 'bg-blue-100 text-blue-800',
  resolving: 'bg-indigo-100 text-indigo-800',
  tagging: 'bg-purple-100 text-purple-800',
  indexing: 'bg-cyan-100 text-cyan-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

const STAGE_LABELS = ['scraped', 'resolved', 'tagged', 'indexed'] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(n: number, total: number): number {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function formatCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SeedingPage() {
  // Form state
  const [city, setCity] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [estimate, setEstimate] = useState<SeedEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState('');

  // Trigger state
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerError, setTriggerError] = useState('');
  const [lastTriggerAt, setLastTriggerAt] = useState(0);

  // Progress state
  const [jobs, setJobs] = useState<CityProgress[]>([]);
  const [progressError, setProgressError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ------ API calls ------

  const fetchEstimate = useCallback(async () => {
    if (!city.trim() || !countryCode.trim()) return;
    setEstimateLoading(true);
    setEstimateError('');
    setEstimate(null);

    try {
      const res = await fetch(`${API_BASE}/admin/seeding/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ city: city.trim(), country_code: countryCode.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setEstimate(await res.json());
    } catch (e: any) {
      setEstimateError(e.message ?? 'Failed to fetch estimate');
    } finally {
      setEstimateLoading(false);
    }
  }, [city, countryCode]);

  const triggerSeed = useCallback(async () => {
    if (!estimate) return;

    // Client-side cooldown
    const elapsed = Date.now() - lastTriggerAt;
    if (elapsed < RATE_LIMIT_COOLDOWN_MS) {
      const wait = Math.ceil((RATE_LIMIT_COOLDOWN_MS - elapsed) / 1000);
      setTriggerError(`Rate limited. Wait ${wait}s before triggering again.`);
      return;
    }

    setTriggerLoading(true);
    setTriggerError('');

    try {
      const res = await fetch(`${API_BASE}/admin/seeding/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          city: estimate.city,
          country_code: estimate.country_code,
          confirmed: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setLastTriggerAt(Date.now());
      setEstimate(null);
      setCity('');
      setCountryCode('');
      // Refresh progress immediately
      fetchProgress();
    } catch (e: any) {
      setTriggerError(e.message ?? 'Failed to trigger seed');
    } finally {
      setTriggerLoading(false);
    }
  }, [estimate, lastTriggerAt]);

  const fetchProgress = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/seeding/progress`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setJobs(data.jobs ?? []);
      setProgressError('');
    } catch (e: any) {
      setProgressError(e.message ?? 'Failed to load progress');
    }
  }, []);

  // ------ Polling ------

  useEffect(() => {
    fetchProgress();
    pollRef.current = setInterval(fetchProgress, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchProgress]);

  // ------ Active job detection ------

  const hasActiveJobs = jobs.some(
    (j) => !['completed', 'failed'].includes(j.status)
  );

  // ------ Render ------

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h2 className="font-display text-2xl text-ink-100">City Seeding</h2>
        <p className="mt-1 font-dm-mono text-sm text-ink-500">
          Trigger and monitor data pipeline seed jobs per city.
        </p>
      </div>

      {/* ---- Trigger Section ---- */}
      <section className="rounded-lg border border-ink-700 bg-surface p-6">
        <h3 className="font-display text-lg text-ink-100 mb-4">
          Trigger Seed Job
        </h3>

        {/* City input */}
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label
              htmlFor="seed-city"
              className="block font-dm-mono text-xs text-ink-500 mb-1"
            >
              City
            </label>
            <input
              id="seed-city"
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="e.g. Austin"
              className="w-full rounded border border-ink-700 bg-white px-3 py-2 font-dm-mono text-sm text-ink-100 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>

          <div className="w-24">
            <label
              htmlFor="seed-country"
              className="block font-dm-mono text-xs text-ink-500 mb-1"
            >
              Country
            </label>
            <input
              id="seed-country"
              type="text"
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value.toUpperCase())}
              placeholder="US"
              maxLength={3}
              className="w-full rounded border border-ink-700 bg-white px-3 py-2 font-dm-mono text-sm text-ink-100 uppercase focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>

          <button
            onClick={fetchEstimate}
            disabled={!city.trim() || !countryCode.trim() || estimateLoading}
            className="rounded bg-ink-200 px-4 py-2 font-dm-mono text-sm text-white hover:bg-ink-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {estimateLoading ? 'Estimating...' : 'Get Estimate'}
          </button>
        </div>

        {estimateError && (
          <p className="mt-2 font-dm-mono text-xs text-error">{estimateError}</p>
        )}

        {/* Estimate card */}
        {estimate && (
          <div className="mt-4 rounded border border-ink-700 bg-white p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-display text-base text-ink-100">
                {estimate.city} ({estimate.country_code})
              </span>
              <span className="font-dm-mono text-sm font-medium text-accent">
                {formatCost(estimate.estimated_cost_usd)} estimated
              </span>
            </div>

            <div className="grid grid-cols-3 gap-4 font-dm-mono text-xs text-ink-500">
              <div>
                <span className="block text-ink-100 text-sm">
                  {estimate.estimated_api_calls}
                </span>
                API calls
              </div>
              <div>
                <span className="block text-ink-100 text-sm">
                  ~{estimate.estimated_duration_minutes} min
                </span>
                Duration
              </div>
              <div>
                <span className="block text-ink-100 text-sm">
                  {estimate.sources.length}
                </span>
                Sources
              </div>
            </div>

            <div className="flex flex-wrap gap-1">
              {estimate.sources.map((s) => (
                <span
                  key={s}
                  className="rounded bg-ink-800 px-2 py-0.5 font-dm-mono text-xs text-ink-500"
                >
                  {s}
                </span>
              ))}
            </div>

            <div className="flex items-center gap-3 pt-2 border-t border-ink-700">
              <button
                onClick={triggerSeed}
                disabled={triggerLoading}
                className="rounded bg-accent px-4 py-2 font-dm-mono text-sm text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
              >
                {triggerLoading ? 'Triggering...' : 'Confirm & Seed'}
              </button>
              <button
                onClick={() => setEstimate(null)}
                className="font-dm-mono text-sm text-ink-500 hover:text-ink-300 transition-colors"
              >
                Cancel
              </button>
            </div>

            {triggerError && (
              <p className="font-dm-mono text-xs text-error">{triggerError}</p>
            )}
          </div>
        )}

        <p className="mt-2 font-dm-mono text-xs text-ink-600">
          Rate limit: 2 seed triggers per minute.
        </p>
      </section>

      {/* ---- Progress Dashboard ---- */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg text-ink-100">
            Seed Progress
          </h3>
          {hasActiveJobs && (
            <span className="inline-flex items-center gap-1.5 font-dm-mono text-xs text-blue-600">
              <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
              Live — polling every {POLL_INTERVAL_MS / 1000}s
            </span>
          )}
        </div>

        {progressError && (
          <p className="font-dm-mono text-xs text-error">{progressError}</p>
        )}

        {jobs.length === 0 && !progressError && (
          <p className="font-dm-mono text-sm text-ink-600">
            No seed jobs found. Trigger one above to get started.
          </p>
        )}

        <div className="space-y-3">
          {jobs.map((job) => (
            <div
              key={job.job_id}
              className="rounded-lg border border-ink-700 bg-surface p-4"
            >
              {/* Header row */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-display text-base text-ink-100">
                    {job.city}
                  </span>
                  <span className="font-dm-mono text-xs text-ink-600">
                    {job.country_code}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 font-dm-mono text-xs ${
                      STATUS_COLORS[job.status] ?? 'bg-ink-800 text-ink-500'
                    }`}
                  >
                    {job.status}
                  </span>
                  <span className="font-dm-mono text-xs text-ink-600">
                    {timeAgo(job.updated_at || job.started_at)}
                  </span>
                </div>
              </div>

              {/* Progress bars */}
              {job.total_expected > 0 && (
                <div className="grid grid-cols-4 gap-2">
                  {STAGE_LABELS.map((stage) => {
                    const value = job[stage];
                    const percent = pct(value, job.total_expected);
                    return (
                      <div key={stage}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-dm-mono text-xs text-ink-500 capitalize">
                            {stage}
                          </span>
                          <span className="font-dm-mono text-xs text-ink-300">
                            {value}/{job.total_expected}
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-ink-800">
                          <div
                            className="h-1.5 rounded-full bg-accent transition-all duration-500"
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Pending — no progress yet */}
              {job.total_expected === 0 && job.status === 'pending' && (
                <p className="font-dm-mono text-xs text-ink-600">
                  Waiting for pipeline to pick up job...
                </p>
              )}

              {/* Error display */}
              {job.error && (
                <p className="mt-2 font-dm-mono text-xs text-error">
                  {job.error}
                </p>
              )}

              {/* Job ID */}
              <p className="mt-2 font-dm-mono text-[10px] text-ink-700">
                {job.job_id}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
