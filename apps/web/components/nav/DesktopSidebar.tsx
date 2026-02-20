"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  label: string;
  href: string;
  icon: (active: boolean) => React.ReactNode;
}

const navItems: NavItem[] = [
  {
    label: "Home",
    href: "/",
    icon: (active) => (
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z" />
        <path d="M9 21V12h6v9" />
      </svg>
    ),
  },
  {
    label: "Trips",
    href: "/trips",
    icon: (active) => (
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
        <circle cx="12" cy="9" r="2.5" />
      </svg>
    ),
  },
  {
    label: "Explore",
    href: "/explore",
    icon: (active) => (
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
      </svg>
    ),
  },
  {
    label: "Profile",
    href: "/profile",
    icon: (active) => (
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="8" r="4" />
        <path d="M20 21a8 8 0 00-16 0" />
      </svg>
    ),
  },
];

function Logo() {
  return (
    <div className="flex items-center gap-2 px-4 py-6">
      <svg
        width="28"
        height="28"
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
      >
        <rect
          x="2"
          y="2"
          width="24"
          height="24"
          rx="6"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-terracotta"
        />
        <path
          d="M8 10h12M8 14h8M8 18h10"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          className="text-terracotta"
        />
      </svg>
      <span className="font-sora text-lg font-semibold text-primary tracking-tight">
        Overplanned
      </span>
    </div>
  );
}

export function DesktopSidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-60 bg-warm-surface border-r border-warm z-40"
      role="navigation"
      aria-label="Main navigation"
    >
      <Logo />

      <ul className="flex flex-col gap-1 px-3 mt-2">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? "bg-terracotta/10 text-terracotta"
                    : "text-warm-text-secondary hover:text-warm-text-primary hover:bg-warm-background"
                }`}
                aria-current={isActive ? "page" : undefined}
              >
                {item.icon(isActive)}
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto px-3 pb-4">
        <div className="px-3 py-2">
          <span className="font-dm-mono text-[10px] uppercase tracking-wider text-warm-text-secondary">
            Beta
          </span>
        </div>
      </div>
    </aside>
  );
}
