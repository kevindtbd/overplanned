'use client';

import { useState, useCallback } from 'react';

/**
 * Stage badge colors following the design system tokens.
 */
const STAGE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  staging: { bg: 'bg-yellow-50', text: 'text-yellow-700', label: 'Staging' },
  ab_test: { bg: 'bg-blue-50', text: 'text-blue-700', label: 'A/B Test' },
  production: { bg: 'bg-green-50', text: 'text-green-700', label: 'Production' },
  archived: { bg: 'bg-ink-800', text: 'text-ink-500', label: 'Archived' },
};

const PROMOTION_PATH: Record<string, string> = {
  staging: 'ab_test',
  ab_test: 'production',
};

interface ModelEntry {
  id: string;
  model_name: string;
  model_version: string;
  stage: string;
  model_type: string;
  description: string | null;
  artifact_path: string | null;
  artifact_hash: string | null;
  metrics: Record<string, number> | null;
  evaluated_at: string | null;
  training_data_range: { from?: string; to?: string; signal_count?: number } | null;
  promoted_at: string | null;
  promoted_by: string | null;
  created_at: string;
}

interface ComparisonData {
  candidate: {
    id: string;
    version: string;
    stage: string;
    metrics: Record<string, number>;
  };
  current: {
    id: string | null;
    version: string | null;
    stage: string;
    metrics: Record<string, number>;
  };
  comparison: {
    primary_metric: string;
    candidate_value: number | null;
    current_value: number | null;
    passes_gate: boolean;
    lower_is_better: boolean;
  };
  target_stage: string;
}

export function StageBadge({ stage }: { stage: string }) {
  const style = STAGE_STYLES[stage] || STAGE_STYLES.archived;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 font-dm-mono text-xs font-medium ${style.bg} ${style.text}`}
    >
      {style.label}
    </span>
  );
}

export function ArtifactHashDisplay({ hash }: { hash: string | null }) {
  if (!hash) {
    return (
      <span className="font-dm-mono text-xs text-ink-600">
        No hash recorded
      </span>
    );
  }
  return (
    <span className="font-dm-mono text-xs text-ink-500" title={hash}>
      SHA-256: {hash.slice(0, 12)}...
    </span>
  );
}

function MetricsTable({
  candidateMetrics,
  currentMetrics,
  primaryMetric,
  lowerIsBetter,
}: {
  candidateMetrics: Record<string, number>;
  currentMetrics: Record<string, number>;
  primaryMetric: string;
  lowerIsBetter: boolean;
}) {
  const allKeys = Array.from(
    new Set([...Object.keys(candidateMetrics), ...Object.keys(currentMetrics)])
  ).sort();

  return (
    <table className="w-full font-dm-mono text-sm">
      <thead>
        <tr className="border-b border-ink-700 text-left">
          <th className="pb-2 pr-4 text-ink-500">Metric</th>
          <th className="pb-2 pr-4 text-ink-500">Candidate</th>
          <th className="pb-2 pr-4 text-ink-500">Current</th>
          <th className="pb-2 text-ink-500">Delta</th>
        </tr>
      </thead>
      <tbody>
        {allKeys.map((key) => {
          const cVal = candidateMetrics[key];
          const curVal = currentMetrics[key];
          const isPrimary = key === primaryMetric;
          const delta = cVal != null && curVal != null ? cVal - curVal : null;
          const isImprovement =
            delta != null
              ? lowerIsBetter
                ? delta <= 0
                : delta >= 0
              : null;

          return (
            <tr
              key={key}
              className={`border-b border-ink-700/50 ${isPrimary ? 'bg-surface font-semibold' : ''}`}
            >
              <td className="py-1.5 pr-4 text-ink-200">
                {key}
                {isPrimary && (
                  <span className="ml-1.5 text-xs text-accent">
                    (primary)
                  </span>
                )}
              </td>
              <td className="py-1.5 pr-4">{cVal != null ? cVal.toFixed(4) : '-'}</td>
              <td className="py-1.5 pr-4">{curVal != null ? curVal.toFixed(4) : '-'}</td>
              <td className="py-1.5">
                {delta != null ? (
                  <span
                    className={
                      isImprovement ? 'text-green-700' : 'text-error'
                    }
                  >
                    {delta > 0 ? '+' : ''}
                    {delta.toFixed(4)}
                  </span>
                ) : (
                  '-'
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

interface PromotionGateProps {
  model: ModelEntry;
  onPromoted: () => void;
}

export function PromotionGate({ model, onPromoted }: PromotionGateProps) {
  const [comparison, setComparison] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  const nextStage = PROMOTION_PATH[model.stage];
  const canPromote = !!nextStage;

  const fetchComparison = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/models/${model.id}/compare`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to fetch comparison (${res.status})`);
      }
      const json = await res.json();
      setComparison(json.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [model.id]);

  const executePromotion = useCallback(async () => {
    if (!nextStage) return;
    setPromoting(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/models/${model.id}/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_stage: nextStage }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Promotion failed (${res.status})`);
      }
      setShowConfirm(false);
      setComparison(null);
      onPromoted();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setPromoting(false);
    }
  }, [model.id, nextStage, onPromoted]);

  if (!canPromote) return null;

  return (
    <div className="mt-4 rounded-lg border border-ink-700 bg-surface p-4">
      <div className="flex items-center justify-between">
        <h4 className="font-display text-sm font-semibold text-ink-200">
          Promote to{' '}
          <span className="text-accent">
            {STAGE_STYLES[nextStage]?.label || nextStage}
          </span>
        </h4>

        {!comparison && (
          <button
            onClick={fetchComparison}
            disabled={loading}
            className="rounded-md bg-base px-3 py-1.5 font-dm-mono text-xs text-ink-300 transition-colors hover:bg-ink-800 disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Compare Metrics'}
          </button>
        )}
      </div>

      {error && (
        <p className="mt-2 font-dm-mono text-xs text-error">{error}</p>
      )}

      {comparison && (
        <div className="mt-4 space-y-4">
          <MetricsTable
            candidateMetrics={comparison.candidate.metrics}
            currentMetrics={comparison.current.metrics}
            primaryMetric={comparison.comparison.primary_metric}
            lowerIsBetter={comparison.comparison.lower_is_better}
          />

          {comparison.current.id && (
            <p className="font-dm-mono text-xs text-ink-500">
              Current {STAGE_STYLES[comparison.target_stage]?.label}:{' '}
              {comparison.current.version}
              {' — will be archived on promotion'}
            </p>
          )}

          {!comparison.current.id && (
            <p className="font-dm-mono text-xs text-ink-500">
              No model currently in {STAGE_STYLES[comparison.target_stage]?.label}.
              This will be the first.
            </p>
          )}

          <div className="flex items-center gap-3 border-t border-ink-700 pt-3">
            {comparison.comparison.passes_gate ? (
              <>
                {!showConfirm ? (
                  <button
                    onClick={() => setShowConfirm(true)}
                    className="rounded-md bg-accent px-4 py-2 font-dm-mono text-sm text-white transition-colors hover:bg-[#B85C3F]"
                  >
                    Promote to {STAGE_STYLES[nextStage]?.label}
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="font-dm-mono text-xs text-ink-500">
                      Confirm promotion?
                    </span>
                    <button
                      onClick={executePromotion}
                      disabled={promoting}
                      className="rounded-md bg-green-700 px-4 py-2 font-dm-mono text-sm text-white transition-colors hover:bg-green-800 disabled:opacity-50"
                    >
                      {promoting ? 'Promoting...' : 'Yes, Promote'}
                    </button>
                    <button
                      onClick={() => setShowConfirm(false)}
                      className="rounded-md border border-ink-700 px-3 py-2 font-dm-mono text-xs text-ink-500 transition-colors hover:bg-ink-800"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </>
            ) : (
              <p className="font-dm-mono text-sm text-error">
                Gate blocked: candidate does not beat current on{' '}
                {comparison.comparison.primary_metric}
              </p>
            )}
            <button
              onClick={() => {
                setComparison(null);
                setShowConfirm(false);
              }}
              className="ml-auto font-dm-mono text-xs text-ink-600 hover:text-ink-500"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
