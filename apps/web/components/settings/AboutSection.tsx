"use client";

// ---------- Icons ----------

function ExternalLinkIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="inline-block ml-1 opacity-40"
      aria-hidden="true"
    >
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

// ---------- Component ----------

const LEGAL_LINKS = [
  { label: "Terms of Service", href: "/legal/terms" },
  { label: "Privacy Policy", href: "/legal/privacy" },
  { label: "Accessibility Statement", href: "/legal/accessibility" },
];

export function AboutSection() {
  return (
    <section aria-labelledby="about-heading">
      <h2 id="about-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        About
      </h2>

      <div className="rounded-[20px] border border-ink-700 bg-surface p-5 space-y-4">
        {/* App version */}
        <div>
          <span className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 block mb-1">
            Version
          </span>
          <p className="font-dm-mono text-sm text-ink-300">
            Beta
          </p>
        </div>

        {/* Legal links */}
        <div className="space-y-2">
          {LEGAL_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="block font-sora text-sm text-ink-300 hover:text-ink-100 transition-colors"
            >
              {link.label}
              <ExternalLinkIcon />
            </a>
          ))}
        </div>

        {/* Feedback */}
        <div className="pt-3 border-t border-ink-700">
          <a
            href="mailto:feedback@overplanned.com"
            className="font-sora text-sm text-accent hover:text-accent/80 transition-colors"
          >
            Send feedback
          </a>
        </div>
      </div>
    </section>
  );
}
