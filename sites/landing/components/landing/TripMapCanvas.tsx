"use client";

import { useEffect, useRef, useCallback } from "react";

/* ------------------------------------------------------------------ */
/*  Stop & block data                                                  */
/* ------------------------------------------------------------------ */

interface Stop {
  x: number;
  y: number;
  label: string;
  start?: boolean;
  end?: boolean;
  current?: boolean; // "you are here" — green dot
}

const STOPS: Stop[] = [
  { x: 0.08, y: 0.82, label: "Tsukiji", start: true },
  { x: 0.22, y: 0.65, label: "Senso-ji" },
  { x: 0.35, y: 0.48, label: "Shinjuku" },
  { x: 0.48, y: 0.35, label: "Harajuku", current: true },
  { x: 0.61, y: 0.14, label: "Meiji" },
  { x: 0.74, y: 0.40, label: "Ginza" },
  { x: 0.88, y: 0.22, label: "Roppongi", end: true },
];

// Pit stop offshoots — short detours branching off the main route
interface PitStop {
  parentSegIdx: number; // which route segment it branches from
  tOnParent: number;    // 0-1 position along that segment
  dx: number;           // x offset (fraction of W)
  dy: number;           // y offset (fraction of H)
  label: string;
}

const PIT_STOPS: PitStop[] = [
  { parentSegIdx: 0, tOnParent: 0.55, dx: -0.06, dy: 0.06, label: "Coffee" },
  { parentSegIdx: 1, tOnParent: 0.40, dx: 0.05, dy: -0.06, label: "Shrine" },
  { parentSegIdx: 3, tOnParent: 0.60, dx: -0.05, dy: -0.05, label: "Ramen" },
  { parentSegIdx: 4, tOnParent: 0.35, dx: 0.06, dy: 0.05, label: "Park" },
  { parentSegIdx: 5, tOnParent: 0.50, dx: -0.04, dy: -0.06, label: "Bar" },
];

// [xFrac, yFrac, width, height]
const BLOCKS: [number, number, number, number][] = [
  [0.05, 0.05, 90, 60],
  [0.24, 0.22, 100, 68],
  [0.48, 0.06, 86, 58],
  [0.68, 0.34, 82, 54],
  [0.32, 0.60, 78, 58],
  [0.60, 0.58, 96, 52],
  [0.80, 0.10, 70, 48],
  [0.86, 0.52, 65, 46],
];

// Day markers
const DAY_MARKERS: { stopIdx: number; label: string }[] = [
  { stopIdx: 1, label: "Day 1" },
  { stopIdx: 3, label: "Day 2" },
  { stopIdx: 5, label: "Day 3" },
];

// Itinerary card overlays (show at specific stops)
interface CardOverlay {
  stopIdx: number;
  title: string;
  time: string;
  tag: string;
  tagType: "local" | "busy" | "source" | "start" | "end" | "current";
  image?: string;
  variant?: "you-are-here";
}

const CARD_OVERLAYS: CardOverlay[] = [
  { stopIdx: 0, title: "Tsukiji outer market", time: "06:00 -- 08:30", tag: "Start", tagType: "start", image: "https://images.unsplash.com/photo-1553621042-f6e147245754?w=200&q=70&auto=format&fit=crop" },
  { stopIdx: 3, title: "Harajuku", time: "Day 2 \u00B7 14:30", tag: "You're here", tagType: "current", variant: "you-are-here" },
  { stopIdx: 4, title: "Meiji Shrine", time: "15:30 -- 17:00", tag: "Quiet Hours", tagType: "local" },
  { stopIdx: 6, title: "Standing bar crawl", time: "19:00 -- late", tag: "End", tagType: "end", image: "https://images.unsplash.com/photo-1554797589-7241bb691973?w=200&q=70&auto=format&fit=crop" },
];

/* ------------------------------------------------------------------ */
/*  Bezier utilities                                                   */
/* ------------------------------------------------------------------ */

function quadBezierPoint(
  p0x: number, p0y: number,
  cpx: number, cpy: number,
  p1x: number, p1y: number,
  t: number,
): [number, number] {
  const u = 1 - t;
  return [
    u * u * p0x + 2 * u * t * cpx + t * t * p1x,
    u * u * p0y + 2 * u * t * cpy + t * t * p1y,
  ];
}

function quadBezierLength(
  p0x: number, p0y: number,
  cpx: number, cpy: number,
  p1x: number, p1y: number,
  steps = 64,
): number {
  let len = 0;
  let [px, py] = [p0x, p0y];
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const [nx, ny] = quadBezierPoint(p0x, p0y, cpx, cpy, p1x, p1y, t);
    const dx = nx - px;
    const dy = ny - py;
    len += Math.sqrt(dx * dx + dy * dy);
    px = nx;
    py = ny;
  }
  return len;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function TripMapCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);
  const animStartRef = useRef<number | null>(null);
  const doneRef = useRef(false);
  const cardRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const isDark = useCallback(() => {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrapper = wrapperRef.current;
    if (!canvas || !wrapper) return;

    const ctxOrNull = canvas.getContext("2d");
    if (!ctxOrNull) return;
    const ctx = ctxOrNull;

    // Cache computed style to avoid per-frame style recalc
    let cachedBgStone = getComputedStyle(document.documentElement)
      .getPropertyValue("--bg-stone").trim();
    const themeObs = new MutationObserver(() => {
      cachedBgStone = getComputedStyle(document.documentElement)
        .getPropertyValue("--bg-stone").trim();
      // Redraw canvas with current theme colors
      if (doneRef.current) {
        drawFrame(1);
      }
    });
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    // Reduced motion preference
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---- sizing ---- */
    function resize() {
      const par = canvas!.parentElement;
      if (!par) return;
      const w = par.offsetWidth;
      const h = par.offsetHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = w * dpr;
      canvas!.height = h * dpr;
      canvas!.style.width = `${w}px`;
      canvas!.style.height = `${h}px`;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    }

    /* ---- build route segments ---- */
    function buildSegments(W: number, H: number) {
      const segments: {
        p0x: number; p0y: number;
        cpx: number; cpy: number;
        p1x: number; p1y: number;
        len: number;
      }[] = [];

      for (let i = 0; i < STOPS.length - 1; i++) {
        const s0 = STOPS[i];
        const s1 = STOPS[i + 1];
        const p0x = s0.x * W;
        const p0y = s0.y * H;
        const p1x = s1.x * W;
        const p1y = s1.y * H;
        const mx = (p0x + p1x) / 2;
        const my = (p0y + p1y) / 2;
        const cpx = mx;
        const cpy = my - Math.abs(p1x - p0x) * 0.18;
        const len = quadBezierLength(p0x, p0y, cpx, cpy, p1x, p1y);
        segments.push({ p0x, p0y, cpx, cpy, p1x, p1y, len });
      }

      return segments;
    }

    function easeOut(t: number): number {
      return 1 - Math.pow(1 - t, 3);
    }

    /* ---- draw frame ---- */
    function drawFrame(progress: number) {
      const par = canvas!.parentElement;
      if (!par) return;
      const W = par.offsetWidth;
      const H = par.offsetHeight;
      if (W === 0 || H === 0) return;

      const dark = isDark();

      ctx.clearRect(0, 0, W, H);

      // Background
      if (cachedBgStone) {
        ctx.fillStyle = cachedBgStone;
        ctx.fillRect(0, 0, W, H);
      }

      // Street grid
      const gridSpacing = 52;
      ctx.lineWidth = 5;
      ctx.strokeStyle = dark
        ? "rgba(255,255,255,0.045)"
        : "rgba(0,0,0,0.06)";

      ctx.beginPath();
      for (let y = 0; y < H; y += gridSpacing) {
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
      }
      ctx.stroke();

      ctx.beginPath();
      for (let x = 0; x < W; x += gridSpacing) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
      }
      ctx.stroke();

      // Diagonal avenues
      ctx.beginPath();
      ctx.moveTo(0, H * 0.8);
      ctx.lineTo(W, H * 0.1);
      ctx.moveTo(0, H * 0.3);
      ctx.lineTo(W * 0.7, H);
      ctx.stroke();

      // City blocks
      ctx.fillStyle = dark ? "rgba(26,20,14,0.65)" : "rgba(192,182,170,0.38)";
      for (const [bx, by, bw, bh] of BLOCKS) {
        ctx.fillRect(bx * W, by * H, bw, bh);
      }

      // Build route segments
      const segments = buildSegments(W, H);
      const totalLength = segments.reduce((acc, s) => acc + s.len, 0);
      const drawLength = progress * totalLength;

      // Draw dashed main route up to drawLength
      const routeColor = dark ? "rgba(201,104,72,0.55)" : "rgba(184,92,63,0.5)";
      ctx.strokeStyle = routeColor;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);

      let accumulated = 0;
      for (const seg of segments) {
        if (accumulated >= drawLength) break;

        const segDrawable = Math.min(seg.len, drawLength - accumulated);
        const segFrac = segDrawable / seg.len;

        ctx.beginPath();
        ctx.moveTo(seg.p0x, seg.p0y);
        const steps = 64;
        const maxStep = Math.ceil(segFrac * steps);
        for (let i = 1; i <= maxStep; i++) {
          const t = Math.min(i / steps, segFrac);
          const [px, py] = quadBezierPoint(
            seg.p0x, seg.p0y, seg.cpx, seg.cpy, seg.p1x, seg.p1y, t,
          );
          ctx.lineTo(px, py);
        }
        ctx.stroke();
        accumulated += seg.len;
      }
      ctx.setLineDash([]);

      // --- Pit stop offshoots ---
      const pitStopColor = dark ? "rgba(201,104,72,0.30)" : "rgba(184,92,63,0.28)";
      const pitDotColor = dark ? "rgba(201,104,72,0.5)" : "rgba(184,92,63,0.45)";
      ctx.setLineDash([3, 3]);
      ctx.lineWidth = 1;

      for (const ps of PIT_STOPS) {
        const seg = segments[ps.parentSegIdx];
        if (!seg) continue;
        // Check if route has reached this pit stop's branch point
        let segStart = 0;
        for (let s = 0; s < ps.parentSegIdx; s++) segStart += segments[s].len;
        const branchAt = segStart + seg.len * ps.tOnParent;
        if (drawLength < branchAt) continue;

        // Branch point on main route
        const [bx, by] = quadBezierPoint(
          seg.p0x, seg.p0y, seg.cpx, seg.cpy, seg.p1x, seg.p1y, ps.tOnParent,
        );
        const ex = bx + ps.dx * W;
        const ey = by + ps.dy * H;

        // Fade in after branch point is reached
        const fadeProgress = Math.min(1, (drawLength - branchAt) / 40);

        ctx.globalAlpha = fadeProgress;
        ctx.strokeStyle = pitStopColor;
        ctx.beginPath();
        ctx.moveTo(bx, by);
        // Slight curve to the offshoot
        const cpxOff = (bx + ex) / 2 + ps.dy * W * 0.03;
        const cpyOff = (by + ey) / 2 - ps.dx * H * 0.03;
        ctx.quadraticCurveTo(cpxOff, cpyOff, ex, ey);
        ctx.stroke();

        // Pit stop dot
        ctx.fillStyle = pitDotColor;
        ctx.beginPath();
        ctx.arc(ex, ey, 3, 0, Math.PI * 2);
        ctx.fill();

        // Pit stop label
        ctx.font = "400 7px DM Mono, monospace";
        ctx.fillStyle = dark ? "rgba(201,104,72,0.55)" : "rgba(184,92,63,0.45)";
        ctx.textAlign = ps.dx < 0 ? "right" : "left";
        ctx.fillText(ps.label, ex + (ps.dx < 0 ? -7 : 7), ey + 3);

        ctx.globalAlpha = 1;
      }
      ctx.setLineDash([]);

      // Stop appearance thresholds
      const stopThreshold = (i: number) => i / (STOPS.length - 1);

      // --- Draw stops and labels ---
      for (let i = 0; i < STOPS.length; i++) {
        const threshold = stopThreshold(i);
        if (progress < threshold) continue;

        const stop = STOPS[i];
        const sx = stop.x * W;
        const sy = stop.y * H;
        const fadeIn = Math.min(1, (progress - threshold) / 0.08);

        let fillColor: string;
        let glowColor: string;
        let radius: number;
        let hasGlow = false;

        if (stop.current) {
          // "You are here" — green
          fillColor = dark ? "#5A9E6A" : "#3D7A52";
          glowColor = dark ? "#5A9E6A" : "#3D7A52";
          radius = 9;
          hasGlow = true;
        } else if (stop.start) {
          fillColor = dark ? "#5C4E42" : "#7A6E64";
          glowColor = "";
          radius = 7;
        } else if (stop.end) {
          fillColor = dark ? "#C96848" : "#B85C3F";
          glowColor = dark ? "#C96848" : "#B85C3F";
          radius = 11;
          hasGlow = true;
        } else {
          fillColor = dark ? "#5C4E42" : "#9E9286";
          glowColor = "";
          radius = 5.5;
        }

        ctx.globalAlpha = fadeIn;

        if (hasGlow) {
          const glowR = stop.end ? 20 : 16;
          const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, glowR);
          grad.addColorStop(0, glowColor);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(sx, sy, glowR, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.fillStyle = fillColor;
        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx.fill();

        if (stop.end) {
          // Outer ring stroke
          ctx.beginPath();
          ctx.arc(sx, sy, radius, 0, Math.PI * 2);
          ctx.strokeStyle = fillColor;
          ctx.lineWidth = 1.5;
          ctx.stroke();

          // Inner filled dot
          ctx.beginPath();
          ctx.arc(sx, sy, 6, 0, Math.PI * 2);
          ctx.fillStyle = fillColor;
          ctx.fill();
        }

        // Label
        const isHighlighted = stop.start || stop.end || stop.current;
        ctx.font = isHighlighted
          ? "600 9px Sora, sans-serif"
          : "400 9px Sora, sans-serif";
        ctx.fillStyle = dark
          ? "rgba(240,234,226,0.7)"
          : "rgba(26,22,18,0.65)";

        const labelOnLeft = stop.x > 0.5;
        if (labelOnLeft) {
          ctx.textAlign = "right";
          ctx.fillText(stop.label, sx - radius - 6, sy + 3);
        } else {
          ctx.textAlign = "left";
          ctx.fillText(stop.label, sx + radius + 6, sy + 3);
        }

        ctx.globalAlpha = 1;
      }

      // Day markers
      ctx.font = "400 8px DM Mono, monospace";
      const dayColor = dark ? "rgba(201,104,72,0.8)" : "rgba(184,92,63,0.75)";

      for (const dm of DAY_MARKERS) {
        const threshold = stopThreshold(dm.stopIdx);
        if (progress < threshold) continue;

        const stop = STOPS[dm.stopIdx];
        const sx = stop.x * W;
        const sy = stop.y * H;
        const fadeIn = Math.min(1, (progress - threshold) / 0.08);

        ctx.globalAlpha = fadeIn;
        ctx.fillStyle = dayColor;

        const labelOnLeft = stop.x > 0.5;
        if (labelOnLeft) {
          ctx.textAlign = "right";
          ctx.fillText(dm.label, sx - 14, sy - 10);
        } else {
          ctx.textAlign = "left";
          ctx.fillText(dm.label, sx + 14, sy - 10);
        }
      }

      ctx.globalAlpha = 1;
      ctx.textAlign = "start";

      // --- Position card overlays via DOM ---
      for (const co of CARD_OVERLAYS) {
        const el = cardRefs.current.get(co.stopIdx);
        if (!el) continue;
        const threshold = stopThreshold(co.stopIdx);
        const fadeIn = Math.min(1, Math.max(0, (progress - threshold) / 0.12));
        const stop = STOPS[co.stopIdx];
        const sx = stop.x * W;
        const sy = stop.y * H;

        // Position card offset from stop
        const onLeft = stop.x > 0.55; // Natural left/right based on position
        const cardX = onLeft ? sx - 168 : sx + 18;
        // Harajuku (current/green): push card below pin to avoid Meiji overlap
        const cardY = co.stopIdx === 3 ? sy + 14 : sy - 20;

        el.style.transform = `translate(${cardX}px, ${cardY}px)`;
        el.style.opacity = String(fadeIn);
        el.style.display = fadeIn > 0.01 ? "block" : "none";
      }
    }

    /* ---- animation loop ---- */
    const DURATION_MS = prefersReducedMotion ? 0 : 2800;

    function animate(timestamp: number) {
      if (animStartRef.current === null) {
        animStartRef.current = timestamp;
      }

      const elapsed = timestamp - animStartRef.current;
      const rawProgress = Math.min(elapsed / DURATION_MS, 1);
      const progress = easeOut(rawProgress);

      drawFrame(progress);

      if (rawProgress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        doneRef.current = true;
        if (wrapperRef.current) {
          wrapperRef.current.setAttribute("data-animation-complete", "true");
        }
      }
    }

    function startAnimation() {
      if (doneRef.current) return;
      animStartRef.current = null;
      rafRef.current = requestAnimationFrame(animate);
    }

    resize();
    drawFrame(0);

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !doneRef.current) {
            startAnimation();
            observer.disconnect();
          }
        }
      },
      { threshold: 0.15 },
    );

    document.fonts.ready.then(() => {
      if (canvasRef.current) {
        observer.observe(canvasRef.current);
      }
    });

    function onResize() {
      resize();
      if (doneRef.current) {
        drawFrame(1);
      }
    }

    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(rafRef.current);
      observer.disconnect();
      themeObs.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, [isDark]);

  const tagColors: Record<string, string> = {
    local: "bg-success-bg text-success",
    busy: "bg-warning-bg text-warning",
    source: "bg-info-bg text-info",
    start: "bg-success-bg text-success",
    end: "bg-accent-light text-accent-fg",
    current: "bg-success-bg text-success",
  };

  return (
    <div
      ref={wrapperRef}
      className="absolute inset-0"
      aria-hidden="true"
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />

      {/* Itinerary card overlays */}
      {CARD_OVERLAYS.map((co) => (
        <div
          key={co.stopIdx}
          ref={(el) => {
            if (el) cardRefs.current.set(co.stopIdx, el);
            else cardRefs.current.delete(co.stopIdx);
          }}
          className="absolute pointer-events-none z-[2]"
          style={{
            willChange: "transform, opacity",
            top: 0,
            left: 0,
            opacity: 0,
            display: "none",
          }}
        >
          {co.variant === "you-are-here" ? (
            <div
              className="rounded-[10px] overflow-hidden min-w-[130px] max-w-[155px] border-l-[3px]"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid color-mix(in srgb, var(--ink-700) 60%, transparent)",
                borderLeft: "3px solid var(--success)",
                boxShadow: "var(--shadow-card)",
              }}
            >
              <div className="p-[8px_10px] flex items-center gap-[6px]">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="var(--success)"
                  stroke="none"
                  aria-hidden="true"
                >
                  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z" />
                </svg>
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-medium text-ink-100 leading-tight">
                    {co.title}
                  </div>
                  <div className="font-dm-mono text-[8px] text-success tracking-[0.04em]">
                    {co.time}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="rounded-[10px] overflow-hidden min-w-[130px] max-w-[155px] flex"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid color-mix(in srgb, var(--ink-700) 60%, transparent)",
                boxShadow: "var(--shadow-card)",
              }}
            >
              {co.image && (
                <div className="w-[44px] flex-shrink-0">
                  <img
                    src={co.image}
                    alt=""
                    className="w-full h-full object-cover block"
                  />
                </div>
              )}
              <div className="p-[8px_10px] flex-1 min-w-0">
                <div className="text-[11px] font-medium text-ink-100 mb-[2px] leading-tight truncate">
                  {co.title}
                </div>
                <div className="font-dm-mono text-[8px] text-ink-500 tracking-[0.04em] mb-[4px]">
                  {co.time}
                </div>
                <span
                  className={`font-dm-mono text-[7px] tracking-[0.06em] uppercase px-1.5 py-0.5 rounded-full inline-block ${tagColors[co.tagType]}`}
                >
                  {co.tag}
                </span>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
