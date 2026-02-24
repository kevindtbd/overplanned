import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Public paths — no auth required
const PUBLIC_PATHS = [
  "/",
  "/auth/signin",
  "/auth/error",
  "/about",
  "/privacy",
  "/terms",
  "/s/",
  "/invite/",
  "/api/auth/",
  "/api/health",
  // Dev-mode dashboard access (bypasses auth in local development)
  ...(process.env.NODE_ENV === "development" ? ["/dashboard", "/dashboard/"] : []),
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    // Exact match OR prefix match — but only treat multi-character paths as
    // prefixes (prevents "/" from matching every route via startsWith).
    (p) => pathname === p || (p.length > 1 && p.endsWith("/") && pathname.startsWith(p))
  );
}

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;

  // Block /dev/* routes in production (belt-and-suspenders with the dev layout).
  if (process.env.NODE_ENV === "production" && path.startsWith("/dev/")) {
    return new NextResponse(null, { status: 404 });
  }

  if (isPublicPath(path)) {
    return NextResponse.next();
  }

  // Session cookie check (works for both JWT and database strategies).
  // In production (HTTPS), NextAuth prefixes with __Secure-.
  const sessionToken =
    req.cookies.get("next-auth.session-token") ||
    req.cookies.get("__Secure-next-auth.session-token");

  if (!sessionToken) {
    const signInUrl = new URL("/auth/signin", req.url);
    signInUrl.searchParams.set("callbackUrl", path);
    return NextResponse.redirect(signInUrl);
  }

  // Admin and subscription-tier checks happen server-side via
  // getServerSession() in pages/API routes.
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
