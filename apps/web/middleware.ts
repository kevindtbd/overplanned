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
  "/dashboard",
  "/dashboard/",
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || (p.endsWith("/") && pathname.startsWith(p))
  );
}

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;

  if (isPublicPath(path)) {
    return NextResponse.next();
  }

  // Database sessions use a session cookie — check for its presence.
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
  // getServerSession() in pages/API routes — the session cookie
  // doesn't carry claims like a JWT would.
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
