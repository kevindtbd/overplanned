"use client";

import { MobileNav } from "@/components/nav/MobileNav";
import { DesktopSidebar } from "@/components/nav/DesktopSidebar";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-app">
      {/* Desktop: sidebar */}
      <DesktopSidebar />

      {/* Main content area */}
      <main
        className="
          pb-20
          lg:pb-0 lg:pl-60
          min-h-screen
        "
      >
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </div>
      </main>

      {/* Mobile: bottom tab bar */}
      <MobileNav />
    </div>
  );
}
