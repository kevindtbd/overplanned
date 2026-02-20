import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token;
    const path = req.nextUrl.pathname;

    // Public paths that don't require auth
    const publicPaths = [
      "/",
      "/auth/signin",
      "/auth/error",
      "/about",
      "/privacy",
      "/terms",
    ];

    if (publicPaths.some((p) => path.startsWith(p))) {
      return NextResponse.next();
    }

    // Admin-only paths
    if (path.startsWith("/admin")) {
      if (token?.systemRole !== "admin") {
        return NextResponse.redirect(new URL("/", req.url));
      }
    }

    // Access control check
    const hasAccess =
      token?.subscriptionTier &&
      ["beta", "lifetime", "pro"].includes(token.subscriptionTier);

    if (!hasAccess && !publicPaths.some((p) => path.startsWith(p))) {
      return NextResponse.redirect(new URL("/auth/signin", req.url));
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
  }
);

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public folder)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
