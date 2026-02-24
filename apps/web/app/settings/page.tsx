"use client";

// Settings Page -- /settings
// Single scrollable page with anchor nav: Account, Subscription, Display,
// Travel Style, Notifications, Privacy, About.

import { useSession } from "next-auth/react";
import { AppShell } from "@/components/layout/AppShell";
import { CardSkeleton, ErrorState } from "@/components/states";
import { AccountSection } from "@/components/settings/AccountSection";
import { SubscriptionBadge } from "@/components/settings/SubscriptionBadge";
import { DisplayPreferences } from "@/components/settings/DisplayPreferences";
import { TravelStyleSection } from "@/components/settings/TravelStyleSection";
import { NotificationsSection } from "@/components/settings/NotificationsSection";
import { PrivacySection } from "@/components/settings/PrivacySection";
import { AboutSection } from "@/components/settings/AboutSection";

const SECTION_ANCHORS = [
  { id: "account", label: "Account" },
  { id: "subscription", label: "Subscription" },
  { id: "display", label: "Display" },
  { id: "travel-style", label: "Travel Style" },
  { id: "notifications", label: "Notifications" },
  { id: "privacy", label: "Privacy" },
  { id: "about", label: "About" },
];

// ---------- Component ----------

export default function SettingsPage() {
  const { data: session, status } = useSession();

  return (
    <AppShell context="app">
      <div className="space-y-8">
        {/* Page header */}
        <header>
          <h1 className="font-sora text-2xl font-medium text-ink-100 sm:text-3xl">
            Settings
          </h1>
          <p className="mt-1 font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Account, preferences, and privacy
          </p>
        </header>

        {/* Loading state */}
        {status === "loading" && (
          <div className="space-y-4">
            <CardSkeleton className="h-48" />
            <CardSkeleton className="h-24" />
            <CardSkeleton className="h-24" />
          </div>
        )}

        {/* Unauthenticated */}
        {status === "unauthenticated" && (
          <ErrorState message="You need to be signed in to view settings." />
        )}

        {/* Anchor nav */}
        {status === "authenticated" && (
          <nav className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
            {SECTION_ANCHORS.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="shrink-0 rounded-full border border-ink-700 px-3 py-1 font-dm-mono text-xs text-ink-400 transition-colors hover:border-accent hover:text-accent"
              >
                {s.label}
              </a>
            ))}
          </nav>
        )}

        {/* Authenticated — render sections */}
        {status === "authenticated" && session?.user && (
          <div className="space-y-10">
            <AccountSection
              name={session.user.name || null}
              email={session.user.email}
              provider="google"
            />

            <SubscriptionBadge tier={session.user.subscriptionTier} />

            <DisplayPreferences />

            <TravelStyleSection />

            <NotificationsSection />

            <PrivacySection email={session.user.email} />

            <AboutSection />
          </div>
        )}
      </div>
    </AppShell>
  );
}
