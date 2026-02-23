"use client";

// Settings Page -- /settings
// Single scrollable page with Account (real), stubs for future sections, and About (real).

import { useSession } from "next-auth/react";
import { AppShell } from "@/components/layout/AppShell";
import { CardSkeleton, ErrorState } from "@/components/states";
import { AccountSection } from "@/components/settings/AccountSection";
import { SubscriptionBadge } from "@/components/settings/SubscriptionBadge";
import { TravelProfileStub } from "@/components/settings/TravelProfileStub";
import { PreferencesStub } from "@/components/settings/PreferencesStub";
import { NotificationsStub } from "@/components/settings/NotificationsStub";
import { PrivacyStub } from "@/components/settings/PrivacyStub";
import { AboutSection } from "@/components/settings/AboutSection";

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

        {/* Authenticated — render sections */}
        {status === "authenticated" && session?.user && (
          <div className="space-y-10">
            <AccountSection
              name={session.user.name || null}
              email={session.user.email}
              provider="google"
            />

            <SubscriptionBadge tier={session.user.subscriptionTier} />

            <TravelProfileStub />

            <PreferencesStub />

            <NotificationsStub />

            <PrivacyStub />

            <AboutSection />
          </div>
        )}
      </div>
    </AppShell>
  );
}
