"use client";

import Image from "next/image";
import Link from "next/link";
import { MobileNav } from "@/components/nav/MobileNav";
import { DesktopSidebar } from "@/components/nav/DesktopSidebar";

// ---------- Types ----------

type AppShellProps = {
  children: React.ReactNode;
  /** 'app' = standard pages with bottom nav, 'trip' = inside a trip (no bottom nav, hero + day strip) */
  context?: "app" | "trip";
  /** Trip hero photo URL (trip context only) */
  tripPhoto?: string;
  /** Trip name displayed in the hero (trip context only) */
  tripName?: string;
};

// ---------- Trip Hero ----------

function TripHero({ tripPhoto, tripName }: { tripPhoto?: string; tripName?: string }) {
  return (
    <div className="relative h-48 w-full overflow-hidden flex-shrink-0">
      {tripPhoto ? (
        <Image
          src={tripPhoto}
          alt={tripName || "Trip photo"}
          fill
          sizes="100vw"
          className="object-cover"
          priority
        />
      ) : (
        <div className="w-full h-full bg-stone" />
      )}
      {/* Warm overlay */}
      <div className="photo-overlay-warm absolute inset-0" aria-hidden="true" />
      {/* Trip name over hero */}
      <div className="absolute bottom-0 left-0 right-0 p-5">
        <p className="font-dm-mono text-[8px] uppercase tracking-[0.12em] text-white/45 mb-1">
          Active trip
        </p>
        {tripName && (
          <h1 className="font-sora text-xl font-medium text-white tracking-[-0.02em] leading-tight">
            {tripName}
          </h1>
        )}
      </div>
    </div>
  );
}

// ---------- Wordmark (mobile top bar, app context only) ----------

function MobileTopBar() {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-ink-900 lg:hidden">
      <span className="font-sora font-semibold text-base tracking-[-0.04em] text-ink-100">
        overplanned<span className="text-accent">.</span>
      </span>
      <Link href="/settings" aria-label="Settings">
        <div className="w-7 h-7 rounded-full bg-raised flex items-center justify-center">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-ink-400"
            aria-hidden="true"
          >
            <circle cx="12" cy="8" r="4" />
            <path d="M20 21a8 8 0 00-16 0" />
          </svg>
        </div>
      </Link>
    </div>
  );
}

// ---------- Component ----------

export function AppShell({
  children,
  context = "app",
  tripPhoto,
  tripName,
}: AppShellProps) {
  const isTrip = context === "trip";

  return (
    <div className="min-h-screen bg-base">
      {/* Desktop: sidebar (both contexts) */}
      <DesktopSidebar />

      {/* Main content area */}
      <main
        className={`
          min-h-screen
          lg:pl-60
          ${isTrip ? "pb-0" : "pb-20 lg:pb-0"}
        `}
      >
        {isTrip ? (
          <>
            {/* Trip context: hero + day strip, no bottom nav */}
            <TripHero tripPhoto={tripPhoto} tripName={tripName} />
            <div className="mx-auto max-w-[1100px] px-6 py-12 lg:px-10 lg:py-16">
              {children}
            </div>
          </>
        ) : (
          <>
            {/* App context: top bar + standard padding */}
            <MobileTopBar />
            <div className="mx-auto max-w-[1100px] px-6 py-12 lg:px-10 lg:py-16">
              {children}
            </div>
          </>
        )}
      </main>

      {/* Mobile bottom nav — app context only */}
      {!isTrip && <MobileNav />}
    </div>
  );
}
