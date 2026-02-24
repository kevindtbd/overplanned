'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  StageBadge,
  ArtifactHashDisplay,
  PromotionGate,
} from './components/PromotionGate';

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

const STAGE_ORDER = ['production', 'ab_test', 'staging', 'archived'] as const;

function groupByModel(models: ModelEntry[]): Record<string, ModelEntry[]> {
  const groups: Record<string, ModelEntry[]> = {};
  for (const m of models) {
    if (!groups[m.model_name]) groups[m.model_name] = [];
    groups[m.model_name].push(m);
  }
  // Sort within each group by stage priority
  for (const name of Object.keys(groups)) {
    groups[name].sort(
      (a, b) => STAGE_ORDER.indexOf(a.stage as any) - STAGE_ORDER.indexOf(b.stage as any)
    );
  }
  return groups;
}

function MetricsPills({ metrics }: { metrics: Record<string, number> | null }) {
  if (!metrics || Object.keys(metrics).length === 0) {
    return <span className="font-dm-mono text-xs text-ink-600">No metrics</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(metrics).map(([key, val]) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 rounded-full bg-base px-2 py-0.5 font-dm-mono text-xs text-ink-500"
        >
          <span className="text-ink-600">{key}:</span>
          <span className="font-medium">{typeof val === 'number' ? val.toFixed(4) : String(val)}</span>
        </span>
      ))}
    </div>
  );
}

function TrainingRange({
  range,
}: {
  range: { from?: string; to?: string; signal_count?: number } | null;
}) {
  if (!range) return null;
  return (
    <span className="font-dm-mono text-xs text-ink-500">
      {range.from && range.to
        ? `${range.from.slice(0, 10)} to ${range.to.slice(0, 10)}`
        : 'Range unknown'}
      {range.signal_count != null && ` (${range.signal_count.toLocaleString()} signals)`}
    </span>
  );
}

export default function ModelsPage() {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStage, setFilterStage] = useState<string>('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filterStage) params.set('stage', filterStage);
      const res = await fetch(`/api/admin/models?${params.toString()}`);
      if (!res.ok) throw new Error(`Failed to load models (${res.status})`);
      const json = await res.json();
      setModels(json.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filterStage]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const grouped = groupByModel(models);

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-semibold text-ink-100">
            Model Registry
          </h2>
          <p className="mt-1 font-dm-mono text-sm text-ink-500">
            Manage ML model lifecycle and promotions
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filterStage}
            onChange={(e) => setFilterStage(e.target.value)}
            className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-dm-mono text-sm text-ink-300"
          >
            <option value="">All stages</option>
            <option value="staging">Staging</option>
            <option value="ab_test">A/B Test</option>
            <option value="production">Production</option>
            <option value="archived">Archived</option>
          </select>
          <button
            onClick={fetchModels}
            disabled={loading}
            className="rounded-md border border-ink-700 bg-surface px-3 py-1.5 font-dm-mono text-sm text-ink-500 transition-colors hover:bg-ink-800 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-4 rounded-md border border-error/30 bg-error-bg p-3 font-dm-mono text-sm text-error">
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && models.length === 0 && (
        <div className="py-12 text-center font-dm-mono text-sm text-ink-600">
          Loading models...
        </div>
      )}

      {/* Empty state */}
      {!loading && models.length === 0 && !error && (
        <div className="rounded-lg border border-ink-700 bg-surface p-12 text-center">
          <p className="font-dm-mono text-sm text-ink-500">
            No models registered yet.
          </p>
          <p className="mt-1 font-dm-mono text-xs text-ink-600">
            Models appear here once registered via the ML pipeline.
          </p>
        </div>
      )}

      {/* Model groups */}
      <div className="space-y-8">
        {Object.entries(grouped).map(([modelName, versions]) => (
          <div key={modelName}>
            <h3 className="mb-3 font-display text-lg font-semibold text-ink-200">
              {modelName}
              <span className="ml-2 font-dm-mono text-xs font-normal text-ink-600">
                {versions.length} version{versions.length !== 1 && 's'}
              </span>
            </h3>

            <div className="space-y-3">
              {versions.map((m) => {
                const isExpanded = expandedId === m.id;
                return (
                  <div
                    key={m.id}
                    className="rounded-lg border border-ink-700 bg-surface shadow-sm"
                  >
                    {/* Row summary */}
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : m.id)}
                      className="flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-base/50"
                    >
                      <StageBadge stage={m.stage} />

                      <span className="font-dm-mono text-sm font-medium text-ink-200">
                        v{m.model_version}
                      </span>

                      <span className="font-dm-mono text-xs text-ink-500">
                        {m.model_type}
                      </span>

                      <div className="ml-auto flex items-center gap-4">
                        <ArtifactHashDisplay hash={m.artifact_hash} />

                        {m.promoted_at && (
                          <span className="font-dm-mono text-xs text-ink-600">
                            Promoted{' '}
                            {new Date(m.promoted_at).toLocaleDateString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                            })}
                          </span>
                        )}

                        <svg
                          className={`h-4 w-4 text-ink-600 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fillRule="evenodd"
                            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                    </button>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="border-t border-ink-700 px-4 py-4">
                        <div className="grid grid-cols-2 gap-4">
                          {/* Left column: info */}
                          <div className="space-y-3">
                            {m.description && (
                              <div>
                                <span className="font-dm-mono text-xs text-ink-600">
                                  Description
                                </span>
                                <p className="text-sm text-ink-300">
                                  {m.description}
                                </p>
                              </div>
                            )}

                            {m.artifact_path && (
                              <div>
                                <span className="font-dm-mono text-xs text-ink-600">
                                  Artifact
                                </span>
                                <p className="font-dm-mono text-xs text-ink-500 break-all">
                                  {m.artifact_path}
                                </p>
                              </div>
                            )}

                            <div>
                              <span className="font-dm-mono text-xs text-ink-600">
                                Artifact Hash
                              </span>
                              <p className="font-dm-mono text-xs text-ink-500 break-all">
                                {m.artifact_hash || 'Not recorded'}
                              </p>
                            </div>

                            <div>
                              <span className="font-dm-mono text-xs text-ink-600">
                                Training Data
                              </span>
                              <div>
                                <TrainingRange range={m.training_data_range} />
                              </div>
                            </div>

                            {m.evaluated_at && (
                              <div>
                                <span className="font-dm-mono text-xs text-ink-600">
                                  Evaluated
                                </span>
                                <p className="font-dm-mono text-xs text-ink-500">
                                  {new Date(m.evaluated_at).toLocaleString()}
                                </p>
                              </div>
                            )}

                            <div>
                              <span className="font-dm-mono text-xs text-ink-600">
                                Registered
                              </span>
                              <p className="font-dm-mono text-xs text-ink-500">
                                {new Date(m.created_at).toLocaleString()}
                              </p>
                            </div>
                          </div>

                          {/* Right column: metrics */}
                          <div>
                            <span className="font-dm-mono text-xs text-ink-600">
                              Metrics
                            </span>
                            <div className="mt-1">
                              <MetricsPills metrics={m.metrics} />
                            </div>
                          </div>
                        </div>

                        {/* Promotion gate */}
                        <PromotionGate model={m} onPromoted={fetchModels} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
