"use client";

import Image from "next/image";
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
          <h1 className="font-lora text-xl font-medium text-white tracking-[-0.02em] leading-tight">
            {tripName}
          </h1>
        )}
      </div>
    </div>
  );
}

// ---------- Day Strip ----------

function DayStrip() {
  // Placeholder day strip — will be wired to trip state in Track 3/5
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const activeIndex = 3; // placeholder

  return (
    <div
      className="
        flex gap-0 overflow-x-auto scrollbar-none
        bg-raised border-b border-ink-700 px-4
      "
      role="tablist"
      aria-label="Trip days"
    >
      {days.map((day, i) => (
        <button
          key={day}
          type="button"
          role="tab"
          aria-selected={i === activeIndex}
          className={`
            font-dm-mono text-[8px] uppercase tracking-[0.06em]
            px-3 py-2 whitespace-nowrap flex-shrink-0
            border-b-2 transition-colors duration-150
            ${
              i === activeIndex
                ? "text-ink-100 border-accent"
                : "text-ink-500 border-transparent hover:text-ink-300"
            }
          `}
        >
          {day}
        </button>
      ))}
    </div>
  );
}

// ---------- Wordmark (mobile top bar, app context only) ----------

function MobileTopBar() {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-ink-900 lg:hidden">
      <span className="font-sora font-bold text-base tracking-[-0.04em] text-ink-100">
        overplanned<span className="text-accent">.</span>
      </span>
      {/* Avatar slot — placeholder circle */}
      <div className="w-7 h-7 rounded-full bg-raised" aria-hidden="true" />
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
            <DayStrip />
            <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
              {children}
            </div>
          </>
        ) : (
          <>
            {/* App context: top bar + standard padding */}
            <MobileTopBar />
            <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
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
