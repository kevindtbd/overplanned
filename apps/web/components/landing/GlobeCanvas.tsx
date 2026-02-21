"use client";

import { useEffect, useRef, useState, useCallback } from "react";

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
/*  City + card data                                                    */
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
  {
    lat: 35.67, lng: 139.65, name: "Tokyo", r: 9, main: true,
    card: { eyebrow: "TOKYO \u00B7 DAY 1", title: "Tsukiji outer market", desc: "locals-only \u00B7 06:00 counter", tag: "Tabelog \u00B7 8.1k" },
  },
  {
    lat: 35.01, lng: 135.77, name: "Kyoto", r: 8, main: true,
    card: { eyebrow: "KYOTO \u00B7 DAY 3", title: "Kinkaku-ji", desc: "weekday \u00B7 thins out by 15:00", tag: "Tabelog \u00B7 4.2k" },
  },
  {
    lat: 37.57, lng: 126.98, name: "Seoul", r: 8, main: true,
    card: { eyebrow: "SEOUL \u00B7 PIVOT", title: "Rain at 14:00", desc: "swapping to indoor alternative" },
  },
  {
    lat: 41.39, lng: 2.17, name: "Barcelona", r: 8.5, main: true,
    card: { eyebrow: "BARCELONA \u00B7 DAY 2", title: "El Born backstreets", desc: "pre-lunch tapas crawl", tag: "Local" },
  },
  { lat: 48.86, lng: 2.35, r: 5, main: false, name: "" },
  { lat: 40.71, lng: -74.01, r: 5, main: false, name: "" },
  { lat: 1.35, lng: 103.82, r: 5, main: false, name: "" },
  { lat: 22.32, lng: 114.17, r: 5, main: false, name: "" },
  { lat: 34.69, lng: 135.5, r: 5, main: false, name: "" },
  { lat: -33.87, lng: 151.21, r: 5, main: false, name: "" },
];

const ROUTES = [[0, 1], [0, 2], [3, 4], [0, 8], [5, 3], [6, 7]];

interface CardPos {
  x: number;
  y: number;
  opacity: number;
  visible: boolean;
  cityIdx: number;
}

export default function GlobeCanvas({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);
  const tRef = useRef(0);
  const rotRef = useRef(-0.5);
  const cardPosRef = useRef<CardPos[]>([]);
  const [cardPositions, setCardPositions] = useState<CardPos[]>([]);

  const isDark = useCallback(() => {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    function resize() {
      const par = canvas!.parentElement;
      if (!par) return;
      canvas!.width = par.offsetWidth;
      canvas!.height = par.offsetHeight;
    }

    function ll(la: number, ln: number) {
      const p = ((90 - la) * Math.PI) / 180;
      const t = ((ln + 180) * Math.PI) / 180;
      return { x: -Math.sin(p) * Math.cos(t), y: Math.cos(p), z: Math.sin(p) * Math.sin(t) };
    }

    function pr(v: { x: number; y: number; z: number }, cx: number, cy: number, R: number) {
      const cY = Math.cos(rotRef.current);
      const sY = Math.sin(rotRef.current);
      const x2 = v.x * cY + v.z * sY;
      const z2 = -v.x * sY + v.z * cY;
      return { x: cx + x2 * R, y: cy - v.y * R, z: z2, vis: z2 > -0.12 };
    }

    function frame() {
      const ctx = canvas!.getContext("2d");
      if (!ctx) return;
      const W = canvas!.width;
      const H = canvas!.height;
      if (W === 0 || H === 0) return;
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.43;
      const dark = isDark();
      const t = tRef.current;

      ctx.clearRect(0, 0, W, H);

      // Ambient glow
      const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5);
      bg.addColorStop(0, dark ? "rgba(201,104,72,0.05)" : "rgba(184,92,63,0.05)");
      bg.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Globe sphere
      const g = ctx.createRadialGradient(cx - R * 0.2, cy - R * 0.2, 0, cx, cy, R);
      g.addColorStop(0, dark ? "rgba(44,36,26,0.65)" : "rgba(255,255,255,0.5)");
      g.addColorStop(1, dark ? "rgba(18,14,9,0.2)" : "rgba(237,232,224,0.15)");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = g;
      ctx.fill();
      ctx.strokeStyle = dark ? "rgba(201,104,72,0.14)" : "rgba(184,92,63,0.11)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Grid lines
      ctx.globalAlpha = dark ? 0.09 : 0.07;
      ctx.strokeStyle = dark ? "rgba(240,234,226,0.5)" : "rgba(26,22,18,0.5)";
      ctx.lineWidth = 0.5;
      for (let la = -60; la <= 60; la += 30) {
        const rL = Math.cos((la * Math.PI) / 180) * R;
        const yL = cy - Math.sin((la * Math.PI) / 180) * R;
        ctx.beginPath();
        ctx.ellipse(cx, yL, rL, rL * 0.11, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
      for (let ln = 0; ln < 360; ln += 30) {
        const a = pr(ll(70, ln), cx, cy, R);
        const b = pr(ll(-70, ln), cx, cy, R);
        if (a.vis && b.vis) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;

      // Continent dot-matrix
      const contDotColor = dark ? "rgba(201,104,72,0.12)" : "rgba(184,92,63,0.08)";
      ctx.fillStyle = contDotColor;
      for (let i = 0; i < CONTINENT_DOTS.length; i++) {
        const [la, ln] = CONTINENT_DOTS[i];
        const v = ll(la, ln);
        const p = pr(v, cx, cy, R);
        if (p.z > -0.1) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Project cities
      const pC = CITIES.map((c) => ({ ...c, ...pr(ll(c.lat, c.lng), cx, cy, R) }));

      // Routes — thicker, more pronounced arcs
      ROUTES.forEach((r, i) => {
        const a = pC[r[0]];
        const b = pC[r[1]];
        if (!a || !b || !a.vis || !b.vis) return;
        ctx.beginPath();
        ctx.setLineDash([5, 3]);
        const al = 0.32 + 0.16 * Math.sin(t * 0.018 + i);
        ctx.strokeStyle = dark ? `rgba(201,104,72,${al})` : `rgba(184,92,63,${al})`;
        ctx.lineWidth = 1.5;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const arcH = Math.max(28, dist * 0.22);
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2 - arcH;
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Cities — bigger main dots with pulsing glow ring
      pC.forEach((c, i) => {
        if (!c.vis) return;
        if (c.main) {
          const pulse = 14 + 4 * Math.sin(t * 0.03 + i * 1.5);
          // Outer glow ring
          const glOuter = ctx.createRadialGradient(c.x, c.y, c.r * 0.5, c.x, c.y, pulse);
          glOuter.addColorStop(0, dark ? "rgba(201,104,72,0.18)" : "rgba(184,92,63,0.12)");
          glOuter.addColorStop(1, "rgba(0,0,0,0)");
          ctx.beginPath();
          ctx.arc(c.x, c.y, pulse, 0, Math.PI * 2);
          ctx.fillStyle = glOuter;
          ctx.fill();

          // Inner glow
          const glInner = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r + 4);
          glInner.addColorStop(0, dark ? "rgba(201,104,72,0.30)" : "rgba(184,92,63,0.22)");
          glInner.addColorStop(1, "rgba(0,0,0,0)");
          ctx.beginPath();
          ctx.arc(c.x, c.y, c.r + 4, 0, Math.PI * 2);
          ctx.fillStyle = glInner;
          ctx.fill();
        }

        const cr = c.main ? c.r : c.r * 0.6;
        ctx.beginPath();
        ctx.arc(c.x, c.y, cr, 0, Math.PI * 2);
        ctx.fillStyle = c.main
          ? dark ? "#C96848" : "#B85C3F"
          : dark ? "rgba(201,104,72,0.4)" : "rgba(184,92,63,0.35)";
        ctx.fill();
        ctx.strokeStyle = dark ? "rgba(14,12,9,0.85)" : "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      // Traveling dot — bigger (5px radius)
      const tN = (t % 160) / 160;
      const p0 = pC[0];
      const p1 = pC[1];
      if (p0 && p1 && p0.vis && p1.vis) {
        const dx = p1.x - p0.x;
        const dy = p1.y - p0.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const arcH = Math.max(28, dist * 0.22);
        const mx = (p0.x + p1.x) / 2;
        const my = (p0.y + p1.y) / 2 - arcH;
        const tx = (1 - tN) * (1 - tN) * p0.x + 2 * (1 - tN) * tN * mx + tN * tN * p1.x;
        const ty = (1 - tN) * (1 - tN) * p0.y + 2 * (1 - tN) * tN * my + tN * tN * p1.y;

        // Glow behind traveling dot
        const tGl = ctx.createRadialGradient(tx, ty, 0, tx, ty, 12);
        tGl.addColorStop(0, dark ? "rgba(201,104,72,0.25)" : "rgba(184,92,63,0.18)");
        tGl.addColorStop(1, "rgba(0,0,0,0)");
        ctx.beginPath();
        ctx.arc(tx, ty, 12, 0, Math.PI * 2);
        ctx.fillStyle = tGl;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(tx, ty, 5, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "#C96848" : "#B85C3F";
        ctx.fill();
        ctx.strokeStyle = dark ? "rgba(14,12,9,0.85)" : "#fff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Update card positions (throttled to ~30fps: every other frame at 60fps)
      if (t % 2 === 0) {
        const newPositions: CardPos[] = [];
        pC.forEach((c, i) => {
          if (!c.main || !c.card) return;
          const vis = c.z > 0;
          const opacity = vis ? Math.min(1, c.z * 2.5) : 0;
          newPositions.push({
            x: c.x + 15,
            y: c.y - 5,
            opacity,
            visible: vis,
            cityIdx: i,
          });
        });
        cardPosRef.current = newPositions;
        setCardPositions(newPositions);
      }

      tRef.current++;
      rotRef.current += 0.0018;
      rafRef.current = requestAnimationFrame(frame);
    }

    resize();

    if (canvas.width > 0 && canvas.height > 0) {
      frame();
    }

    function onResize() {
      const prevW = canvas!.width;
      resize();
      if (prevW === 0 && canvas!.width > 0 && canvas!.height > 0) {
        frame();
      }
    }

    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, [isDark]);

  return (
    <div ref={wrapperRef} className={`absolute inset-0 w-full h-full ${className}`} style={{ position: "absolute" }}>
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      {/* Tooltip card overlays */}
      {cardPositions.map((pos) => {
        const city = CITIES[pos.cityIdx];
        if (!city.card || !pos.visible) return null;
        const bob = Math.sin(Date.now() * 0.002 + pos.cityIdx * 1.3) * 3;
        return (
          <div
            key={city.name}
            className="absolute pointer-events-none z-[4]"
            style={{
              left: pos.x,
              top: pos.y + bob,
              opacity: pos.opacity,
              transition: "opacity 0.4s ease",
              transform: "translateY(-50%)",
            }}
          >
            <div className="card rounded-[14px] shadow-lg p-[10px_14px] min-w-[140px] max-w-[180px]">
              <div className="font-dm-mono text-[8px] tracking-[0.1em] uppercase text-accent-fg mb-[3px]">
                {city.card.eyebrow}
              </div>
              <div className="text-[12px] font-medium text-ink-100 mb-[2px] whitespace-nowrap">
                {city.card.title}
              </div>
              <div className="text-[10px] text-ink-400 font-light italic whitespace-nowrap">
                {city.card.desc}
              </div>
              {city.card.tag && (
                <span className="font-dm-mono text-[8px] text-info bg-info-bg px-1.5 py-0.5 rounded-full inline-block mt-[5px]">
                  {city.card.tag}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
