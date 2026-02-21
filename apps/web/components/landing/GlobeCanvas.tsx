"use client";

import { useEffect, useRef } from "react";
import {
  latLngToVec3,
  projectPoint,
  resolveCardPositions,
  type ProjectedPoint,
  type CardRect,
} from "./globe-utils";

/* ------------------------------------------------------------------ */
/*  Continent dot-matrix data (~400 [lat, lng] pairs)                  */
/*  Simplified outlines at ~5-degree resolution, decorative only       */
/* ------------------------------------------------------------------ */
const CONTINENT_DOTS: [number, number][] = [
  // North America — East coast
  [48, -53], [47, -56], [46, -60], [45, -64], [44, -66], [43, -70],
  [42, -71], [41, -72], [40, -74], [39, -75], [38, -76], [37, -76],
  [36, -76], [35, -76], [34, -78], [33, -80], [32, -81], [31, -81],
  [30, -82], [29, -83], [28, -82], [27, -80], [26, -80], [25, -80],
  [24, -81], [25, -82], [27, -83], [29, -85], [30, -88], [30, -90],
  [29, -91], [29, -94], [28, -96], [27, -97], [26, -97],
  // North America — Gulf + Mexico
  [24, -98], [22, -98], [20, -97], [19, -96], [18, -95], [17, -93],
  [16, -91], [15, -90], [15, -88], [16, -87], [18, -88], [20, -87],
  [21, -87], [21, -90],
  // North America — West coast
  [32, -117], [34, -118], [35, -121], [37, -122], [38, -123],
  [40, -124], [42, -124], [44, -124], [46, -124], [48, -123],
  [49, -123], [50, -125], [52, -128], [54, -130], [56, -133],
  [58, -134], [60, -140], [61, -147], [63, -152], [65, -163],
  // North America — Northern
  [48, -88], [48, -84], [47, -80], [48, -76], [49, -68], [50, -64],
  [51, -58], [52, -56], [50, -55], [48, -55], [47, -53],
  // Great Lakes outline
  [46, -84], [45, -82], [44, -80], [43, -79], [42, -83], [43, -87],
  [45, -87], [46, -85], [47, -88], [48, -89], [47, -90],
  // North America — fill
  [45, -100], [45, -105], [45, -110], [42, -105], [40, -105],
  [38, -100], [36, -95], [35, -90], [35, -85], [38, -85],
  [40, -80], [42, -78], [44, -75], [40, -95], [38, -90],
  [36, -100], [34, -105], [32, -110], [30, -100], [28, -100],

  // South America
  [12, -72], [10, -75], [8, -77], [7, -77], [5, -77], [3, -77],
  [1, -77], [0, -80], [-2, -80], [-4, -81], [-6, -81], [-8, -79],
  [-10, -78], [-12, -77], [-14, -76], [-16, -73], [-18, -70],
  [-20, -70], [-22, -70], [-24, -70], [-26, -71], [-28, -71],
  [-30, -72], [-33, -72], [-35, -72], [-37, -73], [-40, -73],
  [-42, -74], [-44, -72], [-46, -74], [-48, -74], [-50, -74],
  [-52, -70], [-54, -68],
  // South America — East coast
  [7, -60], [5, -52], [3, -50], [1, -50], [-1, -48], [-3, -45],
  [-5, -36], [-7, -35], [-10, -36], [-13, -39], [-15, -39],
  [-18, -40], [-20, -40], [-22, -41], [-23, -43], [-25, -48],
  [-28, -49], [-30, -51], [-32, -52], [-34, -54], [-35, -57],
  // South America — fill
  [-5, -60], [-5, -50], [-10, -55], [-10, -50], [-15, -55],
  [-15, -50], [-20, -55], [-20, -50], [-25, -55], [-25, -60],
  [-10, -65], [-5, -70], [-15, -65], [-20, -65],

  // Europe
  [36, -6], [37, -8], [38, -9], [40, -9], [42, -9], [43, -9],
  [44, -2], [46, -2], [48, -5], [48, 0], [50, -5], [51, -3],
  [52, 0], [53, 0], [54, -3], [56, -5], [58, -5], [60, 5],
  [62, 6], [64, 10], [66, 14], [68, 16], [70, 20], [70, 26],
  [68, 28], [66, 26], [64, 24], [62, 22], [60, 24], [58, 24],
  [56, 21], [55, 18], [54, 14], [54, 10], [53, 8], [52, 5],
  [50, 5], [48, 8], [46, 6], [44, 8], [42, 3], [40, 0],
  [38, 0], [36, -5],
  // Mediterranean
  [37, 15], [38, 13], [40, 12], [42, 12], [44, 12], [45, 14],
  [44, 15], [42, 18], [40, 18], [38, 22], [36, 22], [35, 24],
  [38, 24], [40, 24], [42, 28], [41, 29], [40, 26], [38, 26],
  [36, 28], [37, 30],
  // Europe — fill
  [50, 10], [50, 15], [50, 20], [48, 12], [48, 18], [46, 14],
  [46, 20], [52, 12], [52, 18], [54, 20], [56, 16],

  // Africa
  [35, -1], [33, -5], [31, -8], [28, -10], [25, -13], [22, -17],
  [18, -16], [15, -17], [12, -16], [8, -13], [5, -5], [4, 2],
  [5, 10], [4, 9], [2, 10], [0, 9], [-2, 12], [-5, 12],
  [-8, 13], [-10, 14], [-12, 14], [-15, 12], [-18, 15],
  [-20, 18], [-22, 17], [-25, 15], [-28, 16], [-30, 18],
  [-32, 18], [-34, 18], [-34, 22], [-34, 26], [-33, 28],
  [-30, 30], [-28, 33], [-25, 35], [-22, 35], [-18, 36],
  [-15, 40], [-12, 42], [-8, 40], [-5, 42], [-2, 42],
  [0, 42], [2, 45], [5, 45], [8, 48], [10, 50], [12, 50],
  [14, 48], [15, 45], [18, 42], [20, 40], [22, 38], [25, 35],
  [28, 33], [30, 32], [32, 32], [35, 10], [34, 3],
  // Africa — fill
  [25, 0], [20, 0], [15, 0], [10, 0], [5, 0], [0, 20],
  [0, 30], [-5, 25], [-5, 30], [-10, 25], [-10, 30], [-15, 25],
  [-15, 30], [-20, 25], [-20, 30], [-25, 25], [10, 10], [10, 20],
  [15, 10], [15, 20], [20, 10], [20, 20], [25, 10], [25, 20],

  // Asia — Middle East + Central
  [35, 35], [33, 44], [30, 48], [25, 45], [22, 50], [25, 55],
  [30, 52], [33, 52], [35, 55], [38, 58], [40, 60], [42, 60],
  [45, 60], [48, 55], [50, 55], [50, 65], [48, 70], [45, 75],
  [42, 75], [40, 70], [38, 65],
  // Asia — South Asia
  [30, 68], [28, 70], [25, 68], [22, 72], [20, 73], [18, 73],
  [15, 74], [12, 75], [10, 77], [8, 77], [10, 80], [15, 80],
  [20, 85], [22, 88], [24, 90], [22, 92], [18, 95], [15, 98],
  [12, 100], [8, 98], [5, 100], [2, 104], [0, 104],
  // Asia — East coast
  [42, 132], [40, 128], [38, 125], [35, 127], [33, 130],
  [30, 122], [28, 120], [25, 118], [22, 114], [20, 110],
  [18, 108], [15, 108], [12, 109], [10, 106],
  // Asia — fill/interior
  [48, 80], [48, 90], [48, 100], [48, 110], [45, 90],
  [45, 100], [45, 110], [42, 80], [42, 90], [42, 100],
  [42, 110], [42, 120], [38, 80], [38, 90], [38, 100],
  [38, 110], [35, 80], [35, 90], [35, 100], [35, 110],
  [30, 80], [30, 90], [30, 100], [30, 110], [25, 100],

  // Japan
  [45, 142], [43, 145], [43, 141], [42, 140], [40, 140],
  [38, 140], [36, 140], [35, 137], [34, 135], [33, 131],
  [32, 131], [30, 130],
  // Korean peninsula
  [38, 127], [37, 127], [36, 127], [35, 129], [34, 127],
  // Southeast Asia
  [20, 106], [18, 103], [15, 101], [12, 103], [8, 100],
  [5, 103], [2, 103], [0, 110], [-2, 107], [-5, 106],
  [-5, 110], [-7, 112], [-8, 115], [-8, 120], [-5, 120],
  [-3, 128], [-5, 135], [-7, 140],

  // Australia
  [-12, 131], [-14, 127], [-16, 123], [-18, 122], [-20, 119],
  [-22, 114], [-25, 114], [-28, 114], [-30, 115], [-32, 116],
  [-34, 116], [-35, 117], [-35, 120], [-35, 125], [-36, 130],
  [-36, 135], [-36, 138], [-35, 140], [-34, 142], [-33, 146],
  [-32, 148], [-30, 150], [-28, 153], [-26, 153], [-24, 152],
  [-22, 150], [-20, 148], [-18, 146], [-16, 146], [-14, 143],
  [-13, 141], [-12, 136], [-12, 131],
  // Australia — fill
  [-22, 125], [-22, 130], [-22, 135], [-22, 140], [-22, 145],
  [-26, 125], [-26, 130], [-26, 135], [-26, 140], [-26, 145],
  [-30, 125], [-30, 130], [-30, 135], [-30, 140],
];

/* ------------------------------------------------------------------ */
/*  City + card data (13 total: 5 featured + 8 minor)                  */
/* ------------------------------------------------------------------ */
interface CityDef {
  lat: number;
  lng: number;
  name: string;
  r: number;
  main: boolean;
  card?: {
    eyebrow: string;
    title: string;
    desc: string;
    tag?: string;
  };
}

const CITIES: CityDef[] = [
  // Featured (5, with tooltip cards) — uniform sizes (Stripe-style)
  {
    lat: 35.67, lng: 139.65, name: "Tokyo", r: 5, main: true,
    card: { eyebrow: "TOKYO \u00B7 DAY 1", title: "Tsukiji outer market", desc: "locals-only \u00B7 06:00 counter", tag: "8.1k local reviews" },
  },
  {
    lat: 35.01, lng: 135.77, name: "Kyoto", r: 5, main: true,
    card: { eyebrow: "KYOTO \u00B7 DAY 3", title: "Kinkaku-ji", desc: "weekday \u00B7 thins out by 15:00", tag: "4.2k local reviews" },
  },
  {
    lat: 37.57, lng: 126.98, name: "Seoul", r: 5, main: true,
    card: { eyebrow: "SEOUL \u00B7 PIVOT", title: "Rain at 14:00", desc: "swapping to indoor alternative" },
  },
  {
    lat: 41.39, lng: 2.17, name: "Barcelona", r: 5, main: true,
    card: { eyebrow: "BARCELONA \u00B7 DAY 2", title: "El Born backstreets", desc: "pre-lunch tapas crawl", tag: "Local" },
  },
  {
    lat: 34.69, lng: 135.50, name: "Osaka", r: 5, main: true,
    card: { eyebrow: "OSAKA \u00B7 NIGHT", title: "Dotonbori standing bar", desc: "walk-ins only before 18:00", tag: "5.6k local reviews" },
  },
  // Minor dots — uniform size
  { lat: 38.72, lng: -9.14, name: "Lisbon", r: 3, main: false },
  { lat: 41.01, lng: 28.98, name: "Istanbul", r: 3, main: false },
  { lat: 31.63, lng: -8.00, name: "Marrakech", r: 2.5, main: false },
  { lat: 25.03, lng: 121.57, name: "Taipei", r: 3, main: false },
  { lat: 10.82, lng: 106.63, name: "HCMC", r: 2.5, main: false },
  { lat: 19.43, lng: -99.13, name: "MexicoCity", r: 2.5, main: false },
  { lat: -34.60, lng: -58.38, name: "BuenosAires", r: 2.5, main: false },
  { lat: -33.87, lng: 151.21, name: "Sydney", r: 3, main: false },
];

/* ------------------------------------------------------------------ */
/*  Heatmap scatter dots near featured cities                          */
/*  Denser + bigger near city center, fading outward                   */
/* ------------------------------------------------------------------ */
function generateHeatmapDots(): { lat: number; lng: number; r: number }[] {
  const dots: { lat: number; lng: number; r: number }[] = [];
  // Deterministic scatter using simple hash
  const featured = CITIES.filter((c) => c.main);
  for (const city of featured) {
    // Inner ring (3-5 dots, close, bigger)
    const innerCount = 4;
    for (let i = 0; i < innerCount; i++) {
      const angle = (Math.PI * 2 * i) / innerCount + city.lat * 0.1;
      const dist = 1.2 + (i % 3) * 0.4;
      dots.push({
        lat: city.lat + Math.sin(angle) * dist,
        lng: city.lng + Math.cos(angle) * dist * 1.3,
        r: 2.2 + (i % 2) * 0.4,
      });
    }
    // Outer ring (5-7 dots, farther, smaller)
    const outerCount = 6;
    for (let i = 0; i < outerCount; i++) {
      const angle = (Math.PI * 2 * i) / outerCount + city.lng * 0.05;
      const dist = 2.8 + (i % 4) * 0.8;
      dots.push({
        lat: city.lat + Math.sin(angle) * dist,
        lng: city.lng + Math.cos(angle) * dist * 1.3,
        r: 1.4 + (i % 3) * 0.3,
      });
    }
  }
  return dots;
}

const HEATMAP_DOTS = generateHeatmapDots();
const HEATMAP_VECS = HEATMAP_DOTS.map((d) => latLngToVec3(d.lat, d.lng));

const ROUTES: [number, number][] = [
  [0, 2],  // Tokyo → Seoul
  [2, 8],  // Seoul → Taipei
  [4, 9],  // Osaka → HCMC
];

const ROUTE_DASH = [5, 3];

/* ------------------------------------------------------------------ */
/*  Card lerp state — persistent across frames                        */
/* ------------------------------------------------------------------ */
interface LerpCard {
  targetX: number;
  targetY: number;
  displayX: number;
  displayY: number;
  opacity: number;
  visible: boolean;
  cityIdx: number;
}

/* ------------------------------------------------------------------ */
/*  Pre-compute Vec3 for all static data                              */
/* ------------------------------------------------------------------ */
const CONTINENT_VECS = CONTINENT_DOTS.map(([la, ln]) => latLngToVec3(la, ln));
const CITY_VECS = CITIES.map((c) => latLngToVec3(c.lat, c.lng));

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function GlobeCanvas({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);
  const rotRef = useRef(2.36); // initial rotation: East Asia facing (Tokyo z2=+0.56, Seoul +0.53, Osaka +0.58)
  const tRef = useRef(0);
  const isRunningRef = useRef(false);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const isDarkRef = useRef(false);
  const cardElemRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const lerpCardsRef = useRef<LerpCard[]>([]);
  const lastCardUpdateRef = useRef(0);

  // Cached gradients (recreated on resize only)
  const cachedGradientsRef = useRef<{
    ambient: CanvasGradient | null;
    sphere: CanvasGradient | null;
    cx: number;
    cy: number;
    R: number;
  }>({ ambient: null, sphere: null, cx: 0, cy: 0, R: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctxOrNull = canvas.getContext("2d");
    if (!ctxOrNull) return;
    const ctx = ctxOrNull; // narrowed to non-null for closures
    ctxRef.current = ctx;

    // Reduced motion preference
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Theme observer — cache isDark, no DOM read per frame
    isDarkRef.current = document.documentElement.getAttribute("data-theme") === "dark";
    const themeObserver = new MutationObserver(() => {
      isDarkRef.current = document.documentElement.getAttribute("data-theme") === "dark";
      // Invalidate cached gradients on theme change
      cachedGradientsRef.current.ambient = null;
      cachedGradientsRef.current.sphere = null;
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    // Resize handler with DPR scaling
    let W = 0;
    let H = 0;

    function resize() {
      const par = canvas!.parentElement;
      if (!par) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = par.offsetWidth;
      const h = par.offsetHeight;
      if (w === 0 || h === 0) return;
      canvas!.width = w * dpr;
      canvas!.height = h * dpr;
      canvas!.style.width = w + "px";
      canvas!.style.height = h + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      W = w;
      H = h;
      // Invalidate cached gradients
      cachedGradientsRef.current.ambient = null;
      cachedGradientsRef.current.sphere = null;
    }

    // Projected city results — pre-allocated, mutated in-place
    const projectedCities: (ProjectedPoint & { r: number; main: boolean })[] =
      CITIES.map((c) => ({ x: 0, y: 0, z: 0, vis: false, r: c.r, main: c.main }));

    function frame() {
      if (!isRunningRef.current) return;
      if (W === 0 || H === 0) {
        rafRef.current = requestAnimationFrame(frame);
        return;
      }

      const dark = isDarkRef.current;
      const rotation = rotRef.current;
      const t = tRef.current;

      // Globe positioning — offset right, capped for ultrawide
      const cx = Math.min(W, 1600) * 0.72;
      const cy = H * 0.52;
      const R = H * 0.58;

      ctx.clearRect(0, 0, W, H);

      // --- Ambient glow (cached) ---
      if (!cachedGradientsRef.current.ambient || cachedGradientsRef.current.cx !== cx || cachedGradientsRef.current.cy !== cy || cachedGradientsRef.current.R !== R) {
        const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5);
        bg.addColorStop(0, dark ? "rgba(201,104,72,0.05)" : "rgba(184,92,63,0.05)");
        bg.addColorStop(1, "rgba(0,0,0,0)");
        cachedGradientsRef.current.ambient = bg;

        const g = ctx.createRadialGradient(cx - R * 0.2, cy - R * 0.2, 0, cx, cy, R);
        g.addColorStop(0, dark ? "rgba(44,36,26,0.35)" : "rgba(220,212,200,0.35)");
        g.addColorStop(1, dark ? "rgba(18,14,9,0.08)" : "rgba(210,200,188,0.12)");
        cachedGradientsRef.current.sphere = g;

        cachedGradientsRef.current.cx = cx;
        cachedGradientsRef.current.cy = cy;
        cachedGradientsRef.current.R = R;
      }

      ctx.fillStyle = cachedGradientsRef.current.ambient!;
      ctx.fillRect(0, 0, W, H);

      // --- Globe sphere ---
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = cachedGradientsRef.current.sphere!;
      ctx.fill();
      ctx.strokeStyle = dark ? "rgba(201,104,72,0.15)" : "rgba(184,92,63,0.18)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // --- Grid lines ---
      ctx.globalAlpha = dark ? 0.12 : 0.14;
      ctx.strokeStyle = dark ? "rgba(240,234,226,0.5)" : "rgba(26,22,18,0.35)";
      ctx.lineWidth = 0.5;
      for (let la = -60; la <= 60; la += 30) {
        const rL = Math.cos((la * Math.PI) / 180) * R;
        const yL = cy - Math.sin((la * Math.PI) / 180) * R;
        ctx.beginPath();
        ctx.ellipse(cx, yL, rL, rL * 0.11, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
      for (let ln = 0; ln < 360; ln += 30) {
        const a = projectPoint(latLngToVec3(70, ln), cx, cy, R, rotation);
        const b = projectPoint(latLngToVec3(-70, ln), cx, cy, R, rotation);
        if (a.vis && b.vis) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;

      // --- Continent dots (batched single path) ---
      const contDotColor = dark ? "rgba(201,104,72,0.22)" : "rgba(184,92,63,0.30)";
      ctx.fillStyle = contDotColor;
      ctx.beginPath();
      for (let i = 0; i < CONTINENT_VECS.length; i++) {
        const p = projectPoint(CONTINENT_VECS[i], cx, cy, R, rotation);
        if (p.z > -0.1) {
          ctx.moveTo(p.x + 1.8, p.y);
          ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2);
        }
      }
      ctx.fill();

      // --- Heatmap scatter dots (denser near cities) ---
      const heatColor = dark ? "rgba(201,104,72,0.35)" : "rgba(184,92,63,0.32)";
      ctx.fillStyle = heatColor;
      ctx.beginPath();
      for (let i = 0; i < HEATMAP_VECS.length; i++) {
        const p = projectPoint(HEATMAP_VECS[i], cx, cy, R, rotation);
        if (p.z > -0.05) {
          const r = HEATMAP_DOTS[i].r;
          ctx.moveTo(p.x + r, p.y);
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        }
      }
      ctx.fill();

      // --- Project cities (in-place mutation) ---
      for (let i = 0; i < CITY_VECS.length; i++) {
        const p = projectPoint(CITY_VECS[i], cx, cy, R, rotation);
        projectedCities[i].x = p.x;
        projectedCities[i].y = p.y;
        projectedCities[i].z = p.z;
        projectedCities[i].vis = p.vis;
      }

      // --- Routes ---
      ctx.setLineDash(ROUTE_DASH);
      ROUTES.forEach((r, i) => {
        const a = projectedCities[r[0]];
        const b = projectedCities[r[1]];
        if (!a.vis || !b.vis) return;
        const al = 0.4 + 0.2 * Math.sin(t * 0.018 + i);
        ctx.strokeStyle = dark ? `rgba(201,104,72,${al})` : `rgba(184,92,63,${al})`;
        ctx.lineWidth = 1.5;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const arcH = Math.max(18, dist * 0.18);
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2 - arcH;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        ctx.stroke();
      });
      ctx.setLineDash([]);

      // --- City dots ---
      projectedCities.forEach((c, i) => {
        if (!c.vis) return;
        if (c.main) {
          // Subtle steady glow — no pulse animation (Stripe-style)
          const glOuter = ctx.createRadialGradient(c.x, c.y, c.r * 0.5, c.x, c.y, c.r + 8);
          glOuter.addColorStop(0, dark ? "rgba(201,104,72,0.25)" : "rgba(184,92,63,0.22)");
          glOuter.addColorStop(1, "rgba(0,0,0,0)");
          ctx.beginPath();
          ctx.arc(c.x, c.y, c.r + 8, 0, Math.PI * 2);
          ctx.fillStyle = glOuter;
          ctx.fill();
        }

        const cr = c.main ? c.r : c.r * 0.6;
        ctx.beginPath();
        ctx.arc(c.x, c.y, cr, 0, Math.PI * 2);
        ctx.fillStyle = c.main
          ? dark ? "#C96848" : "#B85C3F"
          : dark ? "rgba(201,104,72,0.4)" : "rgba(184,92,63,0.35)";
        ctx.fill();
        ctx.strokeStyle = dark ? "rgba(14,12,9,0.85)" : "rgba(250,248,245,0.95)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      // --- Card positions (time-based throttle: every ~32ms) ---
      const now = performance.now();
      if (now - lastCardUpdateRef.current >= 32) {
        lastCardUpdateRef.current = now;

        // Build raw card rects for visible featured cities
        const rawCards: CardRect[] = [];
        const cardCityIndices: number[] = [];
        projectedCities.forEach((c, i) => {
          if (!c.main || !CITIES[i].card) return;
          const vis = c.z > 0.3;
          if (vis) {
            rawCards.push({
              x: c.x + 18,
              y: c.y - 30,
              width: 160,
              height: 72,
              cityIdx: i,
            });
            cardCityIndices.push(i);
          }
        });

        // Anti-collision
        const resolved = resolveCardPositions(rawCards, { width: W, height: H });

        // Draw leader lines on canvas
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        resolved.forEach((card, ci) => {
          const city = projectedCities[card.cityIdx];
          ctx.strokeStyle = dark ? "rgba(201,104,72,0.3)" : "rgba(184,92,63,0.35)";
          ctx.beginPath();
          ctx.moveTo(city.x, city.y);
          const cpx = (city.x + card.x) / 2;
          const cpy = city.y - 15;
          ctx.quadraticCurveTo(cpx, cpy, card.x, card.y + card.height / 2);
          ctx.stroke();
        });
        ctx.setLineDash([]);

        // Update lerp targets
        const newLerp: LerpCard[] = [];
        const featuredIndices = CITIES.map((c, i) => c.main && c.card ? i : -1).filter(i => i >= 0);

        featuredIndices.forEach((cityIdx) => {
          const resolvedCard = resolved.find((r) => r.cityIdx === cityIdx);
          const city = projectedCities[cityIdx];
          const vis = city.z > 0.3;
          const opacity = vis ? Math.min(0.92, city.z * 2.5) : 0;

          const existing = lerpCardsRef.current.find((l) => l.cityIdx === cityIdx);
          if (existing) {
            existing.targetX = resolvedCard ? resolvedCard.x : city.x + 18;
            existing.targetY = resolvedCard ? resolvedCard.y : city.y - 30;
            existing.visible = vis;
            // Lerp opacity
            existing.opacity += (opacity - existing.opacity) * 0.12;
            newLerp.push(existing);
          } else {
            const tx = resolvedCard ? resolvedCard.x : city.x + 18;
            const ty = resolvedCard ? resolvedCard.y : city.y - 30;
            newLerp.push({
              targetX: tx, targetY: ty,
              displayX: tx, displayY: ty,
              opacity, visible: vis, cityIdx,
            });
          }
        });
        lerpCardsRef.current = newLerp;
      }

      // --- Lerp card positions every frame ---
      lerpCardsRef.current.forEach((card) => {
        card.displayX += (card.targetX - card.displayX) * 0.12;
        card.displayY += (card.targetY - card.displayY) * 0.12;

        // Apply to DOM directly
        const el = cardElemRefs.current.get(card.cityIdx);
        if (el) {
          el.style.transform = `translate(${card.displayX}px, ${card.displayY}px)`;
          el.style.opacity = String(Math.max(0, card.opacity));
          el.style.display = card.opacity > 0.01 ? "block" : "none";
        }
      });

      if (!prefersReducedMotion) {
        tRef.current++;
        rotRef.current += 0.0008;
      }
      rafRef.current = requestAnimationFrame(frame);
    }

    // --- Start/stop loop ---
    function startLoop() {
      if (isRunningRef.current) return;
      isRunningRef.current = true;
      rafRef.current = requestAnimationFrame(frame);
    }

    function stopLoop() {
      isRunningRef.current = false;
      cancelAnimationFrame(rafRef.current);
    }

    // --- Init ---
    resize();

    // IntersectionObserver — pause when offscreen
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) startLoop();
        else stopLoop();
      },
      { threshold: 0.01 },
    );
    io.observe(canvas);

    // Visibility change — pause when tab backgrounded
    const onVisChange = () => {
      if (document.hidden) stopLoop();
      // Don't auto-restart — IO will handle it when visible
    };
    document.addEventListener("visibilitychange", onVisChange);

    // Resize
    const onResize = () => {
      resize();
    };
    window.addEventListener("resize", onResize);

    return () => {
      stopLoop();
      io.disconnect();
      themeObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisChange);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  // Build featured city list for JSX (rendered once, positioned via refs)
  const featuredCities = CITIES.map((c, i) => ({ city: c, idx: i })).filter(
    ({ city }) => city.main && city.card,
  );

  return (
    <div
      ref={wrapperRef}
      className={`absolute inset-0 w-full h-full ${className}`}
      style={{ position: "absolute" }}
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      {/* Tooltip card overlays — rendered once, positioned via direct DOM mutation */}
      {featuredCities.map(({ city, idx }) => (
        <div
          key={city.name}
          ref={(el) => {
            if (el) cardElemRefs.current.set(idx, el);
            else cardElemRefs.current.delete(idx);
          }}
          className="absolute pointer-events-none z-[4]"
          style={{
            willChange: "transform, opacity",
            top: 0,
            left: 0,
            opacity: 0,
            display: "none",
          }}
        >
          <div className="rounded-[14px] shadow-lg p-[10px_14px] min-w-[140px] max-w-[180px]"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid color-mix(in srgb, var(--ink-700) 60%, transparent)",
              borderRadius: "14px",
              boxShadow: "var(--shadow-card)",
              maxWidth: "180px",
            }}
          >
            <div className="font-dm-mono text-[8px] tracking-[0.1em] uppercase text-accent-fg mb-[3px]">
              {city.card!.eyebrow}
            </div>
            <div className="text-[12px] font-medium text-ink-100 mb-[2px] whitespace-nowrap">
              {city.card!.title}
            </div>
            <div className="text-[10px] text-ink-400 font-light italic whitespace-nowrap">
              {city.card!.desc}
            </div>
            {city.card!.tag && (
              <span className="font-dm-mono text-[8px] text-info bg-info-bg px-1.5 py-0.5 rounded-full inline-block mt-[5px]">
                {city.card!.tag}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
