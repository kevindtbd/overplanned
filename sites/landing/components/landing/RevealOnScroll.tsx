"use client";

import { useEffect, useRef, type ReactNode } from "react";

interface RevealOnScrollProps {
  children: ReactNode;
  className?: string;
  delay?: number;
}

function reveal(el: HTMLElement) {
  el.style.opacity = "1";
  el.style.transform = "translateY(0)";
}

export default function RevealOnScroll({
  children,
  className = "",
  delay = 0,
}: RevealOnScrollProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Fallback: reveal after 2s in case observer never fires
    const fallback = setTimeout(() => reveal(el), 2000 + delay);

    if (!("IntersectionObserver" in window)) {
      reveal(el);
      return () => clearTimeout(fallback);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            clearTimeout(fallback);
            // Use a short delay to stagger animations
            setTimeout(() => reveal(entry.target as HTMLElement), delay);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.01, rootMargin: "0px 0px -20px 0px" }
    );

    observer.observe(el);
    return () => {
      clearTimeout(fallback);
      observer.disconnect();
    };
  }, [delay]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: 0,
        transform: "translateY(18px)",
        transition: `opacity 650ms ease-out, transform 650ms ease-out`,
      }}
    >
      {children}
    </div>
  );
}
