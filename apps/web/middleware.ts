import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

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
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || (p.endsWith("/") && pathname.startsWith(p))
  );
}

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token;
    const path = req.nextUrl.pathname;

    if (isPublicPath(path)) {
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

    if (!hasAccess) {
      return NextResponse.redirect(new URL("/auth/signin", req.url));
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token, req }) => {
        // Allow public paths through without a token
        if (isPublicPath(req.nextUrl.pathname)) {
          return true;
        }
        return !!token;
      },
    },
  }
);

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
