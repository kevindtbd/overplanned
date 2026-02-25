import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,

  enabled: process.env.NODE_ENV === "production",

  environment: process.env.NODE_ENV,

  // Low sample rate for beta — saves free-tier quota
  tracesSampleRate: 0.1,

  // Session replay — only capture on error, skip normal sessions
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0.5,

  // Filter noisy browser errors that are not actionable
  ignoreErrors: [
    // Browser extensions and third-party scripts
    "ResizeObserver loop limit exceeded",
    "ResizeObserver loop completed with undelivered notifications",
    // Network errors from user connectivity
    "Failed to fetch",
    "NetworkError",
    "Load failed",
  ],

  // Keep bundle lean — only load replay integration when an error occurs
  integrations: [
    Sentry.replayIntegration({
      maskAllText: true,
      blockAllMedia: true,
    }),
  ],
});
