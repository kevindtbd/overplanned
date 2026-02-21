"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function LandingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 flex items-center justify-between h-[62px] px-6 lg:px-14 transition-all duration-300 ${
        scrolled
          ? "bg-surface/80 backdrop-blur-xl border-b border-ink-700"
          : "bg-transparent"
      }`}
    >
      {/* Wordmark */}
      <Link href="/" className="font-sora text-[19px] font-bold tracking-[-0.04em] text-ink-100 no-underline">
        overplanned<span className="text-accent">.</span>
      </Link>

      {/* Center nav links -- hidden on mobile */}
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

      {/* CTA */}
      <Link
        href="/auth/signin"
        className="font-sora text-[13px] font-semibold text-white bg-ink-100 border-none rounded-full px-5 py-2 hover:bg-accent transition-colors no-underline"
      >
        Get Started
      </Link>
    </nav>
  );
}
