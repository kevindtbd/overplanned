"use client";

// PulseLine — Group activity over time as an SVG line chart.
//
// Renders a smooth area+line chart of group engagement (votes, signals,
// interactions) across the trip timeline. No external chart libraries —
// pure SVG with cubic bezier smoothing.
//
// Usage:
//   <PulseLine data={pulseHistory} height={160} />

import { useMemo } from "react";

// ---------- Types ----------

export interface PulsePoint {
  /** ISO timestamp or day label */
  label: string;
  /** Primary series: group activity count (0–N) */
  activityCount: number;
  /** Secondary series: contested slot count */
  contestedCount?: number;
}

export interface PulseLineProps {
  data: PulsePoint[];
  height?: number;
  accentColor?: string;
  /** Secondary series color (contested) */
  contestedColor?: string;
  className?: string;
}

// ---------- SVG math helpers ----------

function mapRange(
  value: number,
  inMin: number,
  inMax: number,
  outMin: number,
  outMax: number
): number {
  if (inMax === inMin) return (outMin + outMax) / 2;
  return ((value - inMin) / (inMax - inMin)) * (outMax - outMin) + outMin;
}

/** Build a smooth SVG path from (x, y) point pairs using cubic bezier. */
function buildSmoothPath(points: [number, number][]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;

  let d = `M ${points[0][0]} ${points[0][1]}`;

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpX = (prev[0] + curr[0]) / 2;
    d += ` C ${cpX} ${prev[1]}, ${cpX} ${curr[1]}, ${curr[0]} ${curr[1]}`;
  }

  return d;
}

/** Build a closed area path (line + bottom fill). */
function buildAreaPath(
  points: [number, number][],
  bottomY: number
): string {
  if (points.length === 0) return "";
  const linePath = buildSmoothPath(points);
  const last = points[points.length - 1];
  const first = points[0];
  return `${linePath} L ${last[0]} ${bottomY} L ${first[0]} ${bottomY} Z`;
}

// ---------- Component ----------

export function PulseLine({
  data,
  height = 160,
  accentColor = "var(--accent)",
  contestedColor = "#f59e0b",
  className = "",
}: PulseLineProps) {
  const PAD_LEFT = 32;
  const PAD_RIGHT = 12;
  const PAD_TOP = 12;
  const PAD_BOTTOM = 32;
  const INNER_H = height - PAD_TOP - PAD_BOTTOM;

  const { actPoints, contPoints, maxVal, minVal, gridLines, xLabels, gradientId } =
    useMemo(() => {
      const id = `pulse-grad-${Math.random().toString(36).slice(2, 7)}`;

      if (!data || data.length === 0) {
        return {
          actPoints: [] as [number, number][],
          contPoints: [] as [number, number][],
          maxVal: 0,
          minVal: 0,
          gridLines: [] as number[],
          xLabels: [] as { x: number; label: string }[],
          gradientId: id,
        };
      }

      const allVals = data.flatMap((d) => [
        d.activityCount,
        d.contestedCount ?? 0,
      ]);
      const rawMax = Math.max(...allVals, 1);
      const rawMin = 0;

      // Round max up to a clean step
      const step = rawMax <= 5 ? 1 : rawMax <= 20 ? 5 : 10;
      const max = Math.ceil(rawMax / step) * step;
      const min = rawMin;

      const gLines: number[] = [];
      for (let v = 0; v <= max; v += step) {
        gLines.push(v);
      }

      // We don't know the SVG width at render time — use 100% via viewBox ratio
      // Instead, compute points as fractions [0..1] and scale in render
      const n = data.length;
      const innerW = 1; // will scale via viewBox

      const act: [number, number][] = data.map((d, i) => [
        mapRange(i, 0, Math.max(n - 1, 1), 0, innerW),
        mapRange(d.activityCount, min, max, 1, 0),
      ]);

      const cont: [number, number][] = data.map((d, i) => [
        mapRange(i, 0, Math.max(n - 1, 1), 0, innerW),
        mapRange(d.contestedCount ?? 0, min, max, 1, 0),
      ]);

      const labels = data.map((d, i) => ({
        x: mapRange(i, 0, Math.max(n - 1, 1), 0, innerW),
        label: d.label,
      }));

      return {
        actPoints: act,
        contPoints: cont,
        maxVal: max,
        minVal: min,
        gridLines: gLines,
        xLabels: labels,
        gradientId: id,
      };
    }, [data]);

  // Scale points to SVG coordinate space
  // viewBox width = 1 (fractional) scaled via width="100%"
  // We use a fixed viewBox of 200 x height
  const VW = 200;
  const INNER_W = VW - PAD_LEFT - PAD_RIGHT;
  const INNER_H_REAL = INNER_H;

  const scalePoint = ([fx, fy]: [number, number]): [number, number] => [
    PAD_LEFT + fx * INNER_W,
    PAD_TOP + fy * INNER_H_REAL,
  ];

  const scaledAct = actPoints.map(scalePoint);
  const scaledCont = contPoints.map(scalePoint);
  const bottomY = PAD_TOP + INNER_H_REAL;

  const actLinePath = buildSmoothPath(scaledAct);
  const actAreaPath = buildAreaPath(scaledAct, bottomY);
  const contLinePath = buildSmoothPath(scaledCont);

  if (!data || data.length === 0) {
    return (
      <div
        className={`
          flex items-center justify-center
          rounded-xl border border-ink-700 bg-surface
          font-dm-mono text-xs text-ink-400 uppercase tracking-wider
          ${className}
        `}
        style={{ height }}
        aria-label="No pulse data available"
      >
        No activity data yet
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-ink-700 bg-surface overflow-hidden ${className}`}
      aria-label="Group activity pulse chart"
    >
      <svg
        viewBox={`0 0 ${VW} ${height}`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        aria-hidden="true"
        role="img"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accentColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={accentColor} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {gridLines.map((val) => {
          const y =
            PAD_TOP +
            mapRange(val, minVal, maxVal, INNER_H_REAL, 0);
          return (
            <g key={val}>
              <line
                x1={PAD_LEFT}
                y1={y}
                x2={VW - PAD_RIGHT}
                y2={y}
                stroke="var(--ink-700)"
                strokeWidth="0.5"
                strokeDasharray="3 3"
              />
              <text
                x={PAD_LEFT - 4}
                y={y + 3}
                textAnchor="end"
                fontSize="7"
                fill="var(--ink-400)"
                fontFamily="var(--font-dm-mono, monospace)"
              >
                {val}
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        {xLabels.map(({ x, label }, i) => {
          const svgX = PAD_LEFT + x * INNER_W;
          // Only render a label if there's room (show every nth)
          const step = Math.ceil(xLabels.length / 6);
          if (i % step !== 0 && i !== xLabels.length - 1) return null;
          return (
            <text
              key={i}
              x={svgX}
              y={height - 4}
              textAnchor="middle"
              fontSize="7"
              fill="var(--ink-400)"
              fontFamily="var(--font-dm-mono, monospace)"
            >
              {label.length > 5 ? label.slice(0, 5) : label}
            </text>
          );
        })}

        {/* Area fill */}
        {actAreaPath && (
          <path d={actAreaPath} fill={`url(#${gradientId})`} />
        )}

        {/* Contested line */}
        {contLinePath && (
          <path
            d={contLinePath}
            fill="none"
            stroke={contestedColor}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray="4 2"
            opacity="0.7"
          />
        )}

        {/* Activity line */}
        {actLinePath && (
          <path
            d={actLinePath}
            fill="none"
            stroke={accentColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Data point dots */}
        {scaledAct.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="2.5"
            fill={accentColor}
            stroke="var(--bg-surface)"
            strokeWidth="1.5"
          />
        ))}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 pb-3 pt-1">
        <div className="flex items-center gap-1.5">
          <svg width="16" height="8" aria-hidden="true">
            <line
              x1="0"
              y1="4"
              x2="16"
              y2="4"
              stroke={accentColor}
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
            Activity
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <svg width="16" height="8" aria-hidden="true">
            <line
              x1="0"
              y1="4"
              x2="16"
              y2="4"
              stroke={contestedColor}
              strokeWidth="1.5"
              strokeDasharray="4 2"
              strokeLinecap="round"
            />
          </svg>
          <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
            Contested
          </span>
        </div>
      </div>
    </div>
  );
}
