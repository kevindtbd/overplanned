import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN,

  enabled: process.env.NODE_ENV === "production",

  environment: process.env.NODE_ENV,

  // Low sample rate for beta — saves free-tier quota
  tracesSampleRate: 0.1,
});
