"use client";

import { useEffect, useState } from "react";

const BG_TOKENS = ["base", "surface", "raised", "overlay", "input", "stone", "warm"];
const INK_TOKENS = [100, 200, 300, 400, 500, 600, 700, 800, 900];
const ACCENT_TOKENS = ["accent", "accent-light", "accent-muted", "accent-fg"];
const SEMANTIC = ["success", "info", "warning", "error"];

function Swatch({ label, cssVar }: { label: string; cssVar: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <div
        className="w-10 h-10 rounded-lg border border-ink-700"
        style={{ background: `var(--${cssVar})` }}
      />
      <div>
        <div className="font-dm-mono text-[10px] text-ink-400">{`--${cssVar}`}</div>
        <div className="font-sora text-xs text-ink-200">{label}</div>
      </div>
    </div>
  );
}

export default function TokenSwatchPage() {
  const [theme, setTheme] = useState("light");

  useEffect(() => {
    setTheme(document.documentElement.getAttribute("data-theme") || "light");
  }, []);

  const toggle = () => {
    const next = theme === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    setTheme(next);
  };

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8" style={{ background: "var(--bg-base)" }}>
      <div className="flex justify-between items-center">
        <h1 className="font-sora text-2xl font-bold text-ink-100">Token Swatch</h1>
        <button onClick={toggle} className="btn-primary">
          Theme: {theme}
        </button>
      </div>

      <section>
        <h2 className="section-eyebrow mb-4">Backgrounds</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {BG_TOKENS.map((t) => (
            <Swatch key={t} label={t} cssVar={`bg-${t}`} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Ink Scale (100=darkest)</h2>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
          {INK_TOKENS.map((n) => (
            <Swatch key={n} label={`ink-${n}`} cssVar={`ink-${n}`} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Accent</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {ACCENT_TOKENS.map((t) => (
            <Swatch key={t} label={t} cssVar={t} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Gold</h2>
        <div className="grid grid-cols-2 gap-2">
          <Swatch label="gold" cssVar="gold" />
          <Swatch label="gold-light" cssVar="gold-light" />
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Semantic</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {SEMANTIC.map((s) => (
            <div key={s} className="space-y-1">
              <Swatch label={s} cssVar={s} />
              <Swatch label={`${s}-bg`} cssVar={`${s}-bg`} />
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Typography</h2>
        <div className="space-y-3">
          <p className="font-sora text-ink-100">Sora: Body text and UI elements</p>
          <p className="font-dm-mono text-ink-300">DM Mono: Data labels and badges</p>
          <p className="font-lora italic text-ink-200 text-lg">Lora: Serif headlines and emotional text</p>
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Components</h2>
        <div className="space-y-4">
          <div className="flex gap-3 flex-wrap">
            <button className="btn-primary">Primary Button</button>
            <button className="btn-secondary">Secondary Button</button>
            <button className="btn-ghost">Ghost Button</button>
          </div>
          <div className="flex gap-2 flex-wrap">
            <span className="chip chip-local">Local Gem</span>
            <span className="chip chip-source">Multi Source</span>
            <span className="chip chip-busy">Peak Hours</span>
          </div>
          <div className="card p-4">
            <p className="label-mono mb-2">Card Component</p>
            <p className="text-ink-300 text-sm">A card with the design token system applied.</p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Shadows</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {["sm", "md", "lg", "card", "xl"].map((s) => (
            <div
              key={s}
              className="p-4 rounded-xl text-center text-ink-300 font-dm-mono text-xs"
              style={{
                background: "var(--bg-surface)",
                boxShadow: `var(--shadow-${s})`,
              }}
            >
              shadow-{s}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Skeleton</h2>
        <div className="space-y-2">
          <div className="skel h-4 w-3/4" />
          <div className="skel h-4 w-1/2" />
          <div className="skel h-4 w-2/3" />
        </div>
      </section>
    </div>
  );
}
