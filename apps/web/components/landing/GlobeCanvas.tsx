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
/*  City data                                                           */
/* ------------------------------------------------------------------ */
// Silent dots — unnamed tiny circles for global geographic density
// Spread across underrepresented regions so city dots imply world geography
const SILENT_DOTS: [number, number][] = [
  // Africa
  [6, 3],       // Lagos area
  [9, 38],      // Addis Ababa area
  [-6, 35],     // Dar es Salaam area
  [-26, 28],    // Johannesburg area
  [34, -7],     // Casablanca area
  [30, 31],     // Cairo area
  [-4, 15],     // Kinshasa area
  // Central/South Asia
  [28, 77],     // Delhi area
  [22, 70],     // Karachi area
  [24, 90],     // Dhaka area
  [40, 65],     // Central Asia
  [42, 59],     // Turkmenistan
  // Middle East
  [25, 55],     // Dubai area
  [33, 44],     // Baghdad area
  // South America
  [-12, -77],   // Lima area
  [-33, -71],   // Santiago area
  [-15, -48],   // Brasilia area
  [5, -74],     // Bogota area
  [10, -67],    // Caracas area
  // North America
  [45, -75],    // Ottawa area
  [19, -99],    // Mexico City (already named, skip — use Havana)
  [23, -82],    // Havana area
  [49, -123],   // Vancouver area
  // Oceania / Pacific
  [-37, 175],   // Auckland area
  [-8, 112],    // Jakarta area
  [14, 121],    // Manila area
  // Europe fill
  [55, 37],     // Moscow area
  [52, 21],     // Warsaw area
  [59, 18],     // Stockholm area
  [38, 24],     // Athens area
  // East Asia fill
  [22, 114],    // Hong Kong area
  [39, 116],    // Beijing area
  [31, 121],    // Shanghai area
  // West coast / Pacific NW
  [45, -123],   // Portland (Seattle now a named city)
  [37, -122],   // SF area
  [33, -117],   // San Diego area
  [45, -123],   // Portland area
  // Mexico / Central America
  [21, -104],   // Guadalajara area
  [25, -100],   // Monterrey area
  [15, -90],    // Guatemala City area
  [9, -84],     // Costa Rica area
  [9, -79],     // Panama area
  [20, -88],    // Cancun area
  // Alaska / Northern Pacific
  [64, -148],   // Fairbanks area
  [57, -135],   // Juneau area
  // Northern / Central Asia
  [55, 73],     // Omsk area
  [56, 93],     // Krasnoyarsk area
  [52, 104],    // Irkutsk area
  [62, 130],    // Yakutsk area
  [48, 68],     // Kazakhstan area
  [43, 77],     // Almaty area
  [53, 158],    // Kamchatka area
  // India interior
  [13, 80],     // Chennai area
  [23, 72],     // Ahmedabad area
  [26, 81],     // Lucknow area
  [17, 78],     // Hyderabad area
  [13, 75],     // Bangalore area
  // Inner Eurasia
  [41, 69],     // Tashkent area
  [38, 58],     // Ashgabat area
  [47, 52],     // Caspian area
  [50, 57],     // Orenburg area
  [45, 40],     // Caucasus area
  // Middle East → Egypt corridor
  [32, 36],     // Amman area
  [24, 46],     // Riyadh area
  [27, 30],     // Upper Egypt
  [21, 40],     // Jeddah area
  [36, 43],     // Mosul area
  // Northern Europe / Scandinavia
  [57, -4],     // Scottish Highlands
  [60, 11],     // Oslo area
  [63, 10],     // Trondheim area
  [65, 25],     // Finnish Lapland
  [56, 12],     // Copenhagen area
  [54, -6],     // Belfast area
  [53, -9],     // West Ireland
];

/* ------------------------------------------------------------------ */
/*  City + card data (21 named: 6 featured + 15 minor)                 */
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
  };
}

const CITIES: CityDef[] = [
  // Featured (6, with tooltip cards) — globally distributed
  {
    lat: 35.67, lng: 139.65, name: "Tokyo", r: 5, main: true,
    card: { eyebrow: "TOKYO \u00B7 3 TRIPS", title: "14 days total", desc: "Last: Pontocho standing bar" },
  },
  {
    lat: 41.39, lng: 2.17, name: "Barcelona", r: 5, main: true,
    card: { eyebrow: "BARCELONA \u00B7 2 TRIPS", title: "11 days total", desc: "Most revisited: El Born" },
  },
  {
    lat: 40.71, lng: -74.01, name: "NewYork", r: 5, main: true,
    card: { eyebrow: "NEW YORK \u00B7 1 TRIP", title: "6 days", desc: "Best: Izakaya on St Marks" },
  },
  {
    lat: -34.60, lng: -58.38, name: "BuenosAires", r: 5, main: true,
    card: { eyebrow: "BUENOS AIRES \u00B7 1 TRIP", title: "8 days", desc: "San Telmo on a Sunday" },
  },
  {
    lat: -33.93, lng: 18.42, name: "CapeTown", r: 5, main: true,
    card: { eyebrow: "CAPE TOWN \u00B7 1 TRIP", title: "5 days", desc: "Bo-Kaap at golden hour" },
  },
  {
    lat: -33.87, lng: 151.21, name: "Sydney", r: 5, main: true,
    card: { eyebrow: "SYDNEY \u00B7 2 TRIPS", title: "9 days total", desc: "Enmore Road food crawl" },
  },
  // Minor dots — no tooltips, globally distributed
  { lat: 38.72, lng: -9.14, name: "Lisbon", r: 3.5, main: false },
  { lat: 41.01, lng: 28.98, name: "Istanbul", r: 3.5, main: false },
  { lat: 31.63, lng: -8.00, name: "Marrakech", r: 3, main: false },
  { lat: 25.03, lng: 121.57, name: "Taipei", r: 3.5, main: false },
  { lat: 10.82, lng: 106.63, name: "HCMC", r: 3, main: false },
  { lat: 19.43, lng: -99.13, name: "MexicoCity", r: 3, main: false },
  { lat: 35.01, lng: 135.77, name: "Kyoto", r: 3, main: false },
  { lat: 37.57, lng: 126.98, name: "Seoul", r: 3.5, main: false },
  { lat: 34.69, lng: 135.50, name: "Osaka", r: 3, main: false },
  // Additional spread — fill geographic gaps
  { lat: 13.76, lng: 100.50, name: "Bangkok", r: 4, main: true,
    card: { eyebrow: "BANGKOK \u00B7 2 TRIPS", title: "10 days total", desc: "Chinatown yaowarat at 1am" },
  },
  { lat: -1.29, lng: 36.82, name: "Nairobi", r: 3, main: false },
  { lat: 51.51, lng: -0.13, name: "London", r: 3.5, main: false },
  { lat: 48.86, lng: 2.35, name: "Paris", r: 3.5, main: false },
  { lat: -22.91, lng: -43.17, name: "Rio", r: 3, main: false },
  { lat: 1.35, lng: 103.82, name: "Singapore", r: 3, main: false },
  { lat: 34.05, lng: -118.24, name: "LA", r: 3.5, main: false },
  { lat: 61.22, lng: -149.90, name: "Anchorage", r: 4, main: true,
    card: { eyebrow: "ANCHORAGE \u00B7 1 TRIP", title: "4 days", desc: "Midnight sun hike to Flattop" },
  },
  { lat: 59.93, lng: 30.32, name: "StPetersburg", r: 4, main: true,
    card: { eyebrow: "ST PETERSBURG \u00B7 1 TRIP", title: "5 days", desc: "White nights along the Neva" },
  },
  { lat: 21.31, lng: -157.86, name: "Honolulu", r: 4, main: true,
    card: { eyebrow: "HONOLULU \u00B7 1 TRIP", title: "7 days", desc: "North Shore shrimp truck loop" },
  },
  { lat: 47.92, lng: 106.91, name: "Ulaanbaatar", r: 4, main: true,
    card: { eyebrow: "ULAANBAATAR \u00B7 1 TRIP", title: "8 days", desc: "Ger camp under frozen stars" },
  },
  { lat: 47.61, lng: -122.33, name: "Seattle", r: 3.5, main: false },
  { lat: 19.08, lng: 72.88, name: "Mumbai", r: 3.5, main: false },
];

/* ------------------------------------------------------------------ */
/*  Fibonacci sphere — even density across entire globe surface         */
/*  ~150 tiny dots as ambient texture, no geography needed              */
/* ------------------------------------------------------------------ */
function generateFibSphere(n: number): { lat: number; lng: number }[] {
  const pts: { lat: number; lng: number }[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2; // -1 to 1
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    const lat = Math.asin(y) * (180 / Math.PI);
    const lng = ((theta * 180) / Math.PI) % 360 - 180;
    pts.push({ lat, lng });
  }
  return pts;
}

const FIB_DOTS = generateFibSphere(160);
const FIB_VECS = FIB_DOTS.map((d) => latLngToVec3(d.lat, d.lng));

/* ------------------------------------------------------------------ */
/*  Heatmap scatter dots near ALL cities (not just featured)           */
/*  Featured get 3 rings, minor get 2 rings                            */
/* ------------------------------------------------------------------ */
function generateHeatmapDots(): { lat: number; lng: number; r: number }[] {
  const dots: { lat: number; lng: number; r: number }[] = [];
  for (const city of CITIES) {
    // Inner ring — all cities get this
    const innerCount = city.main ? 5 : 3;
    for (let i = 0; i < innerCount; i++) {
      const angle = (Math.PI * 2 * i) / innerCount + city.lat * 0.1;
      const dist = 1.0 + (i % 3) * 0.5;
      dots.push({
        lat: city.lat + Math.sin(angle) * dist,
        lng: city.lng + Math.cos(angle) * dist * 1.3,
        r: city.main ? 2.4 + (i % 2) * 0.5 : 1.8 + (i % 2) * 0.3,
      });
    }
    // Outer ring
    const outerCount = city.main ? 8 : 4;
    for (let i = 0; i < outerCount; i++) {
      const angle = (Math.PI * 2 * i) / outerCount + city.lng * 0.05;
      const dist = 2.5 + (i % 4) * 0.9;
      dots.push({
        lat: city.lat + Math.sin(angle) * dist,
        lng: city.lng + Math.cos(angle) * dist * 1.3,
        r: city.main ? 1.6 + (i % 3) * 0.4 : 1.2 + (i % 2) * 0.3,
      });
    }
    // Far scatter — featured cities only
    if (city.main) {
      const farCount = 6;
      for (let i = 0; i < farCount; i++) {
        const angle = (Math.PI * 2 * i) / farCount + (city.lat + city.lng) * 0.03;
        const dist = 5 + (i % 3) * 2;
        dots.push({
          lat: city.lat + Math.sin(angle) * dist,
          lng: city.lng + Math.cos(angle) * dist * 1.2,
          r: 1.0 + (i % 2) * 0.4,
        });
      }
    }
  }
  return dots;
}

const HEATMAP_DOTS = generateHeatmapDots();
const HEATMAP_VECS = HEATMAP_DOTS.map((d) => latLngToVec3(d.lat, d.lng));

/* ------------------------------------------------------------------ */
/*  Routes — intercontinental arcs connecting the network               */
/* ------------------------------------------------------------------ */
const ROUTES: [number, number][] = [
  // Pacific chain
  [24, 0],  // Honolulu → Tokyo
  [21, 24], // LA → Honolulu
  [0, 5],   // Tokyo → Sydney
  [9, 5],   // Taipei → Sydney
  // Arctic arc
  [22, 23], // Anchorage → StPetersburg
  // Atlantic & Americas
  [17, 2],  // London → NewYork
  [2, 11],  // NewYork → MexicoCity
  [11, 3],  // MexicoCity → BuenosAires
  [3, 4],   // BuenosAires → CapeTown
  [6, 19],  // Lisbon → Rio
  // Africa & Middle East
  [4, 16],  // CapeTown → Nairobi
  [16, 7],  // Nairobi → Istanbul
  [18, 8],  // Paris → Marrakech
  [7, 23],  // Istanbul → StPetersburg
  // Asia & Indian Ocean
  [15, 27], // Bangkok → Mumbai
  [13, 10], // Seoul → HCMC
  [20, 16], // Singapore → Nairobi
  [15, 5],  // Bangkok → Sydney
  // East Asia hops
  [14, 9],  // Osaka → Taipei
  [12, 13], // Kyoto → Seoul
  [23, 25], // StPetersburg → Ulaanbaatar
  [2, 26],  // NewYork → Seattle
  [27, 1],  // Mumbai → Barcelona
];

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
const SILENT_VECS = SILENT_DOTS.map(([la, ln]) => latLngToVec3(la, ln));
const CITY_VECS = CITIES.map((c) => latLngToVec3(c.lat, c.lng));

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function GlobeCanvas({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);
  const rotRef = useRef(4.9);
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
      const cy = H > 600 ? H * 0.55 : H * 0.48;
      const R = H * 0.48;

      ctx.clearRect(0, 0, W, H);

      // --- Ambient glow (cached) ---
      if (!cachedGradientsRef.current.ambient || cachedGradientsRef.current.cx !== cx || cachedGradientsRef.current.cy !== cy || cachedGradientsRef.current.R !== R) {
        const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5);
        bg.addColorStop(0, dark ? "rgba(201,104,72,0.05)" : "rgba(184,92,63,0.08)");
        bg.addColorStop(1, "rgba(0,0,0,0)");
        cachedGradientsRef.current.ambient = bg;

        const g = ctx.createRadialGradient(cx - R * 0.2, cy - R * 0.2, 0, cx, cy, R);
        g.addColorStop(0, dark ? "rgba(44,36,26,0.35)" : "rgba(180,168,152,0.40)");
        g.addColorStop(1, dark ? "rgba(18,14,9,0.08)" : "rgba(165,152,136,0.18)");
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
      ctx.strokeStyle = dark ? "rgba(201,104,72,0.15)" : "rgba(160,88,60,0.35)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // --- Grid lines ---
      ctx.globalAlpha = dark ? 0.12 : 0.18;
      ctx.strokeStyle = dark ? "rgba(240,234,226,0.5)" : "rgba(26,22,18,0.40)";
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

      // --- Fibonacci star-field (ambient globe texture) ---
      ctx.fillStyle = dark ? "rgba(201,104,72,0.14)" : "rgba(196,105,79,0.18)";
      ctx.beginPath();
      for (let i = 0; i < FIB_VECS.length; i++) {
        const p = projectPoint(FIB_VECS[i], cx, cy, R, rotation);
        if (p.z < -0.1) continue;
        const depthFade = Math.max(0, Math.min(1, (p.z + 0.1) * 1.1));
        const r = 1.2 * depthFade;
        ctx.moveTo(p.x + r, p.y);
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      }
      ctx.fill();

      // --- Silent dots (named geographic density markers) ---
      ctx.fillStyle = dark ? "rgba(201,104,72,0.30)" : "rgba(196,105,79,0.40)";
      ctx.beginPath();
      for (let i = 0; i < SILENT_VECS.length; i++) {
        const p = projectPoint(SILENT_VECS[i], cx, cy, R, rotation);
        if (p.z < -0.12) continue;
        const depthFade = Math.max(0, Math.min(1, (p.z + 0.12) * 1.2));
        const r = 2.2 * depthFade;
        ctx.moveTo(p.x + r, p.y);
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      }
      ctx.fill();

      // --- Heatmap scatter dots (denser near cities) ---
      ctx.fillStyle = dark ? "rgba(201,104,72,0.35)" : "rgba(196,105,79,0.50)";
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

      // --- Routes (solid lines + traveling pulse dots) ---
      ROUTES.forEach((r, i) => {
        const a = projectedCities[r[0]];
        const b = projectedCities[r[1]];
        if (!a.vis || !b.vis) return;
        const al = 0.28 + 0.14 * Math.sin(t * 0.018 + i);
        ctx.strokeStyle = dark ? `rgba(201,104,72,${al})` : `rgba(196,105,79,${Math.min(1, al + 0.15)})`;
        ctx.lineWidth = 1.0;
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

        // Traveling pulse dot — each route has its own phase offset
        // Quadratic bezier: P(t) = (1-t)^2*A + 2(1-t)*t*CP + t^2*B
        const speed = 0.0008 + (i % 3) * 0.0002; // slight speed variation
        const phase = ((t * speed + i * 0.28) % 1);
        const omt = 1 - phase;
        const px = omt * omt * a.x + 2 * omt * phase * mx + phase * phase * b.x;
        const py = omt * omt * a.y + 2 * omt * phase * my + phase * phase * b.y;
        const pulseR = 2.5;
        const pulseAlpha = 0.6 + 0.2 * Math.sin(phase * Math.PI); // brightest at midpoint
        ctx.beginPath();
        ctx.arc(px, py, pulseR, 0, Math.PI * 2);
        ctx.fillStyle = dark
          ? `rgba(201,104,72,${pulseAlpha})`
          : `rgba(196,105,79,${Math.min(1, pulseAlpha + 0.15)})`;
        ctx.fill();
      });

      // --- City dots ---
      projectedCities.forEach((c, i) => {
        if (!c.vis) return;
        if (c.main) {
          // Subtle steady glow — no pulse animation (Stripe-style)
          const glOuter = ctx.createRadialGradient(c.x, c.y, c.r * 0.5, c.x, c.y, c.r + 8);
          glOuter.addColorStop(0, dark ? "rgba(201,104,72,0.25)" : "rgba(196,105,79,0.35)");
          glOuter.addColorStop(1, "rgba(0,0,0,0)");
          ctx.beginPath();
          ctx.arc(c.x, c.y, c.r + 8, 0, Math.PI * 2);
          ctx.fillStyle = glOuter;
          ctx.fill();
        }

        const cr = c.main ? c.r : c.r * 0.6;
        if (!c.main) {
          // Subtle glow for minor cities (simple alpha, no gradient)
          ctx.beginPath();
          ctx.arc(c.x, c.y, cr + 6, 0, Math.PI * 2);
          ctx.fillStyle = dark ? "rgba(201,104,72,0.12)" : "rgba(196,105,79,0.20)";
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(c.x, c.y, cr, 0, Math.PI * 2);
        ctx.fillStyle = c.main
          ? dark ? "#C96848" : "#B85C3F"
          : dark ? "rgba(201,104,72,0.55)" : "rgba(196,105,79,0.70)";
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
          ctx.strokeStyle = dark ? "rgba(201,104,72,0.3)" : "rgba(196,105,79,0.50)";
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
        rotRef.current += 0.0015;
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
          </div>
        </div>
      ))}
    </div>
  );
}
