/**
 * POST /api/auth/dev-login — Dev-only login bypass
 *
 * Mints a real NextAuth JWT for any existing user, skipping Google OAuth.
 * Only available in development.
 *
 * SECURITY: Three layers prevent production exposure:
 * 1. Build-time: throws at import if NODE_ENV !== development
 * 2. Runtime: early return 404 if NODE_ENV !== development
 * 3. UI: sign-in page only renders dev buttons in development
 *
 * Body: { email: string }
 * Sets: next-auth.session-token cookie (signed JWT)
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { encode } from "next-auth/jwt";

const IS_DEV = process.env.NODE_ENV === "development";

export async function POST(req: NextRequest) {
  // Runtime guard — only available in development.
  // Returns a bare 404 with no body so it is indistinguishable from
  // a non-existent route (defense-in-depth alongside the middleware block).
  if (!IS_DEV) {
    return new NextResponse(null, { status: 404 });
  }

  let body: { email?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = body.email?.trim().toLowerCase();
  if (!email) {
    return NextResponse.json({ error: "Email required" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    return NextResponse.json(
      { error: `No user found with email: ${email}` },
      { status: 404 }
    );
  }

  // Mint a real JWT matching what NextAuth's jwt callback produces
  const maxAge = 30 * 24 * 60 * 60; // 30 days
  const token = await encode({
    secret: process.env.NEXTAUTH_SECRET!,
    maxAge,
    token: {
      id: user.id,
      email: user.email,
      name: user.name,
      picture: user.image,
      subscriptionTier: user.subscriptionTier,
      systemRole: user.systemRole,
      sub: user.id,
    },
  });

  const expires = new Date(Date.now() + maxAge * 1000);

  // Set the session cookie (non-HTTPS in dev = no __Secure- prefix)
  const res = NextResponse.json({
    ok: true,
    user: { id: user.id, email: user.email, name: user.name },
  });

  res.cookies.set("next-auth.session-token", token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    expires,
  });

  return res;
}
