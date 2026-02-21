import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("CSS token resolution", () => {
  const css = fs.readFileSync(
    path.resolve(__dirname, "../../app/globals.css"),
    "utf-8"
  );

  const requiredTokens = [
    "--bg-base", "--bg-surface", "--bg-raised", "--bg-overlay",
    "--bg-input", "--bg-stone", "--bg-warm",
    "--accent", "--accent-light", "--accent-muted", "--accent-fg",
    "--gold", "--gold-light",
    "--ink-100", "--ink-200", "--ink-300", "--ink-400", "--ink-500",
    "--ink-600", "--ink-700", "--ink-800", "--ink-900",
    "--success", "--success-bg", "--info", "--info-bg",
    "--warning", "--warning-bg", "--error", "--error-bg",
    "--shadow-sm", "--shadow-md", "--shadow-lg", "--shadow-card", "--shadow-xl",
    "--transition-fast", "--transition-normal", "--transition-slow",
  ];

  it("defines all required tokens in light theme", () => {
    for (const token of requiredTokens) {
      expect(css, `Missing token: ${token}`).toContain(`${token}:`);
    }
  });

  it("has data-theme light selector", () => {
    expect(css).toContain('[data-theme="light"]');
  });

  it("has data-theme dark selector", () => {
    expect(css).toContain('[data-theme="dark"]');
  });

  it("has prefers-color-scheme dark fallback", () => {
    expect(css).toContain("prefers-color-scheme: dark");
  });

  it("has no backward-compatible aliases (removed in Phase 2)", () => {
    const oldAliases = [
      "--color-terracotta", "--color-warm-background", "--color-warm-surface",
      "--color-warm-border", "--color-warm-text-primary", "--color-warm-text-secondary",
    ];
    for (const alias of oldAliases) {
      expect(css, `Stale alias still present: ${alias}`).not.toContain(`${alias}:`);
    }
  });

  it("uses #C4694F for accent (CLAUDE.md canonical)", () => {
    expect(css).toContain("#C4694F");
  });

  it("has shimmer keyframes with reduced-motion pause", () => {
    expect(css).toContain("@keyframes shimmer");
    expect(css).toContain("prefers-reduced-motion");
  });
});
