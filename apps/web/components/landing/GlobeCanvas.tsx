"use client";

import { useEffect, useRef } from "react";

export default function GlobeCanvas({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const tRef = useRef(0);
  const rotRef = useRef(-0.5);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    function isDark() {
      return document.documentElement.getAttribute("data-theme") === "dark";
    }

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

    const CITIES = [
      { lat: 35.67, lng: 139.65, name: "Tokyo", r: 7, main: true },
      { lat: 35.01, lng: 135.77, name: "Kyoto", r: 5.5, main: true },
      { lat: 37.57, lng: 126.98, name: "Seoul", r: 6, main: true },
      { lat: 41.39, lng: 2.17, name: "Barcelona", r: 5, main: true },
      { lat: 48.86, lng: 2.35, r: 4, main: false, name: "" },
      { lat: 40.71, lng: -74.01, r: 4, main: false, name: "" },
      { lat: 1.35, lng: 103.82, r: 3.5, main: false, name: "" },
      { lat: 22.32, lng: 114.17, r: 3.5, main: false, name: "" },
      { lat: 34.69, lng: 135.5, r: 4, main: false, name: "" },
      { lat: -33.87, lng: 151.21, r: 3.5, main: false, name: "" },
    ];
    const ROUTES = [[0, 1], [0, 2], [3, 4], [0, 8], [5, 3], [6, 7]];

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

      // Project cities
      const pC = CITIES.map((c) => ({ ...c, ...pr(ll(c.lat, c.lng), cx, cy, R) }));

      // Routes
      ROUTES.forEach((r, i) => {
        const a = pC[r[0]];
        const b = pC[r[1]];
        if (!a || !b || !a.vis || !b.vis) return;
        ctx.beginPath();
        ctx.setLineDash([4, 3]);
        const al = 0.28 + 0.14 * Math.sin(t * 0.018 + i);
        ctx.strokeStyle = dark ? `rgba(201,104,72,${al})` : `rgba(184,92,63,${al})`;
        ctx.lineWidth = 1;
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2 - 18;
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Cities
      pC.forEach((c, i) => {
        if (!c.vis) return;
        const cr = c.r * (c.main ? 1 + 0.08 * Math.sin(t * 0.025 + i) : 0.6);
        if (c.main) {
          const gl = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, cr + 6);
          gl.addColorStop(0, dark ? "rgba(201,104,72,0.22)" : "rgba(184,92,63,0.15)");
          gl.addColorStop(1, "rgba(0,0,0,0)");
          ctx.beginPath();
          ctx.arc(c.x, c.y, cr + 6, 0, Math.PI * 2);
          ctx.fillStyle = gl;
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(c.x, c.y, cr, 0, Math.PI * 2);
        ctx.fillStyle = c.main
          ? dark ? "#C96848" : "#B85C3F"
          : dark ? "rgba(201,104,72,0.4)" : "rgba(184,92,63,0.35)";
        ctx.fill();
        ctx.strokeStyle = dark ? "rgba(14,12,9,0.85)" : "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        if (c.main && c.name) {
          ctx.fillStyle = dark ? "rgba(240,234,226,0.65)" : "rgba(26,22,18,0.6)";
          ctx.font = "500 9px Sora,sans-serif";
          ctx.fillText(c.name, c.x + cr + 5, c.y + 3);
        }
      });

      // Traveling dot
      const tN = (t % 160) / 160;
      const p0 = pC[0];
      const p1 = pC[1];
      if (p0 && p1 && p0.vis && p1.vis) {
        const mx = (p0.x + p1.x) / 2;
        const my = (p0.y + p1.y) / 2 - 18;
        const tx = (1 - tN) * (1 - tN) * p0.x + 2 * (1 - tN) * tN * mx + tN * tN * p1.x;
        const ty = (1 - tN) * (1 - tN) * p0.y + 2 * (1 - tN) * tN * my + tN * tN * p1.y;
        ctx.beginPath();
        ctx.arc(tx, ty, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "#C96848" : "#B85C3F";
        ctx.fill();
        ctx.strokeStyle = dark ? "rgba(14,12,9,0.85)" : "#fff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      tRef.current++;
      rotRef.current += 0.0018;
      rafRef.current = requestAnimationFrame(frame);
    }

    resize();

    // Only start animation if the canvas has non-zero dimensions.
    // If parent is display:none (e.g. desktop globe on mobile), skip.
    if (canvas.width > 0 && canvas.height > 0) {
      frame();
    }

    function onResize() {
      const prevW = canvas!.width;
      resize();
      // Start animation if canvas just became visible (was 0, now non-zero)
      if (prevW === 0 && canvas!.width > 0 && canvas!.height > 0) {
        frame();
      }
    }

    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return <canvas ref={canvasRef} className={`absolute inset-0 w-full h-full ${className}`} />;
}
