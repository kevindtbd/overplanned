"use client";

import { useEffect, useState } from "react";

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    if (current === "light" || current === "dark") setTheme(current);

    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    document.documentElement.style.colorScheme = next;
    localStorage.setItem("theme", next);
    setTheme(next);
  }

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 flex items-center justify-between h-[62px] px-6 lg:px-14 transition-all duration-300 ${
        scrolled
          ? "backdrop-blur-xl border-b border-ink-700"
          : ""
      }`}
      style={scrolled ? { backgroundColor: "var(--bg-surface-80)" } : undefined}
    >
      <a href="/" className="font-sora text-[19px] font-bold tracking-[-0.04em] text-ink-100 no-underline">
        overplanned<span className="text-accent">.</span>
      </a>

      <div className="hidden md:flex items-center gap-8">
        <a href="#output" className="font-dm-mono text-[10px] tracking-[0.1em] uppercase text-ink-400 hover:text-ink-100 transition-colors no-underline">
          The Output
        </a>
        <a href="#how" className="font-dm-mono text-[10px] tracking-[0.1em] uppercase text-ink-400 hover:text-ink-100 transition-colors no-underline">
          How It Works
        </a>
        <a href="#group" className="font-dm-mono text-[10px] tracking-[0.1em] uppercase text-ink-400 hover:text-ink-100 transition-colors no-underline">
          Group Trips
        </a>
        <a href="#waitlist" className="font-dm-mono text-[10px] tracking-[0.1em] uppercase text-ink-400 hover:text-ink-100 transition-colors no-underline">
          Join
        </a>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={toggleTheme}
          className="w-[34px] h-[34px] rounded-full bg-raised border border-ink-700 flex items-center justify-center text-ink-400 hover:text-ink-100 hover:border-ink-500 transition-all"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        <a
          href="#waitlist"
          className="btn-primary text-[13px] px-5 py-2 no-underline"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}
