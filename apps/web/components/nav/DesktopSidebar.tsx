"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// ---------- Inline SVG Icons ----------

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={active ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function TripsIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={active ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
      <circle cx="12" cy="9" r="2.5" />
    </svg>
  );
}

function ExploreIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={active ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

function ProfileIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={active ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M20 21a8 8 0 00-16 0" />
    </svg>
  );
}

// ---------- Nav Items ----------

interface NavItem {
  label: string;
  href: string;
  Icon: React.ComponentType<{ active: boolean }>;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Home", href: "/", Icon: HomeIcon },
  { label: "Trips", href: "/trips", Icon: TripsIcon },
  { label: "Explore", href: "/explore", Icon: ExploreIcon },
  { label: "Profile", href: "/profile", Icon: ProfileIcon },
];

// ---------- Wordmark ----------

function Wordmark() {
  return (
    <div className="flex items-center px-4 py-6">
      <span className="font-sora font-semibold text-lg tracking-[-0.04em] text-ink-100">
        overplanned<span className="text-accent">.</span>
      </span>
    </div>
  );
}

// ---------- Component ----------

export function DesktopSidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="
        hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-60
        bg-surface border-r border-ink-900 z-40
      "
      role="navigation"
      aria-label="Main navigation"
    >
      <Wordmark />

      <ul className="flex flex-col gap-1 px-3 mt-2">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg
                  text-sm font-medium transition-colors duration-150
                  ${
                    isActive
                      ? "bg-accent/10 text-accent"
                      : "text-ink-400 hover:text-ink-100 hover:bg-raised"
                  }
                `}
                aria-current={isActive ? "page" : undefined}
              >
                <item.Icon active={isActive} />
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto px-3 pb-4">
        <div className="px-3 py-2">
          <span className="label-mono">
            Beta
          </span>
        </div>
      </div>
    </aside>
  );
}
