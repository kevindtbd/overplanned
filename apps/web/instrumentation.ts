export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export async function onRequestError(
  err: { digest?: string } & Error,
  request: {
    path: string;
    method: string;
    headers: Record<string, string>;
  },
  context: { routerKind: string; routePath: string; routeType: string },
) {
  // Sentry reporting (production only)
  if (process.env.NODE_ENV === "production") {
    const Sentry = await import("@sentry/nextjs");
    Sentry.captureException(err, {
      extra: {
        path: request.path,
        method: request.method,
        routerKind: context.routerKind,
        routePath: context.routePath,
        routeType: context.routeType,
      },
    });
  }

  // Discord webhook reporting (uses lib/error-reporting.ts — rate-limited, rich embeds)
  const { reportError } = await import("@/lib/error-reporting");
  await reportError(err, {
    path: request.path,
    method: request.method,
    route: context.routePath,
    routeType: context.routeType,
    digest: err.digest ?? "",
  });
}
